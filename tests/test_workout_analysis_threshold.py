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
    monkeypatch.setattr(
        workout_analysis.api, "get_activity_streams",
        lambda _id, types=None: {},
    )


def _streams(monkeypatch, paces_sec: list[tuple[int, int]], hr: int = 170):
    """Bouw een 1Hz-stream uit (pace_sec_per_km, duur_sec)-blokken."""
    vel, beats = [], []
    for pace_sec, seconds in paces_sec:
        vel += [1000 / pace_sec] * seconds
        beats += [hr] * seconds
    monkeypatch.setattr(
        workout_analysis.api, "get_activity_streams",
        lambda _id, types=None: [
            {"type": "velocity_smooth", "data": vel},
            {"type": "heartrate", "data": beats},
        ],
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


def test_reps_komen_uit_de_pace_stream_niet_uit_icu_intervals(monkeypatch):
    """intervals.icu knipt run-reps op running power, niet op pace.

    Echte sessie (13 jul): een 12-minutenrep werd in brokken geknipt met
    'RECOVERY'-stukken op 4:17/km ertussen, en 2,5 min op target verdween
    zelfs helemaal in de recovery. Op de pace-stream staan de reps er wel.
    """
    event = {"type": "Run", "name": "Lange drempel - 3x12 min @ 4:23/km"}
    _streams(monkeypatch, [
        (295, 900),   # warming-up 4:55/km
        (260, 720),   # rep 1 — 12 min op 4:20/km
        (330, 150),   # sukkeldraf 5:30/km
        (259, 720),   # rep 2
        (330, 150),
        (262, 720),   # rep 3
        (340, 300),   # cooling-down
    ])

    metrics = workout_analysis.analyze(event, _ACTIVITY)["metrics"]

    # Het gladstrijkvenster vervaagt de repgrens een paar seconden; op de
    # vraag "waren dit drie blokken van twaalf minuten?" doet dat niets af.
    assert [round(d / 60) for d in metrics["rep_durations_s"]] == [12, 12, 12]
    assert metrics["work_time_min"] == 36
    assert metrics["target_pace_sec"] == 263
    # 4:20/km gelopen op een target van 4:23: een sneller-signaal, geen trager.
    # (Met de oude icu_intervals-route kwam hier +17s uit — de sukkeldraf.)
    assert -4 <= metrics["pace_delta_sec"] <= -1


def test_korte_dip_binnen_een_rep_breekt_de_rep_niet(monkeypatch):
    """Een bocht of stoplicht mag geen rep in tweeën hakken."""
    event = {"type": "Run", "name": "Lange drempel - 3x12 min @ 4:23/km"}
    _streams(monkeypatch, [
        (295, 600),
        (260, 350),
        (300, 10),    # even inzakken
        (260, 360),
        (340, 300),
    ])

    metrics = workout_analysis.analyze(event, _ACTIVITY)["metrics"]

    assert len(metrics["rep_durations_s"]) == 1
    assert metrics["work_time_min"] == 12


def test_sukkeldraf_telt_niet_als_werk(monkeypatch):
    """De herstelpace mag nooit in de gemiddelde intervalpace belanden."""
    event = {"type": "Run", "name": "Lange drempel - 3x12 min @ 4:23/km"}
    _streams(monkeypatch, [
        (260, 720),
        (337, 400),   # 5:37/km — ruim buiten de 8%-marge
        (260, 720),
    ])

    metrics = workout_analysis.analyze(event, _ACTIVITY)["metrics"]

    assert [round(d / 60) for d in metrics["rep_durations_s"]] == [12, 12]
    assert metrics["observed_pace_sec"] == 260


def test_zonder_bruikbare_stream_valt_analyse_terug_op_intervals(monkeypatch):
    """Fake-modus en oude activiteiten leveren geen streams — dan de intervals."""
    event = {"type": "Run", "name": "Korte drempel - 5x1km @ 4:15/km"}
    monkeypatch.setattr(
        workout_analysis.api, "get_activity_streams",
        lambda _id, types=None: {},
    )

    metrics = workout_analysis.analyze(event, _ACTIVITY)["metrics"]

    assert metrics["observed_pace_sec"] == 252  # uit _INTERVALS


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
