"""Volume-conservatie voor runs — overshoot vandaag = minder later deze week.

Gebruik: na week_planner.build_week, voor de events geschreven worden.

Principe:
  overshoot_km = completed_km_tot_vandaag - planned_km_tot_vandaag
  Als overshoot substantieel (>1.0km of >10% van vandaag's dagdoel): trek
  de overshoot af van resterende geplande runs deze week, proportioneel
  over hun duur.

Extra bij `state.injury.return_from_injury = true`: cap resterende runs ook
hard naar `max(completed_km_this_week)` zodat je geen plotse long run doet
na een rustig week.
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

STATE_PATH = Path(__file__).parent.parent / "state.json"

# Drempel: alleen cappen als overshoot substantieel is.
MIN_OVERSHOOT_KM = 1.0
OVERSHOOT_RATIO = 0.10  # of >10% van het dagdoel

# Ondergrens per sessie — we willen nooit een 1km-sessie uit de planning.
MIN_RUN_KM = 3.0

# Fallback pace voor minutes-naar-km wanneer sessie-km niet bekend is.
_FALLBACK_PACE_SEC_PER_KM = 330  # 5:30/km easy


def _load_state() -> dict:
    with open(STATE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _is_run(sport: str) -> bool:
    return (sport or "") == "Run"


def _session_km(sessie: dict) -> float:
    """Haal km uit een sessie. Kijkt eerst naar expliciete velden, dan
    parseert uit naam/beschrijving, valt terug op duur × fallback pace.
    """
    for k in ("km", "afstand_km", "distance_km"):
        v = sessie.get(k)
        if v:
            return float(v)
    # Parse uit naam ("Long run 10km" of "Z2 8km")
    for src in (sessie.get("naam"), sessie.get("beschrijving")):
        if not src:
            continue
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*km", src, re.IGNORECASE)
        if m:
            return float(m.group(1).replace(",", "."))
    # Fallback: duur × pace
    dur_min = sessie.get("duur_min") or 0
    if dur_min > 0:
        return round(dur_min * 60 / _FALLBACK_PACE_SEC_PER_KM, 1)
    return 0.0


def _activity_km(a: dict) -> float:
    dist_m = a.get("distance") or 0
    return round(dist_m / 1000.0, 1)


def compute_overshoot(
    today: date,
    week_start: date,
    planned_sessions: list[dict],
    activities: list[dict],
) -> dict:
    """Bereken hoeveel km overshoot er vandaag + eerder deze week is.

    Returns:
        {
          "overshoot_km": float,   # positief = meer gedaan dan gepland
          "completed_km": float,   # runs t/m vandaag
          "planned_km_todate": float,  # runs gepland t/m vandaag
          "remaining_sessions": list[dict],  # runs ná vandaag
          "max_completed_km": float,  # langste voltooide run deze week
        }
    """
    week_end = week_start + timedelta(days=6)

    completed_runs = [
        a for a in activities
        if _is_run(a.get("type"))
        and week_start.isoformat() <= (a.get("start_date_local") or "")[:10] <= today.isoformat()
    ]
    completed_km = sum(_activity_km(a) for a in completed_runs)
    max_completed_km = max((_activity_km(a) for a in completed_runs), default=0.0)

    planned_todate = []
    remaining = []
    for s in planned_sessions:
        if not _is_run(s.get("sport")):
            continue
        d_iso = s.get("datum") or ""
        try:
            d = date.fromisoformat(d_iso)
        except (ValueError, TypeError):
            continue
        if d < week_start or d > week_end:
            continue
        if d <= today:
            planned_todate.append(s)
        else:
            remaining.append(s)

    planned_km_todate = sum(_session_km(s) for s in planned_todate)
    overshoot = completed_km - planned_km_todate

    return {
        "overshoot_km": round(overshoot, 1),
        "completed_km": round(completed_km, 1),
        "planned_km_todate": round(planned_km_todate, 1),
        "remaining_sessions": remaining,
        "max_completed_km": round(max_completed_km, 1),
    }


def _cap_session(sessie: dict, target_km: float, reason: str) -> dict:
    """Cap een sessie naar target_km. Past duur, km-waardes in beschrijving
    en naam-note aan. Minimaliseert op MIN_RUN_KM.
    """
    target_km = max(MIN_RUN_KM, round(target_km, 1))
    cur_km = _session_km(sessie)
    if cur_km <= 0 or target_km >= cur_km:
        return sessie
    ratio = target_km / cur_km
    new_dur = int(round((sessie.get("duur_min") or 0) * ratio / 5) * 5)
    new_tss = round((sessie.get("tss_geschat") or 0) * ratio, 1)

    desc = sessie.get("beschrijving") or ""
    # Vervang eerste km-getal in de beschrijving met target
    desc = re.sub(
        r"(\d+(?:[.,]\d+)?)\s*km",
        f"{target_km:g}km",
        desc,
        count=1,
        flags=re.IGNORECASE,
    )
    note = f"[Ingekort naar {target_km:g}km — {reason}]\n\n"

    return {
        **sessie,
        "duur_min": max(20, new_dur),
        "tss_geschat": new_tss,
        "km": target_km,
        "beschrijving": note + desc,
        "naam": f"[-{cur_km - target_km:.1f}km] {sessie.get('naam') or ''}",
    }


def apply(
    week_start: date,
    sessions: list[dict],
    activities: list[dict],
    today: Optional[date] = None,
    state: Optional[dict] = None,
) -> tuple[list[dict], dict]:
    """Pas volume-compensatie toe op `sessions`.

    Returns:
        (new_sessions, info_dict) waar info = compute_overshoot output +
        `"capped": [{"naam": ..., "van_km": ..., "naar_km": ...}]`.
    """
    if today is None:
        today = date.today()
    if state is None:
        state = _load_state()

    info = compute_overshoot(today, week_start, sessions, activities)
    overshoot = info["overshoot_km"]
    remaining = info["remaining_sessions"]
    max_completed = info["max_completed_km"]

    capped_log: list[dict] = []

    # Bepaal of overshoot substantieel genoeg is voor compensatie
    planned_today = info["planned_km_todate"]
    threshold_abs = MIN_OVERSHOOT_KM
    threshold_rel = planned_today * OVERSHOOT_RATIO if planned_today > 0 else 0
    do_compensate = overshoot >= max(threshold_abs, threshold_rel)

    # Injury-mode cap: geen enkele resterende run boven max_completed
    injury = state.get("injury") or {}
    injury_cap_active = bool(injury.get("return_from_injury")) and max_completed > 0

    if not do_compensate and not injury_cap_active:
        info["capped"] = []
        return sessions, info

    # Proportionele reductie over resterende runs
    remaining_km_total = sum(_session_km(s) for s in remaining)
    reduction_budget = max(0.0, overshoot) if do_compensate else 0.0

    new_sessions = []
    for s in sessions:
        if s not in remaining:
            new_sessions.append(s)
            continue
        cur_km = _session_km(s)
        target_km = cur_km

        # Stap 1: proportionele overshoot-reductie
        if reduction_budget > 0 and remaining_km_total > 0:
            share = cur_km / remaining_km_total
            target_km = cur_km - (reduction_budget * share)

        # Stap 2: injury-cap hard maximum
        if injury_cap_active and target_km > max_completed:
            target_km = max_completed

        if target_km < cur_km - 0.3:  # alleen cappen bij zinvol verschil
            reason_parts = []
            if reduction_budget > 0:
                reason_parts.append(f"overshoot {overshoot:.1f}km deze week")
            if injury_cap_active and target_km == max_completed:
                reason_parts.append(f"injury-cap {max_completed:.1f}km")
            reason = ", ".join(reason_parts) or "volume-conservatie"
            capped_s = _cap_session(s, target_km, reason)
            new_sessions.append(capped_s)
            capped_log.append({
                "naam": s.get("naam"),
                "datum": s.get("datum"),
                "van_km": cur_km,
                "naar_km": round(max(MIN_RUN_KM, target_km), 1),
            })
        else:
            new_sessions.append(s)

    info["capped"] = capped_log
    return new_sessions, info


# ── EVENT-LEVEL API (voor auto_feedback / na voltooide activity) ────────────

def _event_km(ev: dict) -> float:
    """Haal geplande km uit een event (intervals.icu formaat)."""
    for k in ("distance_km", "km"):
        if ev.get(k):
            return float(ev[k])
    # Parse uit name/description
    for src in (ev.get("name"), ev.get("description")):
        if not src:
            continue
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*km", src, re.IGNORECASE)
        if m:
            return float(m.group(1).replace(",", "."))
    # Fallback duration × pace
    dur_min = (ev.get("moving_time") or ev.get("duration") or 0) / 60
    if dur_min > 0:
        return round(dur_min * 60 / _FALLBACK_PACE_SEC_PER_KM, 1)
    return 0.0


def apply_to_events(
    events: list[dict],
    activities: list[dict],
    week_start: date,
    today: Optional[date] = None,
    state: Optional[dict] = None,
) -> list[dict]:
    """Bereken cap-updates voor run-events op basis van completed activities.

    Returns een lijst `[{"event_id": ..., "update": {name,description,duration},
    "van_km": x, "naar_km": y, "reden": str}]` die de caller via
    `api.update_event(event_id, **update)` kan toepassen.

    Gebruikt in auto_feedback na elke voltooide activity: zodra overshoot
    gedetecteerd wordt, passen we de nog-te-doen run-events aan.
    """
    if today is None:
        today = date.today()
    if state is None:
        state = _load_state()

    week_end = week_start + timedelta(days=6)

    # Normaliseer events → session-like dicts voor compute_overshoot
    event_sessions = []
    for ev in events:
        if (ev.get("type") or ev.get("sport") or "") != "Run":
            continue
        raw = ev.get("start_date_local") or ev.get("start_date") or ""
        datum = raw[:10] if raw else ""
        event_sessions.append({
            "sport": "Run",
            "datum": datum,
            "naam": ev.get("name"),
            "beschrijving": ev.get("description"),
            "duur_min": int((ev.get("moving_time") or ev.get("duration") or 0) / 60) or None,
            "km": _event_km(ev),
            "tss_geschat": ev.get("load_target"),
            "_event_id": ev.get("id"),
        })

    info = compute_overshoot(today, week_start, event_sessions, activities)
    overshoot = info["overshoot_km"]
    remaining = info["remaining_sessions"]
    max_completed = info["max_completed_km"]

    injury = state.get("injury") or {}
    injury_cap_active = bool(injury.get("return_from_injury")) and max_completed > 0

    planned_today = info["planned_km_todate"]
    threshold_abs = MIN_OVERSHOOT_KM
    threshold_rel = planned_today * OVERSHOOT_RATIO if planned_today > 0 else 0
    do_compensate = overshoot >= max(threshold_abs, threshold_rel)

    if not do_compensate and not injury_cap_active:
        return []

    remaining_km_total = sum(_session_km(s) for s in remaining)
    reduction_budget = max(0.0, overshoot) if do_compensate else 0.0

    updates: list[dict] = []
    for s in remaining:
        cur_km = _session_km(s)
        if cur_km <= 0:
            continue
        target_km = cur_km
        if reduction_budget > 0 and remaining_km_total > 0:
            target_km = cur_km - (reduction_budget * (cur_km / remaining_km_total))
        if injury_cap_active and target_km > max_completed:
            target_km = max_completed
        target_km = max(MIN_RUN_KM, round(target_km, 1))
        if target_km >= cur_km - 0.3:
            continue

        ratio = target_km / cur_km
        new_dur = max(20, int(round(((s.get("duur_min") or 0)) * ratio / 5) * 5))
        desc = s.get("beschrijving") or ""
        desc = re.sub(
            r"(\d+(?:[.,]\d+)?)\s*km",
            f"{target_km:g}km",
            desc,
            count=1,
            flags=re.IGNORECASE,
        )
        reason_parts = []
        if reduction_budget > 0:
            reason_parts.append(f"overshoot {overshoot:.1f}km deze week")
        if injury_cap_active and target_km == max_completed:
            reason_parts.append(f"injury-cap {max_completed:.1f}km")
        reden = ", ".join(reason_parts) or "volume-conservatie"
        note = f"[Auto-ingekort naar {target_km:g}km — {reden}]\n\n"

        updates.append({
            "event_id": s.get("_event_id"),
            "update": {
                "name": f"[-{cur_km - target_km:.1f}km] {s.get('naam') or ''}",
                "description": note + desc,
                "duration": new_dur * 60,  # intervals.icu wil seconden
            },
            "van_km": cur_km,
            "naar_km": target_km,
            "reden": reden,
        })

    return updates
