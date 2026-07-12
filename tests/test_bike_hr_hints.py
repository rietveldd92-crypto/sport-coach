from __future__ import annotations

from agents import workout_library
from core.workout_profile import parse_profile


def test_threshold_builder_contains_hr_hint_on_stable_work_block():
    workout = workout_library.bike_threshold_variants(290)[9]

    assert "- 10m 100% 85rpm (HR 167-175)" in workout["beschrijving"]


def test_vo2_microbursts_do_not_get_hr_hint():
    workout = workout_library.microbursts(290)

    assert "(HR " not in workout["beschrijving"]


def test_endurance_ride_contains_z2_hr_hint():
    workout = workout_library.endurance_ride(60)

    assert "(HR 129-145)" in workout["beschrijving"]


def test_profile_parser_ignores_hr_hints():
    plain = "Main Set\n2x\n- 10m 100% 85rpm\n- 4m 55% 95rpm"
    hinted = "Main Set\n2x\n- 10m 100% 85rpm (HR 167-175)\n- 4m 55% 95rpm"

    assert parse_profile(plain) == parse_profile(hinted)
