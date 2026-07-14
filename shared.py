"""Gedeelde helpers — voorkomt duplicatie tussen app.py, coach.py, auto_feedback.py etc.

Sinds Fase 0 (UPGRADE_PLAN §8) leven load_state/save_state op SQLite
(history.db, tabellen athlete_state + availability_override) in plaats van
state.json. Het dict-formaat dat callers zien is exact gelijk gebleven:
{"injury": {...}, "load": {...}, ..., "availability": {"YYYY-MM-DD": minuten}}.

state.json blijft als read-only fallback bestaan totdat
scripts/migrate_state_json.py is gedraaid.
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path

STATE_PATH = Path(__file__).parent / "state.json"

_log = logging.getLogger(__name__)


def _load_state_json(state_path: Path) -> dict:
    """Legacy: laad state.json. Geeft leeg dict bij ontbreken/fout."""
    try:
        with open(state_path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state_json(state: dict, state_path: Path) -> None:
    """Legacy: schrijf state.json."""
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def load_state(state_path: Path | None = None) -> dict:
    """Laad de athlete state.

    Leest uit SQLite (athlete_state + availability_override) en geeft
    hetzelfde dict-formaat terug als het oude state.json. Zolang de DB
    nog leeg is (migratiescript niet gedraaid), valt dit terug op
    state.json zodat niets breekt.

    Een expliciet afwijkend ``state_path`` (tests) blijft puur op JSON
    werken.
    """
    if state_path is not None and state_path != STATE_PATH:
        return _load_state_json(state_path)

    try:
        import history_db

        if not history_db.athlete_state_is_empty():
            state = history_db.get_athlete_state()
            availability = history_db.get_availability_minutes()
            if availability or "availability" in state:
                state["availability"] = availability
            return state
        _log.info(
            "athlete_state is leeg — fallback naar state.json. "
            "Draai scripts/migrate_state_json.py om naar SQLite te migreren."
        )
    except Exception:
        _log.exception("Kon athlete_state niet uit history.db lezen — fallback naar state.json")
    return _load_state_json(STATE_PATH)


def save_state(state: dict, state_path: Path | None = None) -> None:
    """Schrijf de athlete state naar SQLite (whole-state overwrite,
    net als het oude state.json). ``availability`` gaat naar
    availability_override; alle andere top-level keys naar athlete_state.

    Een expliciet afwijkend ``state_path`` (tests) blijft puur op JSON
    werken.
    """
    if state_path is not None and state_path != STATE_PATH:
        _save_state_json(state, state_path)
        return

    import history_db

    state = dict(state)  # caller's dict niet muteren
    availability = state.pop("availability", None)
    history_db.replace_athlete_state(state)
    history_db.replace_availability_minutes(availability or {})


def types_match(event_type: str, activity_type: str) -> bool:
    """Match intervals.icu event-type met activity-type (Run ↔ Run, Ride ↔ VirtualRide)."""
    run_types = {"Run"}
    bike_types = {"Ride", "VirtualRide"}
    if event_type in run_types and activity_type in run_types:
        return True
    if event_type in bike_types and activity_type in bike_types:
        return True
    return event_type == activity_type


def match_events_activities(events: list, activities: list) -> list:
    """Koppel events (gepland) aan activities (voltooid).

    Toont WORKOUT events + NOTE events (rehab, kracht).
    Activiteiten zonder matching event worden als "ongepland voltooid" toegevoegd.

    Returns lijst van {event, activity, done} dicts, gesorteerd op datum.
    """
    result = []
    matched_activity_ids = set()
    workouts = [e for e in events if e.get("category") == "WORKOUT"]

    def candidates(event: dict) -> list:
        e_date = event.get("start_date_local", "")[:10]
        e_type = event.get("type", "")
        return [
            act for act in activities
            if act.get("id") not in matched_activity_ids
            and act.get("start_date_local", "")[:10] == e_date
            and types_match(e_type, act.get("type", ""))
        ]

    # 1. Match WORKOUT events met activities (elke activity max 1x matchen).
    #    Twee rondes: eerst events waarvan de naam exact op een activiteit valt.
    #    Op een dubbele loopdag (easy + drempel) zijn datum en type gelijk, dus
    #    zonder naam-ronde pikt het eerste event de verkeerde activiteit in en
    #    krijgt de drempelsessie er geen — met een vervuild dossier tot gevolg.
    matches: dict[str, dict] = {}
    for event in workouts:
        name = (event.get("name") or "").strip().lower()
        if not name:
            continue
        act = next((a for a in candidates(event)
                    if (a.get("name") or "").strip().lower() == name), None)
        if act:
            matches[str(event.get("id"))] = act
            matched_activity_ids.add(act.get("id"))

    for event in workouts:
        matched = matches.get(str(event.get("id")))
        if matched is None:
            matched = next(iter(candidates(event)), None)
            if matched:
                matched_activity_ids.add(matched.get("id"))
        result.append({"event": event, "activity": matched, "done": matched is not None})

    # 2. NOTE events (rehab, kracht) — toon als context
    for event in events:
        if event.get("category") != "NOTE":
            continue
        result.append({
            "event": event,
            "activity": None,
            "done": False,
            "is_note": True,
        })

    # 3. Activiteiten zonder matching event (ongepland voltooid)
    for act in activities:
        if act.get("id") in matched_activity_ids:
            continue
        a_date = act.get("start_date_local", "")[:10]
        a_type = act.get("type") or ""
        a_name = act.get("name") or "Ongeplande training"
        if not a_type:
            continue
        # Maak een pseudo-event zodat de rest van de app 'm kan renderen
        pseudo_event = {
            "id": f"unplanned_{act.get('id')}",
            "name": a_name,
            "type": a_type,
            "start_date_local": act.get("start_date_local", ""),
            "category": "WORKOUT",
            "load_target": act.get("icu_training_load"),
            "_unplanned": True,
        }
        result.append({
            "event": pseudo_event,
            "activity": act,
            "done": True,
            "_unplanned": True,
        })

    result.sort(key=lambda x: x["event"].get("start_date_local", ""))
    return result
