from __future__ import annotations

from datetime import date

from agents import volume_compensation


def test_return_from_injury_does_not_cap_remaining_longrun_without_overshoot():
    week_start = date(2026, 7, 6)
    today = date(2026, 7, 7)
    sessions = [
        {
            "sport": "Run",
            "datum": "2026-07-06",
            "naam": "Z2 duurloop",
            "beschrijving": "9.2km easy",
            "duur_min": 50,
            "km": 9.2,
            "tss_geschat": 50,
        },
        {
            "sport": "Run",
            "datum": "2026-07-12",
            "naam": "Lange duurloop",
            "beschrijving": "25km Z2",
            "duur_min": 148,
            "km": 25.0,
            "tss_geschat": 115,
        },
    ]
    activities = [
        {
            "type": "Run",
            "start_date_local": "2026-07-06T07:00:00",
            "distance": 9200,
        }
    ]
    stale_injury_state = {
        "injury": {
            "return_from_injury": True,
            "active_signals": [],
            "days_symptom_free": 121,
        }
    }

    new_sessions, info = volume_compensation.apply(
        week_start,
        sessions,
        activities,
        today=today,
        state=stale_injury_state,
    )

    assert info["overshoot_km"] == 0
    assert info["capped"] == []
    assert new_sessions[1]["km"] == 25.0


def test_return_from_injury_does_not_cap_event_updates_without_overshoot():
    week_start = date(2026, 7, 6)
    today = date(2026, 7, 7)
    events = [
        {
            "id": "done",
            "type": "Run",
            "start_date_local": "2026-07-06T07:00:00",
            "name": "Z2 duurloop",
            "description": "9.2km easy",
            "duration": 50 * 60,
            "distance_km": 9.2,
        },
        {
            "id": "long",
            "type": "Run",
            "start_date_local": "2026-07-12T08:00:00",
            "name": "Lange duurloop",
            "description": "25km Z2",
            "duration": 148 * 60,
            "distance_km": 25.0,
        },
    ]
    activities = [
        {
            "type": "Run",
            "start_date_local": "2026-07-06T07:00:00",
            "distance": 9200,
        }
    ]
    stale_injury_state = {"injury": {"return_from_injury": True}}

    updates = volume_compensation.apply_to_events(
        events,
        activities,
        week_start,
        today=today,
        state=stale_injury_state,
    )

    assert updates == []


def test_interval_rep_km_in_description_does_not_count_as_total_session_km():
    week_start = date(2026, 7, 6)
    today = date(2026, 7, 7)
    threshold = {
        "sport": "Run",
        "datum": "2026-07-07",
        "naam": "Drempel - 5x1000m @ 4:20/km",
        "beschrijving": """
Warmup
- 15m easy

Main Set
5x
- 1km 4:20/km Pace
- 2m rustig

Cooldown
- 10m easy
""",
        "duur_min": 62,
    }
    longrun = {
        "sport": "Run",
        "datum": "2026-07-12",
        "naam": "Lange duurloop negative split - 25km",
        "beschrijving": "Rustig opbouwen",
        "duur_min": 148,
    }
    activities = [
        {
            "type": "Run",
            "start_date_local": "2026-07-06T07:00:00",
            "distance": 9200,
        }
    ]

    assert volume_compensation._session_km(threshold) == 11.3

    new_sessions, info = volume_compensation.apply(
        week_start,
        [threshold, longrun],
        activities,
        today=today,
    )

    assert info["overshoot_km"] == -2.1
    assert info["capped"] == []
    assert new_sessions[1]["naam"] == "Lange duurloop negative split - 25km"
