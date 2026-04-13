"""Beschikbaarheidsbeheer — per dag hoeveel tijd is er voor training.

Opslaan in state.json onder `"availability": {"YYYY-MM-DD": minutes}`.
Stap van 30 min, max 240 (4 uur) per dag. Waarde 0 = rustdag.

De planner gebruikt 0-minuten-dagen als `skip_run_days` en waarschuwt als
het weektotaal lager is dan nodig voor het TSS-doel.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

STATE_PATH = Path(__file__).parent.parent / "state.json"

MIN_STEP = 30
MAX_MINUTES = 240  # 4 uur max

DAYS_NL = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"]

# Ruwe TSS/uur ratio voor budget-check. Gemiddelde week is ~55 TSS/uur
# (mix van easy en hard). Strak genoeg om tekorten te detecteren zonder
# vals alarm bij een pure-kwaliteitsweek.
TSS_PER_HOUR = 55.0


def _load_state() -> dict:
    with open(STATE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save_state(state: dict) -> None:
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def _week_dates(week_start: date) -> list[date]:
    return [week_start + timedelta(days=i) for i in range(7)]


def clamp(minutes: int) -> int:
    """Rond naar dichtstbijzijnde stap en clampen naar [0, MAX_MINUTES]."""
    if minutes < 0:
        return 0
    m = min(MAX_MINUTES, minutes)
    return int(round(m / MIN_STEP) * MIN_STEP)


def get_week(week_start: date) -> dict[str, Optional[int]]:
    """Haal beschikbaarheid op voor 7 dagen vanaf week_start.

    Returnt dict {date_iso: minutes|None}. None = nog niet ingesteld.
    """
    state = _load_state()
    stored = state.get("availability", {}) or {}
    out: dict[str, Optional[int]] = {}
    for d in _week_dates(week_start):
        key = d.isoformat()
        out[key] = stored.get(key)
    return out


def is_week_set(week_start: date) -> bool:
    """True als er minstens één dag van deze week is ingesteld."""
    return any(v is not None for v in get_week(week_start).values())


def set_week(week_start: date, minutes_by_date: dict[str, int]) -> None:
    """Schrijf een week aan beschikbaarheid in één transactie."""
    state = _load_state()
    avail = state.get("availability") or {}
    for d in _week_dates(week_start):
        key = d.isoformat()
        if key in minutes_by_date:
            avail[key] = clamp(int(minutes_by_date[key]))
    state["availability"] = avail
    _save_state(state)


def copy_from_prev_week(week_start: date) -> dict[str, int]:
    """Als de week nog niks heeft ingesteld, kopieer de waardes van de
    vorige week naar deze week en schrijf weg. Returnt het resultaat.

    Als de vorige week óók leeg is, defaulten we naar alle dagen 60 min.
    """
    if is_week_set(week_start):
        return {k: v for k, v in get_week(week_start).items() if v is not None}

    prev_start = week_start - timedelta(days=7)
    prev = get_week(prev_start)
    has_prev = any(v is not None for v in prev.values())

    new_vals: dict[str, int] = {}
    for i, d in enumerate(_week_dates(week_start)):
        prev_key = (prev_start + timedelta(days=i)).isoformat()
        prev_val = prev.get(prev_key)
        new_vals[d.isoformat()] = clamp(prev_val if prev_val is not None else 60)

    set_week(week_start, new_vals)
    return new_vals


def week_total_minutes(week_start: date) -> int:
    """Som van alle beschikbaarheid in de week (None → 0)."""
    return sum(v or 0 for v in get_week(week_start).values())


def get_rest_day_names(week_start: date) -> list[str]:
    """NL-dagnamen met 0 minuten beschikbaarheid — voor skip_run_days."""
    out: list[str] = []
    for i, d in enumerate(_week_dates(week_start)):
        val = get_week(week_start)[d.isoformat()]
        if val == 0:
            out.append(DAYS_NL[i])
    return out


def cap_sessions_for_day(sessions: list[dict], available_min: int) -> list[dict]:
    """Cap geplande sessies voor één dag naar de beschikbare tijd.

    Als de som van duur_min > available_min, schalen we elke sessie
    proportioneel terug en herberekenen we TSS via dezelfde ratio.
    Prepends een NOTE aan de beschrijving zodat de atleet weet dat er
    ingekort is. Laat de workout-naam intact.

    Geen ondergrens per sessie — bij extreme caps kan dit triviaal kort
    worden. Dat is een signaal naar de gebruiker dat de opgegeven tijd
    te krap is voor wat de periodizer vraagt.
    """
    if available_min <= 0 or not sessions:
        return sessions
    total = sum(s.get("duur_min") or 0 for s in sessions)
    if total <= available_min:
        return sessions
    ratio = available_min / total
    capped: list[dict] = []
    for s in sessions:
        new_dur = int(round((s.get("duur_min") or 0) * ratio / 5) * 5)  # 5-min stappen
        new_tss = (s.get("tss_geschat") or 0) * ratio
        note = (
            f"[Ingekort naar {new_dur} min i.v.m. beschikbaarheid "
            f"{available_min} min totaal deze dag]\n\n"
        )
        capped.append({
            **s,
            "duur_min": new_dur,
            "tss_geschat": round(new_tss, 1),
            "beschrijving": note + (s.get("beschrijving") or ""),
        })
    return capped


def check_budget(week_start: date, weekly_tss_target: int) -> dict:
    """Check of beschikbare tijd het weekdoel kan dragen.

    Returns:
        {
          "ok": bool,
          "available_min": int,
          "needed_min": int,
          "shortfall_min": int,  # >0 als tekort
        }
    """
    avail = week_total_minutes(week_start)
    needed = int(round((weekly_tss_target / TSS_PER_HOUR) * 60))
    shortfall = max(0, needed - avail)
    return {
        "ok": shortfall == 0,
        "available_min": avail,
        "needed_min": needed,
        "shortfall_min": shortfall,
    }
