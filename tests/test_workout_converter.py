"""Unit tests for workout_converter.convert().

Fixture-based tests covering the 8 scenarios flagged as critical by the
tester review (obs 418): power-steady, intervals with reps, running pace,
warmup/main/cooldown, missing FTP, empty workout_doc, HR-zone target,
and a total-duration sanity check. Each uses a real (or plausibly
synthetic) workout_doc from ``tests/fixtures/workout_docs/``.
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


def sum_durations(steps: list[dict]) -> int:
    """Sum duration-seconds of a TP structure step list, recursing into reps."""
    total = 0
    for step in steps:
        if step["type"] == "repetition":
            reps = step["length"]["value"]
            total += reps * sum_durations(step["steps"])
        else:
            total += step["length"]["value"]
    return total


# ---------------------------------------------------------------------------
# 1. Power-steady workout conversion
# ---------------------------------------------------------------------------


def test_power_steady_endurance_ride_converts_to_duration_structure():
    """8-step rolling endurance ride: all flat power steps, no repetitions."""
    doc, sport = load_fixture("bike_endurance_rolling_8step.json")

    result = convert(doc, sport)

    assert result["workout_type_id"] == 2  # Bike
    assert result["tp_structure"]["primaryLengthMetric"] == "duration"
    assert result["tp_structure"]["primaryIntensityMetric"] == "power"

    steps = result["tp_structure"]["structure"]
    assert len(steps) == 8
    assert all(s["type"] == "step" for s in steps)
    # First step is warmup (ramp), should have min < max from start/end
    first = steps[0]
    assert first["name"] == "Warm Up"
    assert first["length"] == {"value": 480, "unit": "second"}
    # start=130W, end=182W, ftp=290 → 44.8% / 62.8%
    t = first["targets"][0]
    assert t["minValue"] == pytest.approx(44.8, abs=0.1)
    assert t["maxValue"] == pytest.approx(62.8, abs=0.1)


# ---------------------------------------------------------------------------
# 2. Intervals with repetitions
# ---------------------------------------------------------------------------


def test_threshold_intervals_expand_into_repetition_group():
    """3x8 threshold ride: main set is a repetition with 2 child steps."""
    doc, sport = load_fixture("bike_threshold_3x8_intervals.json")

    result = convert(doc, sport)

    steps = result["tp_structure"]["structure"]
    # Expected layout: warmup, surge, recovery, 3x main, cooldown
    assert [s["type"] for s in steps] == [
        "step", "step", "step", "repetition", "step"
    ]

    main_set = steps[3]
    assert main_set["length"] == {"value": 3, "unit": "repetition"}
    # Child steps: 480s @ 95% FTP work, 180s @ 55% FTP recovery
    children = main_set["steps"]
    assert len(children) == 2
    work = children[0]
    assert work["length"] == {"value": 480, "unit": "second"}
    # 95% of 290 = 275.5 → percentage ~= 94.8-97.2 based on resolved range
    work_target = work["targets"][0]
    # Resolved _power start=268, end=282, ftp=290 → ~92.4% / ~97.2%
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
    assert result["tp_structure"]["primaryIntensityMetric"] == "pace"

    steps = result["tp_structure"]["structure"]
    assert len(steps) == 1
    assert steps[0]["length"] == {"value": 1800, "unit": "second"}
    # _pace start=3.046875, end=3.203125, threshold_pace=4.1666 → ~73.1% / ~76.9%
    t = steps[0]["targets"][0]
    assert t["minValue"] == pytest.approx(73.1, abs=0.2)
    assert t["maxValue"] == pytest.approx(76.9, abs=0.2)


def test_fartlek_run_combines_pace_and_repetitions():
    """Fartlek: pace-based warmup + 5x repetition group + cooldown."""
    doc, sport = load_fixture("run_fartlek_5x_pace.json")

    result = convert(doc, sport)

    steps = result["tp_structure"]["structure"]
    assert [s["type"] for s in steps] == ["step", "repetition", "step"]
    assert steps[1]["length"] == {"value": 5, "unit": "repetition"}
    assert len(steps[1]["steps"]) == 3


# ---------------------------------------------------------------------------
# 4. Warmup / main / cooldown structure
# ---------------------------------------------------------------------------


def test_warmup_and_cooldown_steps_are_named():
    """Steps flagged warmup/cooldown get canonical display names."""
    doc, sport = load_fixture("bike_sweetspot_2x15_intervals.json")

    result = convert(doc, sport)

    steps = result["tp_structure"]["structure"]
    names = [s["name"] for s in steps]
    assert names[0] == "Warm Up"
    assert names[-1] == "Cool Down"


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

    assert result["tp_structure"]["primaryIntensityMetric"] == "heartRate"
    # Middle steady step: _hr start=134, end=140.6, lthr=176 → ~76.1% / ~79.9%
    middle = result["tp_structure"]["structure"][1]
    t = middle["targets"][0]
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

    This is the single most important regression guard: if a step gets
    dropped or a repetition gets unrolled incorrectly, total time
    diverges and this test fires.
    """
    doc, sport = load_fixture(fixture_name)

    result = convert(doc, sport)

    assert result["total_seconds"] == doc["duration"]
    # And the structure itself must sum to the same value
    structure_total = sum_durations(result["tp_structure"]["structure"])
    assert structure_total == doc["duration"]
