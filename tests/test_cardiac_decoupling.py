"""Decoupling meet efficiëntieverlies, niet kale hartslagstijging."""

import pytest

from agents import workout_analysis as wa


def _splits(rows):
    return [{"pace": p, "hr": hr, "distance_km": 1.0} for p, hr in rows]


def test_negative_split_scoort_niet_als_slecht():
    """Het geval van 2 augustus 2026: harder lopen én hogere HR.

    De oude berekening keek alleen naar HR en gaf +5%: "aerobe basis
    onvoldoende". Terwijl pace en HR gelijk opliepen — de efficiëntie bleef
    dus staan.
    """
    rows = [(5.10, 150)] * 6 + [(4.60, 166)] * 6  # ~9% sneller, ~9% meer HR
    decoupling = wa._cardiac_decoupling(_splits(rows))
    assert decoupling is not None
    assert abs(decoupling) < 2, f"negative split mag geen drift-alarm geven ({decoupling}%)"


def test_echte_drift_wordt_wel_gezien():
    """Gelijke pace, oplopende HR = het probleem dat de metric hoort te vangen."""
    rows = [(5.00, 145)] * 6 + [(5.00, 160)] * 6
    decoupling = wa._cardiac_decoupling(_splits(rows))
    assert decoupling > 5


def test_stabiele_loop_zit_rond_nul():
    rows = [(5.00, 150)] * 12
    assert wa._cardiac_decoupling(_splits(rows)) == pytest.approx(0, abs=0.5)


def test_intervals_icu_waarde_wint():
    """intervals.icu rekent over de hele stream; die is preciezer dan km-splits."""
    rows = [(5.00, 145)] * 6 + [(5.00, 175)] * 6  # zou zelf hoog uitkomen
    assert wa._cardiac_decoupling(_splits(rows), {"decoupling": -1.4344}) == -1.4


def test_te_weinig_splits_geeft_none():
    assert wa._cardiac_decoupling(_splits([(5.0, 150), (5.0, 152)])) is None


def test_splits_zonder_hr_tellen_niet_mee():
    rows = [(5.0, 0)] * 8
    assert wa._cardiac_decoupling(_splits(rows)) is None


@pytest.mark.parametrize("dec_min,verwacht", [
    (4.34, "4:20"),
    (5.10, "5:06"),
    (4.883, "4:53"),
    (3.87, "3:52"),
])
def test_pace_nooit_als_losse_decimalen(dec_min, verwacht):
    """4.73 gelezen als "4:73" bestaat niet; alles gaat via _fmt_pace."""
    assert wa._fmt_pace(dec_min) == verwacht
