"""Metrics die het drempeldossier voeden.

De trend-engine draait op `pace_delta_sec` en `interval_hr_avg`. Als die niet
uit de analyse komen, is elke observatie leeg en kan er nooit een suggestie
vallen — vandaar deze tests op de bron.
"""
import pytest

from agents import workout_analysis


@pytest.fixture(autouse=True)
def _no_interval_fetch(monkeypatch):
    """Voorkom dat de analyse intervals.icu belt; wij leveren de intervallen."""
    monkeypatch.setattr(
        workout_analysis.api, "get_activity_detail",
        lambda _id: {"icu_intervals": _INTERVALS},
    )


# 3x 1km: 4:10, 4:12, 4:14/km bij HR 170-172 => gemiddeld 4:12/km (252s)
_INTERVALS = [
    {"type": "WORK", "distance": 1000, "moving_time": 250, "average_heartrate": 170},
    {"type": "WORK", "distance": 1000, "moving_time": 252, "average_heartrate": 171},
    {"type": "WORK", "distance": 1000, "moving_time": 254, "average_heartrate": 172},
]

_ACTIVITY = {"id": 1, "average_heartrate": 140, "distance": 12000, "moving_time": 3600}


def test_drempelsessie_levert_pace_delta_en_reps_hr():
    event = {"type": "Run", "name": "Korte drempel - 5x1km @ 4:15/km"}

    metrics = workout_analysis.analyze(event, _ACTIVITY)["metrics"]

    assert metrics["target_pace_sec"] == 255
    assert metrics["observed_pace_sec"] == 252
    assert metrics["pace_delta_sec"] == -3  # sneller dan target
    assert metrics["interval_hr_avg"] == 171.0


def test_target_pace_uit_naam_gaat_voor_op_drempel_header():
    """De 'Drempelpace:'-header is de referentie van de atleet, niet de target."""
    event = {
        "type": "Run",
        "name": "Lange drempel - 3x12 min @ 4:20/km",
        "description": "Drempelpace: 4:15/km\n\nMain Set\n- 12m 4:20/km Pace",
    }

    assert workout_analysis.target_pace_sec(event) == 260


def test_target_pace_valt_terug_op_beschrijving():
    event = {
        "type": "Run",
        "name": "Lange drempel",
        "description": "Drempelpace: 4:15/km\n\nMain Set\n- 12m 4:20/km Pace",
    }

    assert workout_analysis.target_pace_sec(event) == 260


def test_zonder_target_geen_pace_delta():
    event = {"type": "Run", "name": "Drempelsessie"}

    metrics = workout_analysis.analyze(event, _ACTIVITY)["metrics"]

    assert metrics["observed_pace_sec"] == 252
    assert "pace_delta_sec" not in metrics


@pytest.mark.parametrize("name,expected", [
    ("Korte drempel - 5x1km @ 4:15/km", "run_tempo"),
    ("Lange drempel - 3x12 min @ 4:18/km", "run_tempo"),
    ("VO2max - 10x60s @ 106%", "run_vo2max"),
    ("Speed economy - 8x20s @ 110%", "run_speed"),
    ("Marathon-specifiek - 3x15 min @ 4:20/km", "run_marathon"),
])
def test_library_v2_namen_worden_herkend(name, expected):
    """Zonder deze regels vielen de v2-categorieën terug op 'run_z2'."""
    assert workout_analysis.classify_workout({"type": "Run", "name": name}) == expected
