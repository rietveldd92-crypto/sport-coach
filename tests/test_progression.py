"""Tests voor load_manager._apply_weekly_progression.

Dekt regressies:
- consecutive_build_weeks mag niet meer per analyze()-call incrementeren
- step-progression (threshold/sweetspot/over_unders/cp) moet 1x/wk bumpen
- deload reset counter en vermijdt bump van intensiteit
"""
from datetime import date

from agents.load_manager import _apply_weekly_progression


def _fresh_state(consecutive: int = 0, last_bump: str | None = None,
                 last_deload: str = "2026-04-06",
                 threshold_step: int = 1, sweetspot_step: int = 1,
                 over_unders_step: int = 1, cp_step: int = 0) -> dict:
    return {
        "build_deload": {
            "consecutive_build_weeks": consecutive,
            "last_deload_week": last_deload,
            "is_deload_week": False,
        },
        "progression": {
            "threshold_step": threshold_step,
            "sweetspot_step": sweetspot_step,
            "over_unders_step": over_unders_step,
            "cp_step": cp_step,
            "z2_run_variety_index": 0,
            "long_run_variety_index": 0,
            "endurance_spin_min": 60,
            "long_ride_min": 80,
            "last_bump_week": last_bump,
        },
    }


def test_counter_bumps_once_per_week():
    state = _fresh_state(consecutive=1, last_bump="2026-04-13")
    monday = date(2026, 4, 20)

    # Eerste call in nieuwe week → +1
    _apply_weekly_progression(state, is_deload_week=False, today=monday)
    assert state["build_deload"]["consecutive_build_weeks"] == 2
    assert state["progression"]["last_bump_week"] == "2026-04-20"

    # Tweede call zelfde week → GEEN bump (idempotent)
    _apply_weekly_progression(state, is_deload_week=False, today=monday)
    assert state["build_deload"]["consecutive_build_weeks"] == 2

    # Derde call (simuleer cache-clear / replan) → ook geen bump
    _apply_weekly_progression(state, is_deload_week=False, today=monday)
    assert state["build_deload"]["consecutive_build_weeks"] == 2


def test_step_progression_bumps_once_per_week():
    state = _fresh_state(last_bump="2026-04-13",
                         threshold_step=2, sweetspot_step=3,
                         over_unders_step=1, cp_step=0)
    monday = date(2026, 4, 20)

    _apply_weekly_progression(state, is_deload_week=False, today=monday)
    assert state["progression"]["threshold_step"] == 3
    assert state["progression"]["sweetspot_step"] == 4
    assert state["progression"]["over_unders_step"] == 2
    assert state["progression"]["cp_step"] == 1

    # Zelfde week opnieuw → blijft staan
    _apply_weekly_progression(state, is_deload_week=False, today=monday)
    assert state["progression"]["threshold_step"] == 3
    assert state["progression"]["cp_step"] == 1


def test_variety_index_bumps_once_per_week():
    state = _fresh_state(last_bump="2026-04-13")
    monday = date(2026, 4, 20)

    _apply_weekly_progression(state, is_deload_week=False, today=monday)
    assert state["progression"]["z2_run_variety_index"] == 1
    assert state["progression"]["long_run_variety_index"] == 1

    # Zelfde week opnieuw → geen dubbele rotatie
    _apply_weekly_progression(state, is_deload_week=False, today=monday)
    assert state["progression"]["z2_run_variety_index"] == 1


def test_deload_resets_counter_no_step_bump():
    state = _fresh_state(consecutive=3, last_bump="2026-04-13",
                         threshold_step=5)
    monday = date(2026, 4, 20)

    _apply_weekly_progression(state, is_deload_week=True, today=monday)

    assert state["build_deload"]["consecutive_build_weeks"] == 0
    assert state["build_deload"]["is_deload_week"] is True
    assert state["build_deload"]["last_deload_week"] == "2026-04-20"
    # Step blijft gelijk — deload halveert in bike_coach zelf (t_step - 2)
    assert state["progression"]["threshold_step"] == 5


def test_step_progression_caps_at_max():
    state = _fresh_state(last_bump="2026-04-13",
                         threshold_step=10, sweetspot_step=8,
                         over_unders_step=6, cp_step=5)
    monday = date(2026, 4, 20)

    _apply_weekly_progression(state, is_deload_week=False, today=monday)

    assert state["progression"]["threshold_step"] == 10
    assert state["progression"]["sweetspot_step"] == 8
    assert state["progression"]["over_unders_step"] == 6
    assert state["progression"]["cp_step"] == 5


def test_volume_bump_every_second_week():
    state = _fresh_state(consecutive=1, last_bump="2026-04-13")  # → wordt 2
    monday = date(2026, 4, 20)

    _apply_weekly_progression(state, is_deload_week=False, today=monday)

    # consecutive=2 na bump → 2%2==0 → volume bumpt
    assert state["progression"]["endurance_spin_min"] == 65
    assert state["progression"]["long_ride_min"] == 85


def test_volume_skips_on_odd_week():
    state = _fresh_state(consecutive=0, last_bump="2026-04-13")  # → wordt 1
    monday = date(2026, 4, 20)

    _apply_weekly_progression(state, is_deload_week=False, today=monday)

    # consecutive=1 → 1%2!=0 → volume blijft
    assert state["progression"]["endurance_spin_min"] == 60
    assert state["progression"]["long_ride_min"] == 80


def test_replan_in_existing_week_does_not_bump_counter():
    # Scenario dat de user-state corrumpeerde: consecutive_build_weeks
    # liep naar 29 op doordat analyse() meerdere keren per week gecalled werd.
    state = _fresh_state(consecutive=1, last_bump="2026-04-20")
    monday = date(2026, 4, 20)

    for _ in range(10):
        _apply_weekly_progression(state, is_deload_week=False, today=monday)

    assert state["build_deload"]["consecutive_build_weeks"] == 1


def test_new_week_after_deload_resumes_counter():
    state = _fresh_state(consecutive=0, last_bump="2026-04-13",
                         last_deload="2026-04-13")
    state["build_deload"]["is_deload_week"] = True

    _apply_weekly_progression(state, is_deload_week=False,
                              today=date(2026, 4, 20))

    assert state["build_deload"]["consecutive_build_weeks"] == 1
    assert state["build_deload"]["is_deload_week"] is False


def test_first_ever_run_no_last_bump():
    state = _fresh_state(consecutive=0, last_bump=None)
    monday = date(2026, 4, 20)

    _apply_weekly_progression(state, is_deload_week=False, today=monday)

    # last_bump=None → is_new_week → bump
    assert state["build_deload"]["consecutive_build_weeks"] == 1
    assert state["progression"]["last_bump_week"] == "2026-04-20"
    assert state["progression"]["threshold_step"] == 2
