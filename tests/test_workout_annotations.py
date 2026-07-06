"""Tests for agents.workout_annotations."""
from agents.workout_annotations import (
    annotate_description,
    pct_to_pace_str,
    pct_to_watts,
)


def test_pct_to_watts():
    assert pct_to_watts(100, 290) == 290
    assert pct_to_watts(75, 290) == 218
    assert pct_to_watts(50, 200) == 100


def test_pct_to_pace_str_threshold():
    # 100% van drempelpace = drempelpace
    assert pct_to_pace_str(100, 260) == "4:20/km"


def test_pct_to_pace_str_easy():
    # 75% = trager (ongeveer 5:47/km bij 260s drempel)
    assert pct_to_pace_str(75, 260) == "5:47/km"


def test_annotate_bike_fixed():
    desc = "- 11m 63% 90rpm"
    out = annotate_description(desc, "VirtualRide", ftp=290)
    assert "(183W)" in out
    assert "90rpm" in out


def test_annotate_bike_ramp():
    desc = "- 8m ramp 45-63% 85rpm"
    out = annotate_description(desc, "VirtualRide", ftp=290)
    assert "130->183W" in out


def test_annotate_run_fixed():
    desc = "- 31m 75% Pace"
    out = annotate_description(desc, "Run", threshold_pace_sec=260)
    assert "5:47/km" in out


def test_annotate_run_tempo_komt_na_pace_woord():
    # Tempo hoort NA het woord "Pace" te staan, niet ervoor.
    desc = "- 31m 75% Pace"
    out = annotate_description(desc, "Run", threshold_pace_sec=260)
    assert out == "- 31m 75% Pace (5:47/km)"


def test_annotate_run_ramp_wordt_vaste_stap():
    # Runs krijgen geen ramps: verschuivend pace-doel is fiets-precisie.
    # Ramp wordt één vaste stap op de midpoint-pace.
    desc = "- 5m ramp 55-80% Pace"
    out = annotate_description(desc, "Run", threshold_pace_sec=260)
    assert "ramp" not in out
    assert out == "- 5m 68% Pace (6:22/km)"


def test_annotate_bike_ramp_blijft():
    # Fiets houdt ramps — ERG-mode kan er wat mee.
    desc = "- 8m ramp 45-63% 85rpm"
    out = annotate_description(desc, "VirtualRide", ftp=290)
    assert "ramp" in out


def test_idempotent():
    desc = "- 11m 63% 90rpm\n- 8m ramp 45-63%"
    once = annotate_description(desc, "VirtualRide")
    twice = annotate_description(once, "VirtualRide")
    assert once == twice


def test_unknown_sport_passthrough():
    desc = "- 11m 63% 90rpm"
    assert annotate_description(desc, "WeightTraining") == desc


def test_non_step_lines_preserved():
    desc = "Warmup\n- 5m 50%\n\nMain Set\nFoo bar."
    out = annotate_description(desc, "VirtualRide")
    assert "Warmup" in out
    assert "Main Set" in out
    assert "Foo bar." in out
