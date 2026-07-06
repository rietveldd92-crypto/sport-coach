"""Tests voor agents/pijlers.py — het vier-pijler-model."""
from agents.pijlers import PIJLER_LABELS, classify_pijler, pijler_header


def test_drempel_en_cruise_zijn_lactaatdrempel():
    assert classify_pijler({"type": "drempel"}) == "lactaatdrempel"
    assert classify_pijler({"type": "drempel_cruise"}) == "lactaatdrempel"
    assert classify_pijler({"type": "threshold", "naam": "Threshold – Pyramide"}) == "lactaatdrempel"


def test_long_run_is_fatigue_resistance():
    assert classify_pijler({"type": "lange_duur"}) == "fatigue_resistance"
    assert classify_pijler({"naam": "Lange duurloop – 90 min"}) == "fatigue_resistance"
    assert classify_pijler({"type": "long_slow"}) == "fatigue_resistance"


def test_strides_is_economy_en_vo2_is_vo2():
    assert classify_pijler({"type": "z2_met_strides"}) == "running_economy"
    assert classify_pijler({"type": "vo2max_intervals"}) == "vo2max"


def test_z2_vulling_is_support():
    assert classify_pijler({"type": "z2_standard", "naam": "Duurrit rolling Z2"}) == "support"


def test_header_bestaat_voor_elke_pijler():
    for key in ("lactaatdrempel", "running_economy", "fatigue_resistance",
                "vo2max", "support"):
        assert key in PIJLER_LABELS
    assert pijler_header({"type": "drempel"}).startswith("PIJLER: LACTAATDREMPEL")
