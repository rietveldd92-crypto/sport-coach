"""Unit tests for workout_converter.convert().

Fixture-based tests covering the 8 scenarios flagged as critical by the
tester review (obs 418): power-steady, intervals with reps, running pace,
warmup/main/cooldown, missing FTP, empty workout_doc, HR-zone target,
and a total-duration sanity check.

Every TP step is a ``{"type": "step", "length": {"unit": "repetition"},
"steps": [...leaves]}`` wrapper — confirmed against live TP calendar data.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from trainingpeaks_errors import TPConversionError
from workout_converter import convert

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "workout_docs"


def load_fixture(name: str) -> tuple[dict, str]:
    """Return (workout_doc, sport) from a fixture file."""
    data = json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))
    return data["workout_doc"], data["sport"]


def sum_tp_duration(steps: list[dict]) -> int:
    """Sum duration-seconds of a TP structure step list.

    Every top-level entry is a repetition wrapper with ``length.value``
    reps and a ``steps`` list of leaves that carry the real duration.
    """
    total = 0
    for wrapper in steps:
        reps = wrapper["length"]["value"]
        leaves_total = sum(leaf["length"]["value"] for leaf in wrapper["steps"])
        total += reps * leaves_total
    return total


# ---------------------------------------------------------------------------
# 1. Power-steady workout conversion
# ---------------------------------------------------------------------------


def test_power_steady_endurance_ride_converts_to_duration_structure():
    """8-step rolling endurance ride: all top-level wrappers are 1-rep."""
    doc, sport = load_fixture("bike_endurance_rolling_8step.json")

    result = convert(doc, sport)

    assert result["workout_type_id"] == 2  # Bike
    assert result["tp_structure"]["primaryLengthMetric"] == "duration"
    assert result["tp_structure"]["primaryIntensityMetric"] == "percentOfFtp"

    steps = result["tp_structure"]["structure"]
    assert len(steps) == 8
    # Every top-level wrapper is a 1-rep "step" container, length.unit=repetition
    for w in steps:
        assert w["type"] == "step"
        assert w["length"] == {"value": 1, "unit": "repetition"}
        assert len(w["steps"]) == 1

    # First wrapper: warmup ramp
    warmup_leaf = steps[0]["steps"][0]
    assert warmup_leaf["length"] == {"value": 480, "unit": "second"}
    # Leaves have no type, no name — just length + targets
    assert "type" not in warmup_leaf
    assert "name" not in warmup_leaf
    # start=130W, end=182W, ftp=290 → 44.8% / 62.8%
    t = warmup_leaf["targets"][0]
    assert t["minValue"] == pytest.approx(44.8, abs=0.1)
    assert t["maxValue"] == pytest.approx(62.8, abs=0.1)


# ---------------------------------------------------------------------------
# 2. Intervals with repetitions
# ---------------------------------------------------------------------------


def test_threshold_intervals_expand_into_repetition_wrapper():
    """3x8 threshold ride: main set wrapper has length.value=3 with 2 leaves."""
    doc, sport = load_fixture("bike_threshold_3x8_intervals.json")

    result = convert(doc, sport)

    steps = result["tp_structure"]["structure"]
    # Expected: warmup(1), surge(1), recovery(1), main(3), cooldown(1)
    rep_values = [s["length"]["value"] for s in steps]
    assert rep_values == [1, 1, 1, 3, 1]
    # Single-rep wrappers use type="step"; multi-rep uses type="repetition".
    types = [s["type"] for s in steps]
    assert types == ["step", "step", "step", "repetition", "step"]

    main_set = steps[3]
    assert main_set["length"] == {"value": 3, "unit": "repetition"}
    children = main_set["steps"]
    assert len(children) == 2
    # Work leaf: 480s, _power start=268, end=282, ftp=290 → ~92.4% / ~97.2%
    work = children[0]
    assert work["length"] == {"value": 480, "unit": "second"}
    assert "type" not in work  # leaves have no type
    work_target = work["targets"][0]
    assert work_target["minValue"] == pytest.approx(92.4, abs=0.2)
    assert work_target["maxValue"] == pytest.approx(97.2, abs=0.2)


# ---------------------------------------------------------------------------
# 3. Running pace targets
# ---------------------------------------------------------------------------


def test_simple_run_pace_target_converts_to_pace_intensity():
    """Steady Z2 run uses threshold_pace (not FTP) for percentages."""
    doc, sport = load_fixture("run_z2_pace_steady.json")

    result = convert(doc, sport)

    assert result["workout_type_id"] == 3  # Run
    assert result["tp_structure"]["primaryIntensityMetric"] == "percentOfThresholdPace"

    steps = result["tp_structure"]["structure"]
    assert len(steps) == 1
    wrapper = steps[0]
    assert wrapper["length"] == {"value": 1, "unit": "repetition"}
    leaf = wrapper["steps"][0]
    assert leaf["length"] == {"value": 1800, "unit": "second"}
    # _pace start=3.046875, end=3.203125, threshold_pace=4.1666 → ~73.1% / ~76.9%
    t = leaf["targets"][0]
    assert t["minValue"] == pytest.approx(73.1, abs=0.2)
    assert t["maxValue"] == pytest.approx(76.9, abs=0.2)


def test_fartlek_run_combines_pace_and_repetitions():
    """Fartlek: pace-based warmup + 5x repetition wrapper + cooldown."""
    doc, sport = load_fixture("run_fartlek_5x_pace.json")

    result = convert(doc, sport)

    steps = result["tp_structure"]["structure"]
    rep_values = [s["length"]["value"] for s in steps]
    assert rep_values == [1, 5, 1]
    assert len(steps[1]["steps"]) == 3


# ---------------------------------------------------------------------------
# 4. Warmup / main / cooldown structure
# ---------------------------------------------------------------------------


def test_warmup_and_cooldown_leaves_have_no_name_or_type():
    """Leaves intentionally carry only length + targets — no type or name.

    The old schema set ``name`` on leaves, but the live TP calendar
    doesn't include that field and TP rejected our payloads. This guards
    against reintroducing the problem.
    """
    doc, sport = load_fixture("bike_sweetspot_2x15_intervals.json")

    result = convert(doc, sport)

    for wrapper in result["tp_structure"]["structure"]:
        for leaf in wrapper["steps"]:
            assert "name" not in leaf, f"leaf should not have 'name': {leaf}"
            assert "type" not in leaf, f"leaf should not have 'type': {leaf}"
            assert set(leaf.keys()) == {"length", "targets"}


# ---------------------------------------------------------------------------
# 5. Missing FTP handling
# ---------------------------------------------------------------------------


def test_missing_ftp_raises_conversion_error():
    """POWER workout without FTP must fail loudly, not silently default to 0."""
    doc, sport = load_fixture("bike_missing_ftp_error.json")

    with pytest.raises(TPConversionError, match="ftp"):
        convert(doc, sport)


# ---------------------------------------------------------------------------
# 6. Empty workout_doc
# ---------------------------------------------------------------------------


def test_empty_steps_raises_conversion_error():
    """workout_doc with zero steps must raise, not produce empty TP payload."""
    doc, sport = load_fixture("bike_empty_steps_error.json")

    with pytest.raises(TPConversionError, match="steps"):
        convert(doc, sport)


# ---------------------------------------------------------------------------
# 7. HR-zone target
# ---------------------------------------------------------------------------


def test_hr_target_uses_lthr_threshold_and_heartrate_metric():
    """Endurance run with HR target uses lthr, not FTP or threshold_pace."""
    doc, sport = load_fixture("run_hr_zone_endurance.json")

    result = convert(doc, sport)

    assert result["tp_structure"]["primaryIntensityMetric"] == "percentOfThresholdHr"
    # Middle wrapper (steady step 1), leaf 0:
    # _hr start=134, end=140.6, lthr=176 → ~76.1% / ~79.9%
    middle_wrapper = result["tp_structure"]["structure"][1]
    leaf = middle_wrapper["steps"][0]
    t = leaf["targets"][0]
    assert t["minValue"] == pytest.approx(76.1, abs=0.3)
    assert t["maxValue"] == pytest.approx(79.9, abs=0.3)


# ---------------------------------------------------------------------------
# 8. Total duration sanity check
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fixture_name",
    [
        "run_z2_pace_steady.json",
        "bike_threshold_3x8_intervals.json",
        "bike_sweetspot_2x15_intervals.json",
        "bike_endurance_rolling_8step.json",
        "run_fartlek_5x_pace.json",
        "run_hr_zone_endurance.json",
    ],
)
def test_total_duration_matches_workout_doc(fixture_name):
    """Sum of converted step durations must equal workout_doc.duration.

    The strongest regression guard: if any step is dropped or a
    repetition is unrolled incorrectly, the total diverges.
    """
    doc, sport = load_fixture(fixture_name)

    result = convert(doc, sport)

    assert result["total_seconds"] == doc["duration"]
    structure_total = sum_tp_duration(result["tp_structure"]["structure"])
    assert structure_total == doc["duration"]


# ---------------------------------------------------------------------------
# Extra: steady targets collapse to minValue-only
# ---------------------------------------------------------------------------


def test_steady_target_omits_max_value_when_equal_to_min():
    """When lo == hi, TP expects only ``minValue`` (no ``maxValue``).

    The ``run_z2_pace_steady.json`` fixture has start != end so it won't
    exercise this. We exercise it with a minimal synthetic dict.
    """
    synthetic = {
        "duration": 600,
        "ftp": 290,
        "target": "POWER",
        "steps": [
            {
                "duration": 600,
                "power": {"value": 70, "units": "%ftp"},
                "_power": {"value": 203.0},  # no start/end = steady
            }
        ],
    }
    result = convert(synthetic, "Ride")
    leaf = result["tp_structure"]["structure"][0]["steps"][0]
    assert leaf["targets"][0] == {"minValue": 70.0}
