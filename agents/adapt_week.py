"""adapt_week — pure function die een week bijstuurt o.b.v. deviations.

Gegeven de geplande events voor deze week en een lijst Deviation, produceert
adapt_week een AdaptResult met modifications. GEEN I/O — de caller schrijft
ze naar intervals.icu en het adjustments_log.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Optional

from .models import AdaptResult, Deviation, Modification
from .session_classifier import is_sacred

# Constants
MAX_EXTRAS_BEFORE_WARN = 3
NEXT_48H_TSS_CUT_FRACTION = 0.5  # replaced_harder → halveer next 48h hard session TSS
LONGER_TSS_CUT_FRACTION = 0.25  # longer → 25% cut next dag als >50 TSS
HARD_TSS_THRESHOLD = 50  # boven dit = "hard"


def _event_date(ev: dict[str, Any]) -> Optional[date]:
    raw = ev.get("start_date_local") or ev.get("start_date") or ""
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "")).date()
    except ValueError:
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            return None


def _event_tss(ev: dict[str, Any]) -> float:
    return float(ev.get("load_target") or 0)


def _find_event(events: list[dict[str, Any]], event_id: Optional[str]) -> Optional[dict]:
    if not event_id:
        return None
    for e in events:
        if str(e.get("id")) == str(event_id):
            return e
    return None


def _find_long_run_day(events: list[dict[str, Any]]) -> Optional[date]:
    for e in events:
        if is_sacred(e) and (e.get("type") == "Run") and "long" in (e.get("name") or "").lower():
            return _event_date(e)
    # fallback: elke sacred run > 80 min
    for e in events:
        if e.get("type") == "Run" and is_sacred(e):
            return _event_date(e)
    return None


def _slot_is_rest(events: list[dict[str, Any]], day: date) -> bool:
    """Is er op deze dag GEEN workout gepland?"""
    for e in events:
        if e.get("category") != "WORKOUT":
            continue
        if _event_date(e) == day:
            return False
    return True


def _slot_is_soft(events: list[dict[str, Any]], day: date) -> bool:
    """Is er op deze dag alleen een soft workout gepland?"""
    workouts = [e for e in events if e.get("category") == "WORKOUT" and _event_date(e) == day]
    if not workouts:
        return True  # rustdag telt als plaatsbaar
    return all(not is_sacred(e) for e in workouts)


def _find_reschedule_slot(
    events: list[dict[str, Any]],
    missed_event: dict[str, Any],
    today: date,
) -> Optional[date]:
    """Zoek een geschikte dag deze week om missed_event in te plannen.

    Regels:
    - Moet vandaag of later zijn
    - Moet binnen deze kalenderweek vallen (maandag-zondag van today)
    - Niet dag-voor-long-run
    - Bij voorkeur een rustdag; anders een dag met alleen soft
    - Niet op een dag met al een sacred session (geen double-hard)
    """
    monday = today - timedelta(days=today.weekday())
    week_end = monday + timedelta(days=6)
    long_run = _find_long_run_day(events)

    # Eerst rustdagen proberen, dan soft-dagen
    candidates_rest: list[date] = []
    candidates_soft: list[date] = []
    d = max(today, monday)
    while d <= week_end:
        if long_run and d == long_run - timedelta(days=1):
            d += timedelta(days=1)
            continue
        # Niet op long run dag zelf
        if long_run and d == long_run:
            d += timedelta(days=1)
            continue
        if _slot_is_rest(events, d):
            candidates_rest.append(d)
        elif _slot_is_soft(events, d):
            candidates_soft.append(d)
        d += timedelta(days=1)

    if candidates_rest:
        return candidates_rest[0]
    if candidates_soft:
        return candidates_soft[0]
    return None


def _next_event_within(
    events: list[dict[str, Any]],
    start_day: date,
    hours: int,
) -> Optional[dict[str, Any]]:
    end_day = start_day + timedelta(hours=hours)
    candidates = []
    for e in events:
        if e.get("category") != "WORKOUT":
            continue
        d = _event_date(e)
        if d and start_day < d <= end_day.date() if hasattr(end_day, "date") else start_day < d <= (start_day + timedelta(days=hours // 24)):
            candidates.append((d, e))
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1] if candidates else None


def _next_hard_event_within_48h(
    events: list[dict[str, Any]],
    from_day: date,
) -> Optional[dict[str, Any]]:
    end_day = from_day + timedelta(days=2)
    cand = []
    for e in events:
        if e.get("category") != "WORKOUT":
            continue
        d = _event_date(e)
        if d and from_day < d <= end_day and _event_tss(e) >= HARD_TSS_THRESHOLD:
            cand.append((d, e))
    cand.sort(key=lambda x: x[0])
    return cand[0][1] if cand else None


def _next_day_event(
    events: list[dict[str, Any]],
    from_day: date,
) -> Optional[dict[str, Any]]:
    target = from_day + timedelta(days=1)
    for e in events:
        if e.get("category") != "WORKOUT":
            continue
        if _event_date(e) == target:
            return e
    return None


def _downgrade_to_easy_spin(event: dict[str, Any]) -> dict[str, Any]:
    """Vervang een hard event door een 60min easy spin (bike) of herstelloop (run)."""
    out = dict(event)
    is_run = event.get("type") == "Run"
    if is_run:
        out["name"] = "Herstelloop 30 min Z1"
        out["load_target"] = 25
        out["duration"] = 30 * 60
    else:
        out["name"] = "Easy spin 60 min Z2"
        out["load_target"] = 40
        out["duration"] = 60 * 60
    out["description"] = "Auto-downgrade na zwaardere vervangende sessie."
    return out


def _cut_tss(event: dict[str, Any], fraction: float) -> dict[str, Any]:
    out = dict(event)
    old = _event_tss(event)
    new = max(10.0, old * (1.0 - fraction))
    out["load_target"] = round(new)
    return out


def adapt_week(
    week_events: list[dict[str, Any]],
    deviations: list[Deviation],
    state: dict[str, Any],
    today: Optional[date] = None,
) -> AdaptResult:
    """Pure planningsaanpassing o.b.v. deviations.

    Wijzigt week_events NIET in-place; produceert Modification-entries
    die de caller kan toepassen via intervals.icu client.
    """
    today = today or date.today()
    modifications: list[Modification] = []
    new_events: list[dict[str, Any]] = []
    narrative_parts: list[str] = []
    extras_count = 0
    dropped_sacred = 0
    rescheduled_sacred = 0

    for dev in deviations:
        if dev.type == "extra":
            extras_count += 1
            continue

        if dev.type == "skipped":
            planned = _find_event(week_events, dev.planned_event_id)
            if not planned:
                continue
            if dev.sacred:
                slot = _find_reschedule_slot(week_events, planned, today)
                if slot is None:
                    dropped_sacred += 1
                    narrative_parts.append(
                        f"Geen plek meer voor gemiste '{planned.get('name', '?')}' — valt weg."
                    )
                    continue
                # Maak een nieuw event op de slot-dag
                new_ev = dict(planned)
                new_ev["start_date_local"] = f"{slot.isoformat()}T09:00:00"
                new_ev.pop("id", None)
                new_events.append(new_ev)
                modifications.append(
                    Modification(
                        event_id=str(planned.get("id", "")),
                        action="create",
                        before={},
                        after=new_ev,
                        tss_delta=int(_event_tss(planned)),
                        reason=f"Sacred skipped → verplaatst naar {slot.isoformat()}",
                    )
                )
                rescheduled_sacred += 1
                narrative_parts.append(
                    f"Gemiste sacred '{planned.get('name', '?')}' verplaatst naar {slot.isoformat()}."
                )
            else:
                narrative_parts.append(
                    f"Soft sessie '{planned.get('name', '?')}' overgeslagen — geabsorbeerd."
                )

        elif dev.type == "replaced_harder":
            nxt = _next_hard_event_within_48h(week_events, today)
            if nxt:
                downgraded = _downgrade_to_easy_spin(nxt)
                modifications.append(
                    Modification(
                        event_id=str(nxt.get("id", "")),
                        action="modify",
                        before=dict(nxt),
                        after=downgraded,
                        tss_delta=int(_event_tss(downgraded) - _event_tss(nxt)),
                        reason="Zwaardere vervanging → next hard sessie terug naar easy",
                    )
                )
                narrative_parts.append(
                    f"Je ging {int(dev.tss_actual - dev.tss_planned)} TSS zwaarder — "
                    f"'{nxt.get('name', '?')}' wordt easy spin."
                )

        elif dev.type == "replaced_easier":
            if dev.sacred:
                planned = _find_event(week_events, dev.planned_event_id)
                if planned:
                    slot = _find_reschedule_slot(week_events, planned, today)
                    if slot is not None:
                        new_ev = dict(planned)
                        new_ev["start_date_local"] = f"{slot.isoformat()}T09:00:00"
                        new_ev.pop("id", None)
                        new_events.append(new_ev)
                        modifications.append(
                            Modification(
                                event_id=str(planned.get("id", "")),
                                action="create",
                                before={},
                                after=new_ev,
                                tss_delta=int(_event_tss(planned)),
                                reason=f"Sacred lichter vervangen → herplanning {slot.isoformat()}",
                            )
                        )
                        rescheduled_sacred += 1
                        narrative_parts.append(
                            f"Sacred '{planned.get('name', '?')}' werd lichter uitgevoerd — "
                            f"opnieuw ingepland op {slot.isoformat()}."
                        )
                    else:
                        dropped_sacred += 1
                        narrative_parts.append(
                            f"Kon '{planned.get('name', '?')}' niet herplannen — valt weg."
                        )

        elif dev.type == "longer":
            planned_date = None
            if dev.planned_date:
                try:
                    planned_date = date.fromisoformat(dev.planned_date)
                except ValueError:
                    pass
            ref_day = planned_date or today
            nxt = _next_day_event(week_events, ref_day)
            if nxt and _event_tss(nxt) > HARD_TSS_THRESHOLD:
                cut = _cut_tss(nxt, LONGER_TSS_CUT_FRACTION)
                modifications.append(
                    Modification(
                        event_id=str(nxt.get("id", "")),
                        action="modify",
                        before=dict(nxt),
                        after=cut,
                        tss_delta=int(_event_tss(cut) - _event_tss(nxt)),
                        reason="Langer dan gepland → volgende dag 25% lichter",
                    )
                )
                narrative_parts.append(
                    f"Je liep langer dan gepland — '{nxt.get('name', '?')}' morgen -25% TSS."
                )

    # Extras → junk-miles waarschuwing
    if extras_count > MAX_EXTRAS_BEFORE_WARN:
        narrative_parts.append(
            f"Je hebt {extras_count} ongeplande sessies erbij — pas op voor junk miles."
        )
    elif extras_count > 0:
        narrative_parts.append(f"{extras_count} extra sessie(s) meegeteld in weekbudget.")

    # Bouw narrative + invariant
    if not narrative_parts:
        narrative = "Week verloopt binnen tolerantie — geen wijzigingen nodig."
    else:
        narrative = " ".join(narrative_parts)

    ctl = float(state.get("load", {}).get("ctl_estimate", 0))
    if rescheduled_sacred > 0 or dropped_sacred == 0:
        invariant = f"Wekelijkse CTL-trajectory blijft op koers (CTL {ctl:.1f})."
    else:
        invariant = f"CTL-trajectory licht onder druk ({dropped_sacred} sacred weggevallen)."

    return AdaptResult(
        new_events=new_events,
        modifications=modifications,
        narrative=narrative,
        invariant=invariant,
    )
