"""Tests voor agents.session_classifier.is_sacred."""
from agents.session_classifier import is_sacred


def test_long_run_by_name_is_sacred():
    assert is_sacred({"type": "Run", "name": "Lange duurloop 20km"})


def test_long_run_by_duration_is_sacred():
    assert is_sacred({"type": "Run", "name": "Duurloop", "duration_min": 95})


def test_short_z2_run_is_soft():
    assert not is_sacred({"type": "Run", "name": "Z2 rustige duurloop", "duration_min": 50})


def test_drempel_run_is_sacred():
    assert is_sacred({"type": "Run", "name": "Drempel 4x1km"})


def test_marathon_tempo_is_sacred():
    assert is_sacred({"type": "Run", "name": "Marathon_tempo 10km"})


def test_threshold_bike_is_sacred():
    assert is_sacred({"type": "Ride", "name": "Threshold 3x10min"})


def test_sweetspot_bike_is_sacred():
    assert is_sacred({"type": "Ride", "name": "Sweetspot 2x20"})


def test_easy_spin_bike_is_soft():
    assert not is_sacred({"type": "Ride", "name": "Easy spin 60min"})


def test_recovery_is_always_soft():
    # Zelfs als "long" in de tekst zit — recovery wint
    assert not is_sacred({"type": "Run", "name": "Recovery long walk", "duration_min": 120})


def test_empty_workout():
    assert not is_sacred({})
    assert not is_sacred(None) is True  # returns False, not truthy
