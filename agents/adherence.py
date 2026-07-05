"""
Adherence — meet consistentie over weken, niet per sessie of per week.

Filosofie: consistentie verslaat perfectie. Streefband is 80-90%, niet 100%.
Eén gemiste sessie in één week mag de beoordeling niet laten kantelen.
Onderscheid tussen VERPLICHT (draagt de trainingsstimulus: lange duurloop,
kwaliteitssessie, minimale basisfrequentie) en OPTIONEEL (bonus-volume:
fillers, extra runs/bikes, brick, extra kracht) — een gemiste optionele
sessie is nooit een risico.

Deze laag verandert geen veiligheidsregels (Injury Guard, ACWR, run-cap in
load_manager.enforce_consistency_rules) — die blijven hard. Dit gaat alleen
over hoe voortgang gewogen en besproken wordt.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Literal, Optional

PriorityLabel = Literal["verplicht", "optioneel"]

DAYS_NL = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"]

# Sessietypes/naam-keywords die de weekstimulus dragen — altijd verplicht.
_VERPLICHT_KEYWORDS = (
    "lange_duur", "drempel", "tempoduur", "tempoloon", "tempo_duurloop",
    "interval_10km", "marathon_tempo", "cp_intervals", "vo2max", "vo2",
    "over_unders", "over-unders", "sweetspot", "threshold", "pyramide",
)

# Herstel-/aerobe types die pas vanaf de 2e in de week optioneel worden
# (de 1e draagt de basisfrequentie, dus verplicht).
_EASY_KEYWORDS = (
    "herstelrun", "recovery", "aeroob_z2", "z2_standard", "z2_pickups",
    "z2_met_strides", "z2_progressie", "z2_fartlek", "z2_trail", "easy",
    "fatmax",
)

BAND_LOW = 80.0   # onder dit percentage: onder_streef
BAND_HIGH = 90.0  # boven dit percentage: boven_streef


def _sort_key(sessie: dict) -> int:
    dag = sessie.get("dag")
    try:
        return DAYS_NL.index(dag)
    except ValueError:
        return 99


def classify_priorities(sessions: list[dict]) -> list[dict]:
    """Tag elke sessie in een week met ``priority``. Retourneert een nieuwe
    lijst (muteert de input niet), in de oorspronkelijke volgorde.

    Regels:
    - lange duurloop / kwaliteitssessie (drempel, tempo, interval, sweetspot,
      vo2max, marathon_tempo, ...) = verplicht.
    - brick-sessies (TSS-gap fillers) = altijd optioneel.
    - van de resterende easy/herstel-sessies: de eerste in de weekvolgorde
      is verplicht (basisfrequentie), de rest is optioneel (bonus-volume).
    - onbekend/overig = optioneel (veiligste default, geen valse druk).
    """
    ordered = sorted(range(len(sessions)), key=lambda i: _sort_key(sessions[i]))

    tagged = [dict(s) for s in sessions]
    easy_seen = False
    for i in ordered:
        s = tagged[i]
        if s.get("is_brick"):
            s["priority"] = "optioneel"
            continue
        sessie_type = (s.get("type") or "").lower()
        naam = (s.get("naam") or "").lower()
        if any(k in sessie_type or k in naam for k in _VERPLICHT_KEYWORDS):
            s["priority"] = "verplicht"
        elif any(k in sessie_type or k in naam for k in _EASY_KEYWORDS):
            if not easy_seen:
                s["priority"] = "verplicht"
                easy_seen = True
            else:
                s["priority"] = "optioneel"
        else:
            s["priority"] = "optioneel"
    return tagged


def classify_priority(sessie: dict) -> PriorityLabel:
    """Classificeer één sessie los van weekcontext (voor tests/eenmalig
    gebruik). Kan geen "eerste easy run van de week"-regel toepassen —
    gebruik ``classify_priorities`` voor een volledige week.
    """
    return classify_priorities([sessie])[0]["priority"]


def record_week(week_start: date) -> Optional[dict]:
    """Sluit een week af: matcht placements tegen daadwerkelijk voltooide
    activiteiten en schrijft de required/optional-telling naar
    ``weekly_summary``.

    Retourneert de telling, of None als er geen placements zijn voor deze
    week (bv. weken van vóór de rollout van deze laag).
    """
    import history_db
    import intervals_client as api
    from shared import match_events_activities

    week_end = week_start + timedelta(days=6)
    placements = history_db.get_placements(week_start.isoformat(), week_end.isoformat())
    if not placements:
        return None
    priority_by_event = {p["event_id"]: p.get("priority") for p in placements}

    try:
        events = api.get_events(week_start, week_end)
    except Exception:
        events = []
    try:
        activities = api.get_activities(start=week_start, end=week_end)
    except Exception:
        activities = []

    matched = match_events_activities(events, activities)

    sessions_required = sessions_required_done = 0
    sessions_optional = sessions_optional_done = 0
    planned_tss = actual_tss = 0.0

    for item in matched:
        event = item.get("event") or {}
        if event.get("category") != "WORKOUT":
            continue
        event_id = str(event.get("id"))
        priority = priority_by_event.get(event_id, "optioneel")
        planned_tss += event.get("load_target") or 0
        done = bool(item.get("done"))
        if priority == "verplicht":
            sessions_required += 1
            sessions_required_done += int(done)
        else:
            sessions_optional += 1
            sessions_optional_done += int(done)
        if done and item.get("activity"):
            actual_tss += item["activity"].get("icu_training_load") or 0

    history_db.record_weekly_summary(
        week_start,
        planned_tss=planned_tss,
        actual_tss=actual_tss,
        sessions_planned=sessions_required + sessions_optional,
        sessions_done=sessions_required_done + sessions_optional_done,
        sessions_required=sessions_required,
        sessions_required_done=sessions_required_done,
        sessions_optional=sessions_optional,
        sessions_optional_done=sessions_optional_done,
    )
    return {
        "sessions_required": sessions_required,
        "sessions_required_done": sessions_required_done,
        "sessions_optional": sessions_optional,
        "sessions_optional_done": sessions_optional_done,
    }


def _rate(chunk: list[dict]) -> Optional[float]:
    planned = sum(s.get("sessions_required") or 0 for s in chunk)
    done = sum(s.get("sessions_required_done") or 0 for s in chunk)
    return (done / planned) if planned else None


def analyze(weeks: int = 4) -> dict:
    """Rolling consistentie over de laatste ``weeks`` weken.

    De band wordt uitsluitend bepaald door ``required_pct`` (de "moetjes" —
    lange duurloop, kwaliteitssessie, basisfrequentie). ``optional_pct`` is
    puur informatief: een gemiste optionele sessie mag de band nooit laten
    kantelen, ook niet gedeeltelijk via een gewogen gemiddelde — dat was een
    eerdere versie van deze functie en gaf precies het verkeerde signaal
    (100% verplicht + 0% optioneel werd "onder_streef"). Beoordeelt ook
    nooit op één week: het venster van ``weeks`` weken bepaalt de band, dus
    één slechte week kantelt niets als de rest goed zit. Geen
    "inhaal"-suggesties — die horen hier bewust niet in de output.
    """
    import history_db

    summaries = history_db.get_weekly_summaries(weeks=weeks)
    summaries = [
        s for s in summaries
        if (s.get("sessions_required") or 0) + (s.get("sessions_optional") or 0) > 0
    ]

    if not summaries:
        return {
            "required_pct": None,
            "optional_pct": None,
            "overall_pct": None,
            "trend": "onbekend",
            "band": "onbekend",
            "weeks_counted": 0,
            "message": "Nog geen consistentie-data — telt vanaf de eerstvolgende geplande week.",
        }

    req_planned = sum(s.get("sessions_required") or 0 for s in summaries)
    req_done = sum(s.get("sessions_required_done") or 0 for s in summaries)
    opt_planned = sum(s.get("sessions_optional") or 0 for s in summaries)
    opt_done = sum(s.get("sessions_optional_done") or 0 for s in summaries)

    required_pct = (req_done / req_planned * 100) if req_planned else None
    optional_pct = (opt_done / opt_planned * 100) if opt_planned else None

    # Band draait uitsluitend om required_pct; optional_pct is informatief.
    # Fallback op optional_pct alleen als er in de hele window geen enkele
    # verplichte sessie gepland stond (randgeval, zou niet moeten voorkomen).
    overall_pct = required_pct if required_pct is not None else optional_pct

    trend = "stabiel"
    if len(summaries) >= 4:
        half = len(summaries) // 2
        r_old, r_new = _rate(summaries[:half]), _rate(summaries[half:])
        if r_old is not None and r_new is not None:
            diff = r_new - r_old
            if diff > 0.05:
                trend = "stijgend"
            elif diff < -0.05:
                trend = "dalend"

    if overall_pct is None:
        band = "onbekend"
    elif overall_pct < BAND_LOW:
        band = "onder_streef"
    elif overall_pct <= BAND_HIGH:
        band = "op_streef"
    else:
        band = "boven_streef"

    message = _build_message(band, required_pct, optional_pct, len(summaries), trend)

    return {
        "required_pct": round(required_pct) if required_pct is not None else None,
        "optional_pct": round(optional_pct) if optional_pct is not None else None,
        "overall_pct": round(overall_pct) if overall_pct is not None else None,
        "trend": trend,
        "band": band,
        "weeks_counted": len(summaries),
        "message": message,
    }


def _build_message(band: str, required_pct, optional_pct, n_weeks: int, trend: str) -> str:
    req_str = f"{required_pct:.0f}%" if required_pct is not None else "?"
    opt_str = f"{optional_pct:.0f}%" if optional_pct is not None else "?"
    base = f"Consistentie ({n_weeks}wk): {req_str} verplicht, {opt_str} optioneel"
    if band == "onder_streef":
        return (
            base + f" — onder streefband (80-90%), trend {trend}. "
            "Geen paniek om één week; kijk naar het patroon."
        )
    if band == "boven_streef":
        return base + " — boven streefband. Prima, wel checken of er ruimte is voor rust/leven naast training."
    return base + " — binnen streefband (80-90%)."
