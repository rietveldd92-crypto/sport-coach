"""De workout-naam moet de stappen dekken die eronder staan."""

from agents import workout_naming


# Het echte geval uit de kalender van 31 juli 2026: naam van ladder-trede 6,
# body van trede 4. Je traint naar de body, de coach-feedback las de naam.
DREMPEL_BODY = """\
Drempelpace: 4:20/km

Warmup
- 15m ramp 65-82% Pace

Main Set
3x
- 15m 4:25/km Pace (100% drempel - cruise threshold)
- 3m 64% Pace

Cooldown
- 12m ramp 75-60% Pace
"""


def test_naam_wordt_gecorrigeerd_naar_de_stappen():
    naam, warn = workout_naming.check(
        "Lange drempel - 2x30 min @ 4:20/km", DREMPEL_BODY)
    assert naam == "Lange drempel - 3x15 min @ 4:25/km"
    assert warn is not None
    assert "2x30" in warn and "3x15" in warn


def test_kloppende_naam_blijft_ongemoeid():
    naam, warn = workout_naming.check(
        "Lange drempel - 3x15 min @ 4:25/km", DREMPEL_BODY)
    assert naam == "Lange drempel - 3x15 min @ 4:25/km"
    assert warn is None


def test_cosmetisch_verschil_is_geen_mismatch():
    naam, warn = workout_naming.check(
        "Lange drempel - 3x15min @ 4:25/km", DREMPEL_BODY)
    assert warn is None


def test_km_reps_worden_herkend():
    body = """\
Main Set
6x
- 1.5km 4:17/km Pace (102% drempel - intervalpace)
- 2m 64% Pace

Cooldown
- 12m ramp
"""
    naam, warn = workout_naming.check("Korte drempel - 5x1km @ 4:22/km", body)
    assert naam == "Korte drempel - 6x1.5km @ 4:17/km"
    assert warn is not None


def test_procent_target_wordt_herkend():
    body = """\
Main Set
6x
- 3m 112% Pace (VO2max)
- 2m 58% Pace

Cooldown
- 12m ramp
"""
    # De VO2max-namen schrijven minuten als "2m"; die stijl houden we aan.
    naam, warn = workout_naming.check("VO2max - 14x2m @ 112%", body)
    assert naam == "VO2max - 6x3m @ 112%"
    assert warn is not None


def test_warmup_telt_niet_mee_als_main_set():
    """De warmup heeft ook '- 15m ...'-regels; die mogen de naam niet sturen."""
    parsed = workout_naming.parse_main_set(DREMPEL_BODY)
    assert parsed == {"reps": 3, "dur": 15.0, "unit": "m", "target": "4:25/km"}


def test_vrije_vorm_body_laat_naam_met_rust():
    """Duurlopen hebben geen main set — dan niet gokken."""
    naam, warn = workout_naming.check(
        "Lange duurloop negative split - 22km", "- 60m 70% Pace\n- 60m 75% Pace")
    assert naam == "Lange duurloop negative split - 22km"
    assert warn is None


def test_naam_zonder_spec_blijft_ongemoeid():
    naam, warn = workout_naming.check("Fatmax - 80 min high Z2", DREMPEL_BODY)
    assert naam == "Fatmax - 80 min high Z2"
    assert warn is None
