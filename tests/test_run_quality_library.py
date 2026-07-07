from __future__ import annotations

from datetime import date

from agents import endurance_coach, workout_library


def test_run_quality_ladders_are_tss_progressive():
    for category, rungs in workout_library.RUN_QUALITY_LIBRARY.items():
        rung_tss = [
            min(workout["tss_geschat"] for workout in variants)
            for variants in rungs
        ]
        assert rung_tss == sorted(rung_tss), category
        assert rung_tss[-1] > rung_tss[0], category


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
