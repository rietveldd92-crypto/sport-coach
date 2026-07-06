"""Beschikbaarheidsbeheer — compat-laag in minuten per dag.

Sinds Fase 1 (Planner v2) is ``core/availability_v2.py`` de bron:
tijdvensters per datum (override) of per weekdag (patroon). Deze module
blijft het minuten-dict-contract leveren voor bestaande callers:
``get_week`` geeft {date_iso: minuten|None}, afgeleid van de slots;
``set_week`` schrijft minuten als overrides (07:00 + minuten).

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
    Minuten zijn afgeleid van de v2-slots (override → patroon → legacy).
    """
    from core import availability_v2 as av2

    out: dict[str, Optional[int]] = {}
    for d in _week_dates(week_start):
        out[d.isoformat()] = av2.minutes_for_day(d)
    return out


def is_week_set(week_start: date) -> bool:
    """True als er minstens één dag van deze week is ingesteld."""
    return any(v is not None for v in get_week(week_start).values())


def set_week(week_start: date, minutes_by_date: dict[str, int]) -> None:
    """Schrijf een week aan beschikbaarheid (minuten → override-vensters).

    Per dag één venster 07:00 + minuten; 0 = expliciete rustdag-marker.
    Dagen waarvan het totaal niet wijzigt behouden hun (eventueel rijkere)
    v2-vensters.
    """
    from core import availability_v2 as av2

    for d in _week_dates(week_start):
        key = d.isoformat()
        if key in minutes_by_date:
            av2.set_override_minutes(d, clamp(int(minutes_by_date[key])))


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


def _is_easy_bike_session(session: dict) -> bool:
    """True als we deze sessie mogen rebuilden via library.endurance_ride.

    Werkt voor bike-endurance/Z1/easy/spin — intervalsessies mogen we
    niet zomaar herschalen omdat de interval-structuur dan niet klopt.
    """
    naam = (session.get("naam") or "").lower()
    sport = session.get("sport") or ""
    if sport not in ("VirtualRide", "Ride"):
        return False
    easy_keywords = ["endurance", "easy", "z1", "z2", "recovery",
                     "duurrit", "long slow", "fatmax", "spin", "herstel"]
    return any(k in naam for k in easy_keywords)


def rebuild_or_cap(session: dict, target_min: int) -> dict:
    """Probeer een sessie te herbouwen op een kortere duur.

    Voor easy bike-sessies: regen via workout_library.endurance_ride zodat
    de structuur klopt bij de nieuwe duur.
    Voor alle andere types: proportionele cap met [Ingekort] note.
    """
    current_dur = session.get("duur_min") or 0
    if current_dur <= target_min:
        return session
    if _is_easy_bike_session(session):
        try:
            from agents import workout_library as lib
            rebuilt = lib.endurance_ride(max(30, target_min))
            rebuilt["dag"] = session.get("dag")
            rebuilt["datum"] = session.get("datum")
            return rebuilt
        except Exception:
            pass  # Fall through naar proportionele cap
    # Fallback: proportionele cap
    ratio = target_min / current_dur
    new_dur = int(round(target_min / 5) * 5)
    new_tss = (session.get("tss_geschat") or 0) * ratio
    note = (
        f"[Ingekort naar {new_dur} min i.v.m. beschikbaarheid "
        f"{target_min} min]\n\n"
    )
    return {
        **session,
        "duur_min": new_dur,
        "tss_geschat": round(new_tss, 1),
        "beschrijving": note + (session.get("beschrijving") or ""),
    }


def cap_sessions_for_day(sessions: list[dict], available_min: int) -> list[dict]:
    """Cap geplande sessies voor één dag naar de beschikbare tijd.

    RUNS WORDEN NOOIT STILLETJES INGEKORT. Een lange duurloop van 2 km of
    een 30-min snipper omdat de beschikbaarheid krap staat, is precies de
    junk die het vertrouwen in het plan sloopt (atleet-feedback 2026-07-06).
    Een run die niet past blijft intact en krijgt een expliciete conflict-
    note — de atleet beslist zelf (beschikbaarheid verruimen of schrappen).

    Fiets-sessies mogen wél geschaald worden: easy rides worden herbouwd
    op de kortere duur (rebuild_or_cap), de rest proportioneel.
    """
    if available_min <= 0 or not sessions:
        return sessions
    total = sum(s.get("duur_min") or 0 for s in sessions)
    if total <= available_min:
        return sessions

    runs = [s for s in sessions if (s.get("sport") or "") == "Run"]
    bikes = [s for s in sessions if (s.get("sport") or "") != "Run"]

    out: list[dict] = []
    run_min = 0
    for s in runs:
        dur = s.get("duur_min") or 0
        run_min += dur
        if run_min > available_min:
            s = {
                **s,
                "beschrijving": (
                    f"[PAST NIET IN BESCHIKBAARHEID ({available_min} min "
                    f"opgegeven) — bewust NIET ingekort. Verruim je "
                    f"beschikbaarheid of schrap de sessie zelf.]\n\n"
                    + (s.get("beschrijving") or "")
                ),
            }
        out.append(s)

    bike_budget = max(0, available_min - run_min)
    bike_total = sum(s.get("duur_min") or 0 for s in bikes)
    if bikes and bike_total > bike_budget:
        ratio = bike_budget / bike_total if bike_total else 0
        for s in bikes:
            target = int(round((s.get("duur_min") or 0) * ratio / 5) * 5)
            if target < 30:
                continue  # te kort om zinvol te zijn — liever weg dan junk
            out.append(rebuild_or_cap(s, target))
    else:
        out.extend(bikes)
    return out


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
