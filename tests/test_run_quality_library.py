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
    for category in ("subthreshold", "threshold", "speed", "vo2max", "marathon"):
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
        "run_subthreshold",
        "run_speed",
        "run_marathon",
    }
    assert picked[0]["naam"] != picked[3]["naam"]
    # Speed is bewust licht (economy-prikkel), marathon het zwaarst.
    assert all(40 <= p["tss_geschat"] <= 90 for p in picked)


def test_subthreshold_is_echt_sub_drempel():
    """Elke sub-drempelworkout moet ook als sub-drempel classificeren.

    Zakt de gap met de drempelpace onder SUBT_MIN_GAP_SEC, dan leest het
    drempeldossier de sessie als drempelwerk en gaat de drift-regel de
    drempelpace omlaag praten (bug van 12 aug, commit 44b700f).
    """
    from agents.threshold_model import SUBT_MIN_GAP_SEC, session_kind

    pace_re = re.compile(r"- \d+m (?P<m>\d):(?P<s>\d{2})/km Pace")
    for threshold_sec in (245, 255, 262):
        rungs = workout_library.run_quality_library(
            threshold_sec, mp_sec=280,
        )["subthreshold"]
        for variants in rungs:
            for workout in variants:
                assert workout["naam"].startswith("Sub-drempel")
                m = pace_re.search(workout["beschrijving"])
                pace = int(m.group("m")) * 60 + int(m.group("s"))
                assert pace - threshold_sec >= SUBT_MIN_GAP_SEC, workout["naam"]
                assert session_kind(workout["naam"], pace, threshold_sec) == (
                    "subthreshold"
                )


def test_subthreshold_beschrijving_bevat_kalibratieprotocol():
    from agents.feedback_engine import SUBT_CAL_HR_MAX, SUBT_CAL_HR_MIN

    workout = workout_library.pick_run_quality(
        step=3, variety_index=0, category="subthreshold", threshold_sec=262,
    )

    assert f"{SUBT_CAL_HR_MIN}-{SUBT_CAL_HR_MAX} bpm" in workout["beschrijving"]
    assert "AFBREKEN" in workout["beschrijving"]


def test_pick_long_run_marathonspecifiek_roteert_mp_en_subdrempel():
    mp = workout_library.pick_long_run(
        20, 0, marathon_specific=True, threshold_sec=262)
    sub = workout_library.pick_long_run(
        20, 1, marathon_specific=True, threshold_sec=262)
    plain = workout_library.pick_long_run(20, 0)

    assert mp["type"] == "long_run_mp"
    assert "@ MP" in mp["naam"]
    assert sub["type"] == "long_run_subt"
    assert "sub-drempel" in sub["naam"]
    assert plain["type"] == "long_run"


def test_marathon_block_pace_realistisch_tot_de_drempel_het_doel_dekt():
    # Drempel 4:22 → afgeleide MP 4:35 (drempel+5%), niet de doelpace.
    assert workout_library.marathon_block_pace(262) == round(262 * 1.05)
    # Snelle drempel: de (tragere) doelpace wint dan vanzelf.
    fast = workout_library.marathon_block_pace(238)
    assert fast >= round(238 * 1.05)


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
    # Norwegian-omslag: beide kwaliteitsdagen in het legacy-pad zijn sub-drempel.
    assert types.count("run_subthreshold") == 2
