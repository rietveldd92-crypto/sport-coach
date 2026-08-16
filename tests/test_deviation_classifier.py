"""Tests voor agents.deviation_classifier."""
from datetime import date

from agents.deviation_classifier import classify_deviation, detect_deviations


TODAY = date(2026, 4, 15)


def _ev(eid="e1", etype="Run", name="Duurloop", tss=60, dt="2026-04-14", dur_sec=3600):
    return {
        "id": eid,
        "type": etype,
        "name": name,
        "load_target": tss,
        "start_date_local": f"{dt}T09:00:00",
        "duration": dur_sec,
        "category": "WORKOUT",
    }


def _act(aid="a1", atype="Run", tss=60, dt="2026-04-14", moving=3600):
    return {
        "id": aid,
        "type": atype,
        "icu_training_load": tss,
        "start_date_local": f"{dt}T09:05:00",
        "moving_time": moving,
    }


def test_none_returns_none():
    assert classify_deviation(None, None, today=TODAY) is None


def test_extra_ongeplande_activiteit():
    dev = classify_deviation(None, _act(tss=50), today=TODAY)
    assert dev is not None
    assert dev.type == "extra"
    assert dev.tss_actual == 50


def test_skipped_gisteren_sacred():
    planned = _ev(name="Lange duurloop", tss=120, dt="2026-04-14")
    dev = classify_deviation(planned, None, today=TODAY)
    assert dev.type == "skipped"
    assert dev.sacred is True
    assert dev.severity in {"medium", "high"}


def test_skipped_gisteren_soft():
    planned = _ev(name="Z2 rustige duurloop", tss=40, dt="2026-04-14")
    dev = classify_deviation(planned, None, today=TODAY)
    assert dev.type == "skipped"
    assert dev.sacred is False


def test_skipped_toekomst_geen_deviation():
    planned = _ev(dt="2026-04-20")
    assert classify_deviation(planned, None, today=TODAY) is None


def test_replaced_harder():
    planned = _ev(tss=60)
    actual = _act(tss=145)  # > 1.3 * 60 = 78 → harder
    dev = classify_deviation(planned, actual, today=TODAY)
    assert dev.type == "replaced_harder"
    assert dev.severity == "high"


def test_replaced_easier_sacred():
    planned = _ev(name="Drempel 4x1km", tss=80)
    actual = _act(tss=30)  # < 0.6 * 80 = 48
    dev = classify_deviation(planned, actual, today=TODAY)
    assert dev.type == "replaced_easier"
    assert dev.sacred is True


def test_longer_binnen_tss_band():
    planned = _ev(tss=60, dur_sec=3600)  # 60 min
    actual = _act(tss=62, moving=5400)  # 90 min, TSS binnen tolerantie
    dev = classify_deviation(planned, actual, today=TODAY)
    assert dev.type == "longer"


def test_within_tolerance_returns_none_type():
    planned = _ev(tss=60, dur_sec=3600)
    actual = _act(tss=58, moving=3700)
    dev = classify_deviation(planned, actual, today=TODAY)
    assert dev.type == "none"


def test_detect_deviations_verwerkt_hele_week():
    events = [
        _ev(eid="e_skip", name="Lange duurloop", tss=120, dt="2026-04-13"),
        _ev(eid="e_ok", name="Z2 easy", tss=40, dt="2026-04-14"),
    ]
    activities = [
        _act(aid="a_ok", tss=42, dt="2026-04-14"),
        # Extra: ongeplande rit
        {
            "id": "a_extra",
            "type": "Ride",
            "icu_training_load": 55,
            "start_date_local": "2026-04-14T18:00:00",
            "moving_time": 3000,
            "name": "Avondrit",
        },
    ]
    devs = detect_deviations(events, activities, today=TODAY)
    types = sorted(d.type for d in devs)
    # e_skip → skipped (gisteren), a_extra → extra
    assert "skipped" in types
    assert "extra" in types
