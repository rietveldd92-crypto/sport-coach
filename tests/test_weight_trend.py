"""Gewicht als prestatievariabele — trend, nooit één weging."""
import sys
from datetime import date, timedelta

import pytest

from agents import weight_trend


def _fake_api(rows):
    return type("API", (), {"get_wellness": staticmethod(lambda *_a, **_k: rows)})


def _row(days_ago: int, kg):
    d = date.today() - timedelta(days=days_ago)
    return {"id": d.isoformat(), "weight": kg}


def test_zonder_metingen_zwijgt_de_module(monkeypatch):
    monkeypatch.setitem(sys.modules, "intervals_client", _fake_api([]))

    r = weight_trend.analyze()

    assert r["latest"] is None
    assert r["kg_per_week"] is None
    assert "Geen gewichtsmetingen" in r["message"]


def test_trend_vergelijkt_twee_weekgemiddelden(monkeypatch):
    rows = [_row(d, 86.0) for d in range(0, 7)] + \
           [_row(d, 87.0) for d in range(7, 14)]
    monkeypatch.setitem(sys.modules, "intervals_client", _fake_api(rows))

    r = weight_trend.analyze()

    assert r["avg_recent"] == 86.0
    assert r["avg_prior"] == 87.0
    assert r["kg_per_week"] == -1.0


def test_te_snel_afvallen_wordt_benoemd(monkeypatch):
    rows = [_row(d, 85.0) for d in range(0, 7)] + \
           [_row(d, 87.0) for d in range(7, 14)]
    monkeypatch.setitem(sys.modules, "intervals_client", _fake_api(rows))

    assert "kost spiermassa" in weight_trend.analyze()["message"]


def test_gewichtsverlies_vertaalt_naar_seconden_per_km():
    """87 -> 84 kg is 3.45% massa; bij 0.8 tijdwinst per procent op 255 s/km."""
    gain = weight_trend.seconds_per_km_from_loss(87, 84, 255)

    assert 6.5 < gain < 7.5


def test_zwaarder_worden_levert_geen_winst():
    assert weight_trend.seconds_per_km_from_loss(87, 90, 255) == 0.0


def test_doelgewicht_is_de_pessimistische_bovengrens():
    """42:30 -> sub-40 puur uit massa: ~7% eraf, dus ruim 80 kg."""
    target = weight_trend.target_kg_for_pace(87, 255, 240)

    assert 79 < target < 82
