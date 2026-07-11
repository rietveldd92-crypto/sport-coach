from datetime import date, timedelta

import shared
from core import availability_v2 as av2


WEEK_START = date(2026, 7, 6)
DAYS_NL = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag",
           "zaterdag", "zondag"]


def _session(naam, duur, sport="VirtualRide", type_="endurance_ride"):
    return {
        "naam": naam,
        "duur_min": duur,
        "sport": sport,
        "type": type_,
        "tss_geschat": duur,
        "beschrijving": "test",
    }


def test_slot_solver_planner_vult_lege_beschikbare_dagen():
    from agents.week_planner import _plan_with_slot_solver

    shared.save_state({"preferences": {"tss_fillers_enabled": False}})
    for i in range(7):
        day = WEEK_START + timedelta(days=i)
        av2.set_override(day, [("07:00", "08:00")])

    sessions = [
        _session("Z2 run", 45, sport="Run", type_="z2_standard"),
        _session("Sweetspot", 60, type_="sweetspot"),
    ]
    placed, warnings = _plan_with_slot_solver(
        WEEK_START,
        sessions,
        {"recommended_weekly_tss": 0},
        {"run_intensity_allowed": True},
    )

    assert not warnings
    used_days = {s["dag"] for s in placed}
    assert used_days == set(DAYS_NL)

    fills = [s for s in placed if s.get("is_fill")]
    assert len(fills) == 5
    assert all(s["_solver"]["kind"] == "easy" for s in fills)
