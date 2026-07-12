from __future__ import annotations

import pytest

from core.workout_profile import parse_profile


BIKE_THRESHOLD = """Warmup
- 10m ramp 50-80% 90rpm

Main Set
2x
- 10m 100% 85rpm
- 4m 55% 95rpm

Cooldown
- 10m ramp 75-50%
"""


def test_bike_threshold_profile_duration_and_pcts():
    profile = parse_profile(BIKE_THRESHOLD)

    assert sum(step["sec"] for step in profile) == pytest.approx(48 * 60)
    assert 100 in [step["pct"] for step in profile]
    assert 80 in [step["pct"] for step in profile]


def test_run_repeats_km_pace_with_threshold_pace():
    desc = """Main Set
5x
- 1km 4:15/km Pace
- 2m 64% Pace
"""

    profile = parse_profile(desc, threshold_pace_sec=255)

    assert len(profile) == 10
    assert [step["sec"] for step in profile[::2]] == [255] * 5
    assert [step["pct"] for step in profile[::2]] == [100] * 5


def test_ramp_becomes_four_substeps():
    profile = parse_profile("- 8m ramp 50-80%")

    assert len(profile) == 4
    assert [step["sec"] for step in profile] == [120] * 4
    assert [step["pct"] for step in profile] == [50, 60, 70, 80]


def test_free_text_returns_empty_profile():
    assert parse_profile("Los fietsen op gevoel. Geen structuur.") == []


def test_hr_hint_does_not_change_profile():
    plain = "- 10m 100% 85rpm"
    hinted = "- 10m 100% 85rpm (HR 167-175)"

    assert parse_profile(plain) == parse_profile(hinted)
