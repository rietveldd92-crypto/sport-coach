"""Tests voor _try_shift_before_replan scope-narrowing.

Bug die we fixen: bij elke availability-edit werden ALLE dagen met
over-capacity behandeld, ook pre-existing ones. Als Zaterdag al een
2,5u Z2 had met 60 min avail, faalde shift altijd en viel de UI
terug op full replan — zelfs als de gebruiker alleen Maandag aanpaste.

Deze tests simuleren de helper met een mock intervals_client zodat we
de scope-logica kunnen valideren zonder echte API.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest


MONDAY = date(2026, 4, 20)
DAYS = [MONDAY + timedelta(days=i) for i in range(7)]
ISO = [d.isoformat() for d in DAYS]
MON, TUE, WED, THU, FRI, SAT, SUN = ISO


def _ev(eid, date_iso, name, sport="Run", minutes=60):
    return {
        "id": eid,
        "name": name,
        "type": sport,
        "category": "WORKOUT",
        "start_date_local": f"{date_iso}T00:00:00",
        "moving_time": minutes * 60,
        "load_target": 50,
        "is_note": None,
    }


@pytest.fixture
def helper(monkeypatch):
    """Laadt app._try_shift_before_replan met gemockte intervals_client."""
    # Mock intervals_client ZONDER hem echt te importeren (Streamlit niet nodig)
    mock_api = MagicMock()
    monkeypatch.setitem(sys.modules, "intervals_client", mock_api)

    # Laadt de helper via importlib uit app.py zonder top-level Streamlit
    # te triggeren: extract de functie-source en exec in nieuwe namespace.
    from pathlib import Path
    src = Path(__file__).parent.parent / "app.py"
    text = src.read_text(encoding="utf-8")
    # Knip alleen de functiedefinitie eruit
    start = text.index("def _try_shift_before_replan(")
    # Zoek het einde: de volgende top-level def na start
    end = text.index("\ndef _resolve_phase_tss_range", start)
    fn_src = text[start:end]

    ns: dict = {}
    exec(fn_src, ns)
    return ns["_try_shift_before_replan"], mock_api


def test_geen_overflow_geen_actie(helper):
    """Avail verhoogt; geen shift nodig."""
    fn, api = helper
    api.get_events.return_value = [_ev("e1", TUE, "Z2 run 60 min", minutes=60)]
    new_avail = {d: 120 for d in ISO}
    prev_avail = {d: 60 for d in ISO}
    res = fn(MONDAY, new_avail, state={}, prev_avail=prev_avail)
    assert res["applied"] == 0
    assert res["needs_replan"] is False
    assert res["targets"] == []


def test_pre_existing_overflow_wordt_genegeerd(helper):
    """Zaterdag heeft al 150 min plan op 60 min avail; user past Maandag
    aan (Mon blijft 60). Zaterdag mag NIET getriggerd worden omdat de
    avail op Zaterdag niet verlaagd is deze sessie."""
    fn, api = helper
    api.get_events.return_value = [
        _ev("e1", SAT, "Z2 endurance 150 min", sport="VirtualRide", minutes=150),
    ]
    new_avail = {d: 60 for d in ISO}
    # prev: zelfde avail → zaterdag is pre-existing, niet deze edit
    prev_avail = {d: 60 for d in ISO}
    res = fn(MONDAY, new_avail, state={}, prev_avail=prev_avail)
    assert res["applied"] == 0
    assert res["needs_replan"] is False  # géén full replan!
    assert res["targets"] == []


def test_verlaagde_dag_wordt_aangepakt(helper):
    """Dinsdag had 120, nu 30. Bevat run 60min + bike 60min. Shift één."""
    fn, api = helper
    api.get_events.return_value = [
        _ev("e1", TUE, "Z2 duurloop 60 min", sport="Run", minutes=60),
        _ev("e2", TUE, "Z2 endurance 60 min", sport="VirtualRide", minutes=60),
    ]
    api.update_event.return_value = {}
    new_avail = {d: 120 for d in ISO}
    new_avail[TUE] = 60  # verlaagd!
    prev_avail = {d: 120 for d in ISO}  # was 120 op TUE
    res = fn(MONDAY, new_avail, state={}, prev_avail=prev_avail)
    # Eén shift uitgevoerd (één past op TUE=60, ander verhuist)
    assert res["applied"] == 1
    assert res["needs_replan"] is False
    assert TUE in res["targets"]
    # update_event is aangeroepen
    api.update_event.assert_called_once()


def test_verhoogde_dag_telt_niet_als_target(helper):
    """Als avail omhoog gaat maar er toch overflow is (pre-existing),
    niet triggeren."""
    fn, api = helper
    api.get_events.return_value = [
        _ev("e1", SAT, "Z2 endurance 150 min", sport="VirtualRide", minutes=150),
    ]
    new_avail = {d: 60 for d in ISO}
    new_avail[SAT] = 90  # omhoog maar still not enough
    prev_avail = {d: 60 for d in ISO}
    res = fn(MONDAY, new_avail, state={}, prev_avail=prev_avail)
    # Zaterdag verhoogd, niet verlaagd → geen target
    assert res["targets"] == []
    assert res["needs_replan"] is False


def test_geen_prev_avail_fallt_terug_op_oud_gedrag(helper):
    """Zonder prev_avail snapshot: elke overflow telt (oud gedrag, fragieler)."""
    fn, api = helper
    api.get_events.return_value = [
        _ev("e1", TUE, "Z2 run 60 min", sport="Run", minutes=60),
    ]
    api.update_event.return_value = {}
    new_avail = {d: 120 for d in ISO}
    new_avail[TUE] = 30  # overflow
    res = fn(MONDAY, new_avail, state={}, prev_avail=None)
    # Zonder snapshot: TUE telt toch als target
    assert TUE in res["targets"]


def test_shift_kan_niet_dan_needs_replan(helper):
    """Dinsdag verlaagd maar geen plek om Z2 heen te shiften."""
    fn, api = helper
    # Dinsdag: run + bike samen 120 min. Alle andere dagen al vol.
    events = [_ev("e_tue_run", TUE, "Z2 run 60", minutes=60),
              _ev("e_tue_bike", TUE, "Z2 endurance 60", sport="VirtualRide", minutes=60)]
    # Andere dagen elk 60 min vol
    for d_iso in (MON, WED, THU, FRI, SAT, SUN):
        events.append(_ev(f"busy_{d_iso}", d_iso, "Z2 busy 60",
                          sport="VirtualRide", minutes=60))
    api.get_events.return_value = events
    new_avail = {d: 60 for d in ISO}
    new_avail[TUE] = 60  # niet verlaagd in avail, maar 60+60=120 past niet op 60
    prev_avail = {d: 60 for d in ISO}
    prev_avail[TUE] = 120  # was 120, nu 60 → verlaagd
    new_avail[TUE] = 60
    res = fn(MONDAY, new_avail, state={}, prev_avail=prev_avail)
    # Shift faalt (geen plek) → needs_replan
    assert res["needs_replan"] is True
    assert TUE in res["targets"]
