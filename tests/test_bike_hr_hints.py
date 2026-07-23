from __future__ import annotations

from agents import feedback_engine, workout_library
from core.workout_profile import parse_profile

# Uit de referentiewaarden afgeleid: de hints horen mee te schuiven zodra HRmax
# bijgesteld wordt, dus een hard getal hier zou alleen de test laten rotten.
DREMPEL_BAND = (f"{feedback_engine.THRESHOLD_HR_MIN}-"
                f"{feedback_engine.THRESHOLD_HR_MAX}")
Z2_BAND = f"{feedback_engine.Z2_HR_MIN}-{feedback_engine.Z2_HR_MAX}"


def test_threshold_builder_contains_hr_hint_on_stable_work_block():
    workout = workout_library.bike_threshold_variants(290)[9]

    assert f"- 10m 100% 85rpm (HR {DREMPEL_BAND})" in workout["beschrijving"]


def test_vo2_microbursts_do_not_get_hr_hint():
    workout = workout_library.microbursts(290)

    assert "(HR " not in workout["beschrijving"]


def test_endurance_ride_contains_z2_hr_hint():
    workout = workout_library.endurance_ride(60)

    assert f"(HR {Z2_BAND})" in workout["beschrijving"]


def test_profile_parser_ignores_hr_hints():
    plain = "Main Set\n2x\n- 10m 100% 85rpm\n- 4m 55% 95rpm"
    hinted = "Main Set\n2x\n- 10m 100% 85rpm (HR 167-175)\n- 4m 55% 95rpm"

    assert parse_profile(plain) == parse_profile(hinted)
