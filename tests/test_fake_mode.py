"""INTERVALS_FAKE-modus (Fase 4): offline fixture-data via intervals_client.

De env-flag laat intervals_client bij import de gedeelde fixture uit
core.fake_intervals installeren, zodat frontend-dev en smoke-tests
zonder netwerk werken. Hier testen we dat pad end-to-end: flag aan →
install_fake → /api/today en /api/week geven 200 met fixture-data.
"""
from __future__ import annotations

import importlib
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

import config
import intervals_client
from core import fake_intervals

TODAY = date.today()
MONDAY = TODAY - timedelta(days=TODAY.weekday())


@pytest.fixture()
def fake_client(monkeypatch):
    """App-client met INTERVALS_FAKE aan, zonder echte tokens/netwerk."""
    monkeypatch.setattr(config, "_from_streamlit", lambda name: None)
    for var in ("API_TOKEN", "TP_SYNC_ENABLED", "SCHEDULER_ENABLED"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("INTERVALS_FAKE", "1")
    assert fake_intervals.fake_enabled()

    # Zelfde pad als een verse `uvicorn`-start met de flag: install_fake
    # patcht intervals_client in-place. Originele functies herstellen we
    # na de test zodat de rest van de suite onaangetast blijft.
    originals = {name: getattr(intervals_client, name)
                 for name in fake_intervals.PATCHED}
    mock = fake_intervals.install_fake()
    assert intervals_client.FAKE_MODE is True

    from api.main import create_app

    with TestClient(create_app()) as client:
        yield client, mock

    for name, fn in originals.items():
        setattr(intervals_client, name, fn)
    intervals_client.FAKE_MODE = False


def test_flag_detection(monkeypatch):
    monkeypatch.delenv("INTERVALS_FAKE", raising=False)
    assert not fake_intervals.fake_enabled()
    for raw in ("1", "true", "YES", "On"):
        monkeypatch.setenv("INTERVALS_FAKE", raw)
        assert fake_intervals.fake_enabled()
    monkeypatch.setenv("INTERVALS_FAKE", "0")
    assert not fake_intervals.fake_enabled()


def test_import_time_install(monkeypatch):
    """Flag gezet vóór import → module patcht zichzelf (uvicorn-pad)."""
    monkeypatch.setenv("INTERVALS_FAKE", "1")
    originals = {name: getattr(intervals_client, name)
                 for name in fake_intervals.PATCHED}
    try:
        mod = importlib.reload(intervals_client)
        assert mod.FAKE_MODE is True
        events = mod.get_events(MONDAY, MONDAY + timedelta(days=6))
        assert any(e["id"] == "e_today" for e in events)
    finally:
        monkeypatch.delenv("INTERVALS_FAKE", raising=False)
        importlib.reload(intervals_client)
        for name, fn in originals.items():
            setattr(intervals_client, name, fn)
        intervals_client.FAKE_MODE = False


def test_today_and_week_serve_fixture_data(fake_client):
    client, _mock = fake_client

    r = client.get("/api/today")
    assert r.status_code == 200
    body = r.json()
    assert body["date"] == TODAY.isoformat()
    assert body["workout"]["event"]["id"] == "e_today"
    assert body["workout"]["done"] is False
    assert body["tomorrow"][0]["event"]["id"] == "e_tomorrow"
    # Header-badge: injury_guard-status aanwezig (groen op verse staat).
    assert body["injury_guard"]["status"] in {"groen", "geel", "rood"}

    r = client.get(f"/api/week/{MONDAY.isoformat()}")
    assert r.status_code == 200
    week = r.json()
    assert week["week_start"] == MONDAY.isoformat()
    ids = {i["event"]["id"] for i in week["items"]}
    assert {"e_done", "e_today"} <= ids
    tomorrow = TODAY + timedelta(days=1)
    if tomorrow <= MONDAY + timedelta(days=6):
        assert "e_tomorrow" in ids
    else:
        next_monday = tomorrow - timedelta(days=tomorrow.weekday())
        r_next = client.get(f"/api/week/{next_monday.isoformat()}")
        assert r_next.status_code == 200
        next_ids = {i["event"]["id"] for i in r_next.json()["items"]}
        assert "e_tomorrow" in next_ids
    assert len(week["availability"]) == 7


def test_availability_override_survives_plan_week(fake_client):
    """Regressie (2026-07-20): beschikbaarheid zetten → week herplannen
    mocht de zojuist gezette overrides niet wissen. De plan-flow doet
    meerdere load→save-state-cycli (injury_guard, load_manager, weeklog);
    zolang save_state availability terugschreef, verdween elke override
    die niet in de (stale) snapshot zat — en plande de week op niets."""
    client, _mock = fake_client

    # Volgende week plannen: geen fixture-events, dus een schone plan-run.
    next_monday = MONDAY + timedelta(days=7)
    days = [next_monday + timedelta(days=i) for i in range(7)]

    # Beschikbaarheid via de API zoals de AvailabilitySheet dat doet.
    for d in days[:6]:
        r = client.put(
            f"/api/availability/override/{d.isoformat()}",
            json={"slots": [{"start": "07:00", "end": "09:00", "context": "any"}]},
        )
        assert r.status_code == 200
    r = client.put(
        f"/api/availability/override/{days[6].isoformat()}",
        json={"slots": []},  # zondag rustdag
    )
    assert r.status_code == 200

    r = client.post(f"/api/week/{next_monday.isoformat()}/plan")
    assert r.status_code == 200
    plan = r.json()
    codes = {w.get("code") for w in plan.get("warnings") or []}
    assert "no_availability" not in codes
    assert plan["planned_sessions"] > 0

    # Overrides staan er na het plannen nog exact zo in.
    r = client.get(f"/api/week/{next_monday.isoformat()}")
    assert r.status_code == 200
    avail = r.json()["availability"]
    for d in days[:6]:
        assert avail[d.isoformat()] == [
            {"start": "07:00", "end": "09:00", "context": "any"}
        ], f"override voor {d} is verdwenen na plan"
    assert avail[days[6].isoformat()] == []
