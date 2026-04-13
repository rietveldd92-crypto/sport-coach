"""Tests voor agents.workout_intent.get_intent."""
from __future__ import annotations

import pytest

from agents.workout_intent import get_intent


@pytest.mark.parametrize("wtype,must_contain", [
    ("threshold", "vermogen vasthouden"),
    ("cp_intervals", "all-out"),
    ("fatmax_medium", "High Z2"),
    ("fatmax_lang", "High Z2"),
    ("long_slow", "Cadens"),
    ("easy_spin", "herstel"),
    ("recovery_spin", "herstel"),
    ("z2_standard", "Conversatietempo"),
    ("aerobic_z2", "Conversatietempo"),
    ("lange_duur", "sloom"),
    ("long_run", "sloom"),
    ("tempoduur", "aerobe drempel"),
    ("drempel", "gelijkmatig"),
    ("marathon_tempo", "Race-pace"),
    ("strides", "Neuromusculaire"),
])
def test_per_type_intent(wtype, must_contain):
    msg = get_intent({"type": wtype})
    assert must_contain.lower() in msg.lower()


def test_unknown_type_fallback():
    msg = get_intent({"type": "volkomen_onbekend"})
    assert "luister" in msg.lower() or "voer uit" in msg.lower()


def test_none_workout_fallback():
    msg = get_intent(None)
    assert msg
    assert "luister" in msg.lower() or "voer uit" in msg.lower()


def test_empty_type_fallback():
    msg = get_intent({"type": ""})
    assert "luister" in msg.lower() or "voer uit" in msg.lower()


def test_substring_match_run_z2():
    """run_z2_standard zou moeten matchen op z2_standard via substring."""
    msg = get_intent({"type": "run_z2_standard"})
    assert "Conversatietempo".lower() in msg.lower()


def test_substring_match_bike_threshold():
    """bike_threshold moet de threshold-intent krijgen."""
    msg = get_intent({"type": "bike_threshold"})
    assert "vermogen vasthouden".lower() in msg.lower()


def test_naam_fallback_fatmax():
    """Events uit intervals.icu hebben geen coach-type — gebruik naam."""
    msg = get_intent({"type": "Ride", "naam": "Fatmax – 80 min high Z2"})
    assert "high z2" in msg.lower()


def test_naam_fallback_longrun():
    msg = get_intent({"type": "Run", "naam": "Lange duurloop – 24 km"})
    assert "sloom" in msg.lower()


def test_naam_fallback_threshold():
    msg = get_intent({"type": "Ride", "naam": "Threshold – 4x6 min @ 97%"})
    assert "vermogen vasthouden" in msg.lower()
