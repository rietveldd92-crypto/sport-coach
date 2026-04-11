"""Gedeelde helpers — voorkomt duplicatie tussen app.py, coach.py, auto_feedback.py etc."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

STATE_PATH = Path(__file__).parent / "state.json"


def load_state(state_path: Path = STATE_PATH) -> dict:
    """Laad state.json. Geeft leeg dict bij ontbreken/fout."""
    try:
        with open(state_path) as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state: dict, state_path: Path = STATE_PATH) -> None:
    """Schrijf state.json."""
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


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

    Returns lijst van {event, activity, done} dicts, gesorteerd op datum.
    """
    result = []
    for event in events:
        if event.get("category") != "WORKOUT":
            continue
        e_date = event.get("start_date_local", "")[:10]
        e_type = event.get("type", "")
        matched = None
        for act in activities:
            a_date = act.get("start_date_local", "")[:10]
            a_type = act.get("type", "")
            if a_date == e_date and types_match(e_type, a_type):
                matched = act
                break
        result.append({"event": event, "activity": matched, "done": matched is not None})
    result.sort(key=lambda x: x["event"].get("start_date_local", ""))
    return result
