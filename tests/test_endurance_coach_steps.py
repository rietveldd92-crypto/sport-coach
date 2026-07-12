"""Regressietests voor intervals.icu step-syntax in run-templates."""
from __future__ import annotations

import re

from agents import workout_library


_PACE_STEP_OK = re.compile(
    r"^- \d+(?:\.\d+)?(?:km|m|s) \d:\d{2}/km Pace\b",
    re.MULTILINE,
)


def test_threshold_library_steps_are_intervals_icu_parseable():
    library = workout_library.run_quality_library(threshold_sec=255)
    for category in ("threshold", "speed", "vo2max", "marathon"):
        for rung in library[category]:
            for workout in rung:
                desc = workout["beschrijving"]
                assert _PACE_STEP_OK.search(desc), (
                    f"{category}/{workout['naam']}: geen parseable pace-step"
                )
                assert not re.search(r"^- .*@", desc, re.MULTILINE)


def test_threshold_library_schaalt_met_drempelpace():
    slow = workout_library.pick_run_quality(
        step=3, variety_index=0, category="threshold", threshold_sec=255)
    fast = workout_library.pick_run_quality(
        step=3, variety_index=0, category="threshold", threshold_sec=245)

    assert "Drempelpace: 4:15/km" in slow["beschrijving"]
    assert "Drempelpace: 4:05/km" in fast["beschrijving"]
    assert slow["beschrijving"] != fast["beschrijving"]


def test_threshold_library_heeft_cruise_en_intervalvormen():
    workout = workout_library.run_quality_library(threshold_sec=255)["threshold"][0]
    descriptions = "\n".join(w["beschrijving"] for w in workout)
    assert "cruise threshold" in descriptions
    assert "intervalpace" in descriptions


def test_dubbele_drempel_vanaf_start_week_ook_in_deload():
    from datetime import date, timedelta

    from agents.endurance_coach import DOUBLE_DREMPEL_START_WEEK, plan_sessions

    ig = {"run_intensity_allowed": True, "strides_allowed": True,
          "tempo_allowed": True, "volume_modifier": 1.0}
    lm = {"recommended_weekly_tss": 650}

    quality_types = {"run_threshold_short", "run_threshold_long", "run_vo2max"}

    def quality_count(week_nr, deload=False):
        guard = dict(ig, _is_deload_week=deload)
        monday = date(2026, 4, 6) + timedelta(weeks=week_nr - 1)
        from agents import marathon_periodizer as mp
        vol = mp.calculate_weekly_run_volume(week_nr)
        out = plan_sessions(phase=vol["fase"], injury_guard=guard,
                            load_manager=lm, week_start=monday,
                            marathon_volume=vol)
        return sum(1 for s in out if s.get("type") in quality_types)

    assert DOUBLE_DREMPEL_START_WEEK <= 14
    assert quality_count(DOUBLE_DREMPEL_START_WEEK) == 2
    assert quality_count(DOUBLE_DREMPEL_START_WEEK + 1, deload=True) == 2
    assert quality_count(DOUBLE_DREMPEL_START_WEEK - 1) == 1


def test_bike_week_geen_threshold_bij_dubbele_run_drempel():
    from agents.bike_coach import select_bike_sessions_for_week

    sessies = select_bike_sessions_for_week(17, "transformatie_I", {"ftp": 290})
    types = {s.get("type") for s in sessies}
    assert "threshold" not in types, "fiets mag geen 3e LT-dag toevoegen"
    assert types & {"long_slow", "fatmax_medium", "fatmax_lang"}
