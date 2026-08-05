"""De symptoomvrij-teller telde aanroepen in plaats van dagen.

Zonder signaalhistorie deed `analyze()` `days_symptom_free + 1` per aanroep.
De poorten voor strides (14) en tempo (21) waren daarmee onbereikbaar voor
een atleet die nooit een klacht had gemeld — op 28 juli 2026 stond de teller
op 4 bij 999 dagen sinds het laatste signaal, met alles op slot.
"""
from datetime import date, timedelta

import pytest

from agents import injury_guard


class _PinnedDate(date):
    @classmethod
    def today(cls):
        return cls(2026, 8, 5)


def _state(injury: dict) -> dict:
    return {"injury": injury, "signal_buffer": {}}


@pytest.fixture(autouse=True)
def _no_disk(monkeypatch):
    """Nooit naar state.json schrijven tijdens deze tests."""
    monkeypatch.setattr(injury_guard, "_save_state", lambda _s: None)


def test_zonder_historie_staan_de_poorten_open(monkeypatch):
    monkeypatch.setattr(injury_guard, "_load_state", lambda: _state({
        "active_signals": [], "history": [], "days_symptom_free": 4,
    }))

    r = injury_guard.analyze()

    assert r["days_symptom_free"] >= 21
    assert r["strides_allowed"] is True
    assert r["tempo_allowed"] is True


def test_een_gemeld_signaal_zet_de_teller_terug_op_nul(monkeypatch):
    monkeypatch.setattr(injury_guard, "_load_state", lambda: _state({
        "active_signals": [], "history": [], "days_symptom_free": 40,
    }))

    r = injury_guard.analyze(feedback_signals=["knie_pijn"])

    assert r["days_symptom_free"] == 0
    assert r["strides_allowed"] is False
    assert r["tempo_allowed"] is False


def test_met_historie_telt_de_gewone_teller(monkeypatch):
    """Wie wél een klacht heeft gehad, doorloopt het terugkeerprotocol."""
    monkeypatch.setattr(injury_guard, "date", _PinnedDate)
    signal_day = (_PinnedDate.today() - timedelta(days=6)).isoformat()
    monkeypatch.setattr(injury_guard, "_load_state", lambda: _state({
        "active_signals": [],
        "history": [{"date": signal_day, "signals": ["knie_pijn"],
                     "type": "direct"}],
        "last_signal_date": signal_day,
        "days_symptom_free": 5,
    }))

    r = injury_guard.analyze()

    assert r["days_symptom_free"] < 14
    assert r["strides_allowed"] is False
