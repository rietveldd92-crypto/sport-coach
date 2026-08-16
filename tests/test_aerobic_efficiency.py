"""Pace bij vaste hartslag — de marker die EF niet kan zijn."""

import pytest

from agents import aerobic_efficiency as ae


def _run(aid, datum, *, minuten=120, naam="Lange duurloop - 22km", km=22.0):
    return {
        "id": aid, "type": "Run", "name": naam,
        "start_date_local": f"{datum}T09:00:00",
        "moving_time": minuten * 60, "distance": km * 1000,
    }


def _streams(hr_seq, vel_seq):
    return [{"type": "heartrate", "data": hr_seq},
            {"type": "velocity_smooth", "data": vel_seq}]


@pytest.fixture(autouse=True)
def _no_cache(monkeypatch):
    """Cache uit: elke test rekent zelf, en schrijft niet in history.db."""
    import history_db

    monkeypatch.setattr(history_db, "get_aerobic_efficiency",
                        lambda *a, **kw: None)
    monkeypatch.setattr(history_db, "record_aerobic_efficiency",
                        lambda *a, **kw: None)


def _patch_streams(monkeypatch, hr, vel):
    import intervals_client

    monkeypatch.setattr(intervals_client, "get_activity_streams",
                        lambda aid, types=None: _streams(hr, vel))


def test_meet_pace_in_band(monkeypatch):
    n = 3600
    hr = [145] * n
    vel = [1000 / 300] * n  # 5:00/km
    _patch_streams(monkeypatch, hr, vel)

    m = ae.measure(_run("1", "2026-08-02"))
    assert m["usable"]
    assert m["pace_sec"] == 300
    assert m["samples_sec"] == n - ae.WARMUP_SKIP_SEC


def test_warmup_telt_niet_mee(monkeypatch):
    """Hartslag loopt achter op inspanning; de eerste 10 min zijn onbruikbaar."""
    n = 3600
    hr = [145] * n
    vel = [1000 / 600] * ae.WARMUP_SKIP_SEC + [1000 / 300] * (n - ae.WARMUP_SKIP_SEC)
    _patch_streams(monkeypatch, hr, vel)

    m = ae.measure(_run("1", "2026-08-02"))
    assert m["pace_sec"] == 300, "trage inloopkilometers mogen niet meetellen"


def test_alleen_hartslag_in_band(monkeypatch):
    n = 3600
    half = n // 2
    hr = [145] * half + [170] * (n - half)          # tweede helft boven de band
    vel = [1000 / 300] * half + [1000 / 240] * (n - half)
    _patch_streams(monkeypatch, hr, vel)

    m = ae.measure(_run("1", "2026-08-02"))
    assert m["pace_sec"] == 300, "het harde eindblok hoort buiten de meting"


def test_stilstaan_telt_niet_mee(monkeypatch):
    n = 3600
    vel = [1000 / 300] * n
    for i in range(1000, 1300):
        vel[i] = 0.2  # verkeerslicht
    _patch_streams(monkeypatch, [145] * n, vel)

    m = ae.measure(_run("1", "2026-08-02"))
    assert m["pace_sec"] == 300


def test_kwaliteitssessie_doet_niet_mee():
    """Dribbelpauzes vallen in de band bij een pace die niets zegt."""
    assert ae.measure(_run("1", "2026-08-02",
                           naam="Lange drempel - 3x12 min @ 4:22/km")) is None
    assert ae.measure(_run("1", "2026-08-02", naam="VO2max - 6x3m @ 112%")) is None


def test_korte_run_doet_niet_mee():
    assert ae.measure(_run("1", "2026-08-02", minuten=30)) is None


def test_fiets_doet_niet_mee():
    act = _run("1", "2026-08-02")
    act["type"] = "Ride"
    assert ae.measure(act) is None


def test_te_weinig_tijd_in_band_is_niet_bruikbaar(monkeypatch):
    n = 3600
    hr = [170] * n
    for i in range(1000, 1060):  # slechts 60s in de band
        hr[i] = 145
    _patch_streams(monkeypatch, hr, [1000 / 300] * n)

    m = ae.measure(_run("1", "2026-08-02"))
    assert m["usable"] is False
    assert m["pace_sec"] is None


def test_trend_ziet_verbetering():
    """Dennis' echte reeks: 5:20 -> 5:10 -> 5:01 in twee weken."""
    metingen = [
        {"date": "2026-07-18", "pace_sec": 320, "samples_sec": 1321,
         "distance_km": 22.3, "usable": True},
        {"date": "2026-07-26", "pace_sec": 310, "samples_sec": 798,
         "distance_km": 25.0, "usable": True},
        {"date": "2026-08-02", "pace_sec": 301, "samples_sec": 540,
         "distance_km": 24.9, "usable": True},
    ]
    analyse = {"hr_band": (142, 150), "metingen": metingen}
    slope = ae._slope_sec_per_week(metingen)
    assert slope is not None
    assert slope < -5, f"duidelijke verbetering verwacht, kreeg {slope}"


def test_analyse_zonder_metingen_klaagt_niet():
    a = ae.analyze([])
    assert a["huidig"] is None
    assert a["richting"] == "onbekend"
    assert "Nog geen bruikbare meting" in a["samenvatting"]


def test_analyse_met_twee_metingen_geeft_geen_trend(monkeypatch):
    n = 3600
    _patch_streams(monkeypatch, [145] * n, [1000 / 300] * n)
    a = ae.analyze([_run("1", "2026-07-26"), _run("2", "2026-08-02")])
    assert len(a["metingen"]) == 2
    assert a["slope_sec_per_week"] is None
    assert a["richting"] == "te weinig data"


def test_fmt_pace():
    assert ae.fmt_pace(301) == "5:01/km"
    assert ae.fmt_pace(320) == "5:20/km"
    assert ae.fmt_pace(None) == "-"


def test_cache_scheidt_hr_banden(tmp_path, monkeypatch):
    """Bandwissel mag de meting van de andere band niet overschrijven.

    Migratie 008 had activity_id als enige primary key terwijl de lookup op
    (activity_id, hr_low, hr_high) ging — een bandwissel wiste dan stil de
    historie.
    """
    monkeypatch.setenv("SPORT_DB_PATH", str(tmp_path / "t.db"))
    import importlib

    import history_db
    importlib.reload(history_db)

    history_db.record_aerobic_efficiency(
        "a1", activity_date="2026-08-02", hr_low=142, hr_high=150,
        pace_sec=301, samples_sec=540, distance_km=24.9)
    history_db.record_aerobic_efficiency(
        "a1", activity_date="2026-08-02", hr_low=135, hr_high=145,
        pace_sec=318, samples_sec=900, distance_km=24.9)

    smal = history_db.get_aerobic_efficiency("a1", 142, 150)
    breed = history_db.get_aerobic_efficiency("a1", 135, 145)
    assert smal is not None and smal["pace_sec"] == 301
    assert breed is not None and breed["pace_sec"] == 318

    importlib.reload(history_db)


def test_streams_vraagt_alleen_wat_nodig_is(monkeypatch):
    """Zonder types-filter komen alle 15 streams mee; dat is pure bandbreedte."""
    import intervals_client

    gevraagd = {}

    def _fake(aid, types=None):
        gevraagd["types"] = types
        return _streams([145] * 3600, [1000 / 300] * 3600)

    monkeypatch.setattr(intervals_client, "get_activity_streams", _fake)
    ae.measure(_run("1", "2026-08-02"))
    assert gevraagd["types"] == ["velocity_smooth", "heartrate"]
