"""Een vastgezette sessie overleeft een herplanning van de week.

De aanleiding: de zondagavond-scheduler draaide, verving alle workouts van
de week, en nam daarmee de marathon-bloksessie van zondag mee — een
afspraak die niet uit dit systeem komt en dus nergens beschermd was.
"""
from datetime import date, timedelta

import pytest

from agents import availability, session_lock
from core import availability_v2 as av2
from tests.mock_intervals import MockIntervals, _event, install


MONDAY = date(2026, 9, 7)
SUNDAY = MONDAY + timedelta(days=6)


def _session(name: str, day: str) -> dict:
    return {
        "naam": name,
        "type": "run_threshold_short",
        "duur_min": 60,
        "tss_geschat": 60,
        "sport": "Run",
        "beschrijving": "- 60m 4:20/km Pace",
        "dag": day,
        "plaatsing_reden": "test",
    }


# ── markering ─────────────────────────────────────────────────────────────

def test_markering_telt_in_naam_en_beschrijving():
    assert session_lock.is_pinned({"name": "[VAST] Marathon bloksessie"})
    assert session_lock.is_pinned(
        {"name": "Marathon bloksessie", "description": "[VAST] groepstraining"})
    assert not session_lock.is_pinned({"name": "Drempel 4x2km"})
    assert not session_lock.is_pinned(None)


def test_markering_is_hoofdletterongevoelig():
    assert session_lock.is_pinned({"name": "[vast] Bloksessie"})


def test_strip_marker_haalt_alle_markeringen_weg():
    assert session_lock.strip_marker("[VAST] [VAST] Bloksessie") == "Bloksessie"
    assert session_lock.strip_marker(None) == ""


def test_pinned_day_names_kijkt_alleen_binnen_de_week():
    events = [
        _event("a", SUNDAY, "[VAST] Marathon bloksessie"),
        _event("b", MONDAY + timedelta(days=14), "[VAST] Later"),
        _event("c", MONDAY, "Drempel 4x2km"),
    ]
    assert session_lock.pinned_day_names(events, MONDAY) == ["zondag"]


# ── planner laat hem staan ────────────────────────────────────────────────

def test_weekplanner_wist_een_vastgezette_sessie_niet(monkeypatch):
    from agents import week_planner

    mock = MockIntervals(today=MONDAY)
    mock.events = [
        _event("blok", SUNDAY, "[VAST] Marathon bloksessie", "Run", 180),
        _event("los", MONDAY + timedelta(days=2), "Oude drempel", "Run", 70),
    ]
    install(monkeypatch, mock)
    for weekday in range(7):
        av2.set_pattern(weekday, [("07:00", "09:00")])

    week_planner.build_week(
        MONDAY,
        [_session("Nieuwe drempel", "dinsdag")],
        [],
        injury_guard={"status": "groen", "strength_allowed": False},
        load_manager={"current_phase": "basis_I", "recommended_weekly_tss": 200,
                      "ctl": 40, "atl": 40, "tsb": 0},
        dry_run=False,
        preplanned=True,
        today=MONDAY,
    )

    assert not any(call[:2] == ("delete_event", "blok") for call in mock.calls)
    assert any(call[:2] == ("delete_event", "los") for call in mock.calls)
    assert any(e["name"] == "[VAST] Marathon bloksessie" for e in mock.events)


# ── dag blijft bezet ──────────────────────────────────────────────────────

def test_vastgezette_dag_is_bezet_voor_de_planner(monkeypatch):
    fake = type("API", (), {"get_events": staticmethod(
        lambda *_a, **_k: [_event("blok", SUNDAY, "[VAST] Marathon bloksessie")])})
    monkeypatch.setitem(__import__("sys").modules, "intervals_client", fake)

    assert availability.get_pinned_day_names(MONDAY) == ["zondag"]


def test_gewone_workout_blokkeert_de_dag_niet(monkeypatch):
    fake = type("API", (), {"get_events": staticmethod(
        lambda *_a, **_k: [_event("x", SUNDAY, "Long run 32 km")])})
    monkeypatch.setitem(__import__("sys").modules, "intervals_client", fake)

    assert availability.get_pinned_day_names(MONDAY) == []


def test_onbereikbare_api_blokkeert_de_planner_niet(monkeypatch):
    def _boom(*_a, **_k):
        raise RuntimeError("intervals.icu down")

    fake = type("API", (), {"get_events": staticmethod(_boom)})
    monkeypatch.setitem(__import__("sys").modules, "intervals_client", fake)

    assert availability.get_pinned_day_names(MONDAY) == []


# ── solver verschuift hem niet ────────────────────────────────────────────

def test_solver_ziet_een_vastgezette_sessie_als_locked():
    from core import replan

    movable = [_event("blok", SUNDAY, "[VAST] Marathon bloksessie")]
    _, _, locked = replan._solver_inputs(movable, {})
    assert locked == {"blok"}


def test_solver_laat_een_gewone_sessie_vrij():
    from core import replan

    movable = [_event("los", SUNDAY, "Long run 32 km")]
    _, _, locked = replan._solver_inputs(movable, {})
    assert locked == set()


# ── vastzetten en vrijgeven ───────────────────────────────────────────────

def test_pin_day_markeert_alleen_de_workouts_van_die_dag(monkeypatch):
    mock = MockIntervals(today=MONDAY)
    mock.events = [
        _event("blok", SUNDAY, "Marathon bloksessie", "Run", 180),
        _event("zat", MONDAY + timedelta(days=5), "Easy run", "Run", 45),
    ]
    install(monkeypatch, mock)

    geraakt = session_lock.pin_day(SUNDAY)

    assert [e["name"] for e in geraakt] == ["[VAST] Marathon bloksessie"]
    namen = {e["id"]: e["name"] for e in mock.events}
    assert namen["blok"] == "[VAST] Marathon bloksessie"
    assert namen["zat"] == "Easy run"


def test_pin_event_is_idempotent(monkeypatch):
    mock = MockIntervals(today=MONDAY)
    mock.events = [_event("blok", SUNDAY, "[VAST] Marathon bloksessie")]
    install(monkeypatch, mock)

    session_lock.pin_day(SUNDAY)

    assert mock.events[0]["name"] == "[VAST] Marathon bloksessie"
    assert not any(call[0] == "update_event" for call in mock.calls)


def test_unpin_day_geeft_de_sessie_weer_vrij(monkeypatch):
    mock = MockIntervals(today=MONDAY)
    mock.events = [_event("blok", SUNDAY, "[VAST] Marathon bloksessie")]
    install(monkeypatch, mock)

    session_lock.unpin_day(SUNDAY)

    assert mock.events[0]["name"] == "Marathon bloksessie"


# ── adapt_week verplaatst hem niet ────────────────────────────────────────

def test_adapt_week_verplaatst_een_gemiste_vastgezette_sessie_niet():
    from agents.adapt_week import adapt_week
    from agents.models import Deviation

    blok = {
        "id": "blok", "name": "[VAST] Marathon bloksessie", "type": "Run",
        "load_target": 180, "duration": 10800, "category": "WORKOUT",
        "start_date_local": f"{MONDAY + timedelta(days=1)}T09:00:00",
    }
    dev = Deviation(
        type="skipped", planned_event_id="blok", tss_planned=180,
        tss_actual=0, severity="high",
        planned_date=(MONDAY + timedelta(days=1)).isoformat(), sacred=True,
    )

    result = adapt_week([blok], [dev], {"load": {"ctl_estimate": 49.0}},
                        today=MONDAY + timedelta(days=2))

    assert result.modifications == []
    assert result.new_events == []
    assert "vast in de agenda" in result.narrative
