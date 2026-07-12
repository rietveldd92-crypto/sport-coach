from datetime import date

from core import availability_v2 as av2
from tests.mock_intervals import MockIntervals, install


WEEK_START = date(2026, 7, 13)


def _session(name: str, dag: str, sport: str = "Run", minutes: int = 60) -> dict:
    return {
        "naam": name,
        "type": "long_run" if "Long" in name else "run_threshold_short",
        "duur_min": minutes,
        "tss_geschat": minutes,
        "sport": sport,
        "beschrijving": "testbeschrijving",
        "dag": dag,
        "datum": (WEEK_START).isoformat(),
        "plaatsing_reden": f"{name} op {dag}: testreden.",
    }


def test_build_week_v3_preplanned_houdt_plaatsing_en_reden(monkeypatch):
    install(monkeypatch, MockIntervals())
    for weekday in range(7):
        av2.set_pattern(weekday, [("07:00", "08:00")])

    from agents import week_planner

    run_sessions = [
        _session("Interval A", "maandag", minutes=60),
        _session("Interval B", "donderdag", minutes=60),
        _session("Long run", "zondag", minutes=120),
    ]
    bike_sessions = [
        _session("Forenzen-rit", "dinsdag", "VirtualRide", minutes=100),
    ]
    events = week_planner.build_week(
        WEEK_START,
        run_sessions,
        bike_sessions,
        injury_guard={"status": "groen", "strength_allowed": False},
        load_manager={
            "current_phase": "basis_I",
            "recommended_weekly_tss": 400,
            "ctl": 50,
            "atl": 45,
            "tsb": 5,
        },
        dry_run=True,
        preplanned=True,
        planner_warnings=[{
            "tier": 2,
            "code": "available_day_left_empty",
            "dag": "woensdag",
            "sessie": None,
            "message": "woensdag blijft leeg: geraamte/urenbudget is op.",
        }],
    )

    workouts = [e for e in events if e["categorie"] == "WORKOUT"]
    assert len(workouts) == 4
    assert len({e["datum"] for e in workouts}) == 4
    assert all("Plaatsing:" in e["beschrijving"] for e in workouts)
    assert next(e for e in workouts if e["naam"] == "Long run")["tss"] == 120
