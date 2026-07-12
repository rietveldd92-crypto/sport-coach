from __future__ import annotations

import re
from datetime import date

from agents import endurance_coach, workout_library


def test_run_quality_ladders_are_tss_progressive():
    for category, rungs in workout_library.run_quality_library(255, mp_sec=256).items():
        rung_tss = [
            min(workout["tss_geschat"] for workout in variants)
            for variants in rungs
        ]
        assert rung_tss == sorted(rung_tss), category
        assert rung_tss[-1] > rung_tss[0], category


def test_run_quality_v2_ladders_are_strictly_progressive():
    library = workout_library.run_quality_library(255, mp_sec=256)
    for category in ("threshold", "speed", "vo2max", "marathon"):
        rung_tss = [
            min(workout["tss_geschat"] for workout in variants)
            for variants in library[category]
        ]
        assert rung_tss == sorted(rung_tss), category
        assert len(set(rung_tss)) == len(rung_tss), category


def test_run_quality_v2_steps_are_parseable_absolute_paces():
    step_re = re.compile(
        r"^- (?:\d+(?:\.\d+)?km|\d+m|\d+s) \d:\d{2}/km Pace\b",
        re.MULTILINE,
    )
    for category, rungs in workout_library.run_quality_library(255, mp_sec=256).items():
        if category in {"threshold_short", "threshold_long"}:
            continue
        for variants in rungs:
            for workout in variants:
                if category == "speed":
                    assert "Drempelpace: 4:15/km" in workout["beschrijving"]
                assert step_re.search(workout["beschrijving"]), category


def test_run_quality_v2_pace_schaalt_met_threshold():
    slow = workout_library.pick_run_quality(
        step=2, variety_index=0, category="threshold_short", threshold_sec=255,
    )
    fast = workout_library.pick_run_quality(
        step=2, variety_index=0, category="threshold_short", threshold_sec=245,
    )

    pace_re = re.compile(r"- \d+(?:\.\d+)?km (?P<m>\d):(?P<s>\d{2})/km Pace")
    slow_m = pace_re.search(slow["beschrijving"])
    fast_m = pace_re.search(fast["beschrijving"])
    slow_sec = int(slow_m.group("m")) * 60 + int(slow_m.group("s"))
    fast_sec = int(fast_m.group("m")) * 60 + int(fast_m.group("s"))
    assert slow_sec - fast_sec in {9, 10, 11}


def test_speed_is_geen_lt_sessie_en_blijft_licht():
    speed = workout_library.pick_run_quality(
        step=6, variety_index=1, category="speed", threshold_sec=255,
    )

    assert speed["type"] == "run_speed"
    assert speed["intensiteit_factor"] <= 0.80


def test_marathon_gebruikt_doelpace_en_warns_bij_te_snelle_mp():
    marathon = workout_library.pick_run_quality(
        step=1, variety_index=0, category="marathon", threshold_sec=270, mp_sec=256,
    )

    assert "4:16/km Pace" in marathon["beschrijving"]
    assert marathon.get("warnings")


def test_pick_run_quality_rotates_category_and_variant_but_keeps_step():
    picked = [
        workout_library.pick_run_quality(step=2, variety_index=i)
        for i in range(6)
    ]

    assert {p["type"] for p in picked[:3]} == {
        "run_threshold_short",
        "run_threshold_long",
        "run_vo2max",
    }
    assert picked[0]["naam"] != picked[3]["naam"]
    assert all(55 <= p["tss_geschat"] <= 90 for p in picked)


def test_marathon_drempel_gate_uses_quality_library(monkeypatch):
    state = {
        "progression": {
            "run_quality_step": 2,
            "run_quality_variety_index": 0,
            "z2_run_variety_index": 0,
            "long_run_variety_index": 0,
        }
    }
    monkeypatch.setattr("shared.load_state", lambda: state)

    volume = {
        "fase": "transformatie_I",
        "week": 17,
        "run_km_totaal": 55.0,
        "run_sessies": 4,
        "korte_sessies": 3,
        "km_per_korte_sessie": 10.0,
        "medium_sessies": 0,
        "lange_duurloop_km": 22.0,
        "run_intensiteit": "drempel",
    }
    guard = {
        "run_intensity_allowed": True,
        "tempo_allowed": True,
        "strides_allowed": True,
        "volume_modifier": 1.0,
    }

    sessions = endurance_coach.plan_sessions(
        phase="transformatie_I",
        injury_guard=guard,
        load_manager={"recommended_weekly_tss": 600},
        week_start=date(2026, 7, 27),
        marathon_volume=volume,
    )

    types = [s["type"] for s in sessions]
    assert any(t in {"run_threshold_short", "run_threshold_long", "run_vo2max"}
               for t in types)
    assert types.count("run_threshold_long") >= 1
