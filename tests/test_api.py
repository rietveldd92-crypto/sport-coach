"""Integratietests voor de FastAPI-laag (Fase 3, UPGRADE_PLAN §8 DoD).

Elke endpoint minstens één happy path + auth-afwijzing, tegen de
gemockte intervals.icu (tests/mock_intervals.py). Dit is de e2e-dekking
die het UPGRADE_PLAN als Definition of Done noemt:

- /move: harde assert op diff-minimaliteit (precies 1 sessie verhuist);
- /checkin: blessuresignaal beïnvloedt de injury_guard-status.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

import config
import history_db
import shared
from core import availability_v2 as av2
from tests.mock_intervals import MockIntervals, install

TODAY = date.today()
MONDAY = TODAY - timedelta(days=TODAY.weekday())
NEXT_MONDAY = MONDAY + timedelta(days=7)


def _seed_state() -> None:
    shared.save_state({
        "injury": {
            "active_signals": [],
            "last_signal_date": None,
            "days_symptom_free": 30,
            "history": [],
            "return_from_injury": False,
        },
        "load": {
            "ctl_estimate": 48.0,
            "atl_estimate": 44.0,
            "tsb_estimate": 4.0,
            "weekly_tss_target": 400,
            "last_calculated": TODAY.isoformat(),
        },
        "preferences": {"runs_back_to_back_ok": False},
        "weekly_log": [],
        "current_phase": "accumulatie_II",
        "race_date": "2026-10-18",
    })


def _seed_availability() -> None:
    for weekday in range(7):
        av2.set_pattern(weekday, [("07:00", "09:40")])


@pytest.fixture()
def env(monkeypatch):
    """Gecontroleerde config: geen st.secrets, geen tokens/flags uit .env."""
    monkeypatch.setattr(config, "_from_streamlit", lambda name: None)
    for var in ("API_TOKEN", "TP_SYNC_ENABLED", "SCHEDULER_ENABLED",
                "GOOGLE_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    # Geen echte Gemini-calls vanuit tests, ook niet als er ergens
    # toch een key rondslingert.
    from agents import feedback_engine
    monkeypatch.setattr(feedback_engine, "gemini_available", lambda: False)
    yield monkeypatch


@pytest.fixture()
def mock_api(env):
    return install(env, MockIntervals())


@pytest.fixture()
def client(mock_api):
    _seed_state()
    _seed_availability()
    from api.main import create_app

    with TestClient(create_app()) as c:
        yield c


# ── AUTH ──────────────────────────────────────────────────────────────────

AUTH_CHECK_PATHS = [
    "/api/today",
    f"/api/week/{MONDAY.isoformat()}",
    "/api/season",
    "/api/trends",
    "/api/availability/pattern",
    f"/api/availability/override/{TODAY.isoformat()}",
    "/api/goals",
    "/api/coach/feedback?event_id=e_done",
]


@pytest.mark.parametrize("path", AUTH_CHECK_PATHS)
def test_auth_rejected_without_token(mock_api, env, path):
    """API_TOKEN gezet → request zonder/met fout token wordt geweigerd."""
    env.setenv("API_TOKEN", "geheim-token")
    _seed_state()
    from api.main import create_app

    with TestClient(create_app()) as client:
        assert client.get(path).status_code == 401
        r = client.get(path, headers={"Authorization": "Bearer verkeerd"})
        assert r.status_code == 401


def test_auth_accepted_with_token_and_post(mock_api, env):
    env.setenv("API_TOKEN", "geheim-token")
    _seed_state()
    from api.main import create_app

    with TestClient(create_app()) as client:
        ok = client.get("/api/today",
                        headers={"Authorization": "Bearer geheim-token"})
        assert ok.status_code == 200
        # POST zonder token faalt ook (dependency vóór endpoint).
        r = client.post("/api/checkin", json={"sleep_score": 4})
        assert r.status_code == 401


# ── TODAY ─────────────────────────────────────────────────────────────────

def test_today_happy_path(client):
    r = client.get("/api/today")
    assert r.status_code == 200
    body = r.json()
    assert body["date"] == TODAY.isoformat()
    assert body["workout"]["event"]["id"] == "e_today"
    assert body["workout"]["done"] is False
    assert "coach_note" in body["workout"]
    assert body["checkin"]["done"] is False
    tomorrow_ids = [t["event"]["id"] for t in body["tomorrow"]]
    assert "e_tomorrow" in tomorrow_ids


def test_today_intervals_down_gives_502(client, mock_api):
    mock_api.fail_events = True
    r = client.get("/api/today")
    assert r.status_code == 502
    assert "intervals.icu" in r.json()["detail"]


# ── WEEK ──────────────────────────────────────────────────────────────────

def test_week_view(client):
    r = client.get(f"/api/week/{NEXT_MONDAY.isoformat()}")
    assert r.status_code == 200
    body = r.json()
    assert body["week_start"] == NEXT_MONDAY.isoformat()
    ids = {i["event"]["id"] for i in body["items"]}
    assert {"e_nw_run", "e_nw_bike", "e_nw_long"} <= ids
    # Availability-slots per dag (7 dagen, uit het patroon)
    assert len(body["availability"]) == 7
    first_day = body["availability"][NEXT_MONDAY.isoformat()]
    assert first_day == [{"start": "07:00", "end": "09:40", "context": "any"}]


def test_week_plan_creates_events(client, mock_api):
    r = client.post(f"/api/week/{NEXT_MONDAY.isoformat()}/plan")
    assert r.status_code == 200
    body = r.json()
    assert body["planned_sessions"] > 0
    created = [c for c in mock_api.calls if c[0] == "create_event"]
    assert created, "plan-flow hoort events naar intervals.icu te schrijven"


# ── PLACEMENTS: MOVE (diff-minimaliteit) + SWAP ───────────────────────────

def test_move_diff_is_minimal(client, mock_api):
    """Drag van de threshold-rit wo → do: precies 1 sessie verhuist."""
    thursday = NEXT_MONDAY + timedelta(days=3)
    r = client.post(
        "/api/placements/e_nw_bike/move",
        json={"target_date": thursday.isoformat()},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("OPTIMAL", "FEASIBLE")
    assert body["applied"] is False
    # Diff-minimaliteit: alléén de gesleepte sessie verhuist.
    assert len(body["diff"]) == 1
    mv = body["diff"][0]
    assert mv["event_id"] == "e_nw_bike"
    assert mv["from"] == (NEXT_MONDAY + timedelta(days=2)).isoformat()
    assert mv["to"] == thursday.isoformat()
    # Preview → niets gemuteerd in intervals.icu
    assert not [c for c in mock_api.calls if c[0] == "update_event"]


def test_move_apply_writes_and_locks(client, mock_api):
    thursday = NEXT_MONDAY + timedelta(days=3)
    r = client.post(
        f"/api/placements/e_nw_bike/move?apply=true",
        json={"target_date": thursday.isoformat()},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["applied"] is True
    event = next(e for e in mock_api.events if e["id"] == "e_nw_bike")
    assert event["start_date_local"][:10] == thursday.isoformat()
    placement = history_db.get_placement("e_nw_bike")
    assert placement is not None
    assert placement["date"] == thursday.isoformat()
    assert placement["locked"] == 1


def test_move_unknown_event_404(client):
    r = client.post(
        "/api/placements/bestaat_niet/move",
        json={"target_date": (NEXT_MONDAY + timedelta(days=3)).isoformat()},
    )
    assert r.status_code == 404


def test_swap_happy_path(client, mock_api):
    r = client.post("/api/placements/e_today/swap",
                    json={"category": "makkelijker"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["chosen"]["naam"]
    assert body["undo"]["orig_name"] == "Easy run 40 min"
    event = next(e for e in mock_api.events if e["id"] == "e_today")
    assert event["name"] == body["chosen"]["naam"]


def test_swap_unknown_event_404(client):
    r = client.post("/api/placements/bestaat_niet/swap",
                    json={"category": "harder"})
    assert r.status_code == 404


# ── AVAILABILITY ──────────────────────────────────────────────────────────

def test_availability_pattern_roundtrip(client):
    r = client.put("/api/availability/pattern", json={
        "days": {"0": [{"start": "06:00", "end": "07:30"}]},
    })
    assert r.status_code == 200
    pattern = r.json()["pattern"]
    assert pattern["0"] == [{"slot_start": "06:00", "slot_end": "07:30",
                             "context": "any"}]
    # GET geeft hetzelfde terug
    r2 = client.get("/api/availability/pattern")
    assert r2.json()["pattern"]["0"][0]["slot_start"] == "06:00"


def test_availability_override_roundtrip(client):
    day = (TODAY + timedelta(days=2)).isoformat()
    r = client.put(f"/api/availability/override/{day}", json={
        "slots": [{"start": "18:00", "end": "19:30", "context": "indoor_only"}],
    })
    assert r.status_code == 200
    assert r.json()["slots"] == [
        {"start": "18:00", "end": "19:30", "context": "indoor_only"}]

    # Rustdag-marker
    r = client.put(f"/api/availability/override/{day}", json={"slots": []})
    assert r.json()["slots"] == []

    # Override wissen → terug naar patroon (geen override meer)
    r = client.put(f"/api/availability/override/{day}", json={"slots": None})
    assert r.json()["slots"] is None


def test_availability_override_save_replaces_existing_rows(client):
    day = (TODAY + timedelta(days=3)).isoformat()
    r = client.put(f"/api/availability/override/{day}", json={
        "slots": [
            {"start": "06:00", "end": "07:00"},
            {"start": "18:00", "end": "19:00"},
        ],
    })
    assert r.status_code == 200

    r = client.put(f"/api/availability/override/{day}", json={
        "slots": [{"start": "07:00", "end": "08:00"}],
    })
    assert r.status_code == 200
    assert r.json()["slots"] == [
        {"start": "07:00", "end": "08:00", "context": "any"}]

    with history_db._connect() as conn:
        rows = conn.execute(
            "SELECT slot_start, slot_end FROM availability_override"
            " WHERE date = ? ORDER BY slot_start",
            (day,),
        ).fetchall()
    assert [(r["slot_start"], r["slot_end"]) for r in rows] == [
        ("07:00", "08:00")]


def test_fixed_sessions_crud_roundtrip(client):
    r = client.put("/api/fixed-sessions/1", json={
        "name": "Forenzen-rit",
        "sport": "VirtualRide",
        "duration_min": 100,
        "if_estimate": 0.65,
        "enabled": True,
    })
    assert r.status_code == 200
    body = r.json()["fixed_session"]
    assert body["weekday"] == 1
    assert body["duration_min"] == 100
    assert body["enabled"] == 1

    listed = client.get("/api/fixed-sessions").json()["fixed_sessions"]
    assert [s["weekday"] for s in listed] == [1]

    r = client.delete("/api/fixed-sessions/1")
    assert r.status_code == 200
    assert client.get("/api/fixed-sessions").json()["fixed_sessions"] == []


# ── GOALS + SEASON ────────────────────────────────────────────────────────

def test_goals_create_generates_macroplan(client):
    event_date = (TODAY + timedelta(weeks=18)).isoformat()
    r = client.post("/api/goals", json={
        "type": "10k", "sport": "run", "event_date": event_date,
        "target_value": "0:42:00",
    })
    assert r.status_code == 201
    body = r.json()
    goal_id = body["goal"]["id"]
    assert body["generation"]["plan_weeks"] > 0

    listed = client.get("/api/goals").json()["goals"]
    assert [g["id"] for g in listed] == [goal_id]

    # Tweede actief A-doel → 409
    r2 = client.post("/api/goals", json={
        "type": "marathon", "sport": "run", "event_date": event_date,
    })
    assert r2.status_code == 409

    # Rolling re-periodisatie
    r3 = client.post(f"/api/goals/{goal_id}/regenerate")
    assert r3.status_code == 200
    assert r3.json()["status"] in (
        "within_band", "replanned", "injury_adjusted", "no_goal")

    # Verwijderen
    assert client.delete(f"/api/goals/{goal_id}").status_code == 204
    assert client.get("/api/goals").json()["goals"] == []
    assert client.delete(f"/api/goals/{goal_id}").status_code == 404


def test_season_view(client):
    r = client.get("/api/season")
    assert r.status_code == 200
    body = r.json()
    assert body["goal"]["type"]            # actief doel of fallback-plan
    assert len(body["plan_weeks"]) > 0
    assert body["advice"]
    assert isinstance(body["ctl_actual"], list)
    assert isinstance(body["ctl_target_path"], list)


def test_season_survives_intervals_down(client, mock_api):
    mock_api.fail_events = True
    mock_api.fail_activities = True
    r = client.get("/api/season")
    assert r.status_code == 200          # nette fallback, geen crash
    assert r.json()["ctl_actual"] == []


# ── CHECKIN (injury_guard-flow) ──────────────────────────────────────────

def test_checkin_records_wellness_and_stays_green(client):
    r = client.post("/api/checkin", json={
        "sleep_score": 4, "energy": 4, "soreness": 2, "motivation": 5,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["checkin_score"] == pytest.approx(3.75)
    assert body["injury_guard"]["status"] == "groen"
    rec = history_db.get_wellness(TODAY)
    assert rec["sleep_score"] == 4 and rec["motivation"] == 5


def test_checkin_injury_signal_flips_guard_to_red(client):
    """Direct blessuresignaal (knie_pijn) → injury_guard ROOD,
    loopintensiteit dicht — zelfde flow als het oude adjust.py-pad."""
    r = client.post("/api/checkin", json={
        "sleep_score": 3, "energy": 3, "soreness": 4, "motivation": 3,
        "injury_signals": ["knie_pijn"],
    })
    assert r.status_code == 200
    guard = r.json()["injury_guard"]
    assert guard["status"] == "rood"
    assert guard["run_intensity_allowed"] is False
    assert "knie_pijn" in guard["active_signals"]
    # Status is persistent: volgende analyze ziet het signaal ook.
    state = shared.load_state()
    assert "knie_pijn" in state["injury"]["active_signals"]


# ── CHECKIN HISTORY (Jij-scherm, Fase 5) ─────────────────────────────────

def test_checkin_history(client):
    client.post("/api/checkin", json={
        "sleep_score": 4, "energy": 3, "soreness": 2, "motivation": 5,
    })
    r = client.get("/api/checkin/history")
    assert r.status_code == 200
    body = r.json()
    assert body["days"] == 14
    rec = next(x for x in body["records"] if x["date"] == TODAY.isoformat())
    assert rec["sleep_score"] == 4
    assert rec["checkin_score"] == pytest.approx(3.5)
    assert body["signals"] == []
    assert body["injury_guard"]["status"] == "groen"


def test_checkin_history_exposes_signals(client):
    """Blessuresignaal uit de checkin verschijnt in de signaalhistorie —
    de injury_guard-buffer wordt zo transparant (UPGRADE_PLAN §6)."""
    client.post("/api/checkin", json={"injury_signals": ["knie_pijn"]})
    r = client.get("/api/checkin/history?days=7")
    assert r.status_code == 200
    body = r.json()
    assert any("knie_pijn" in (h.get("signals") or [])
               for h in body["signals"])
    assert body["injury_guard"]["status"] == "rood"
    # days buiten 1..90 → 422
    assert client.get("/api/checkin/history?days=0").status_code == 422


# ── TRENDS ────────────────────────────────────────────────────────────────

def test_trends_view(client):
    r = client.get("/api/trends")
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "intervals"
    assert len(body["ctl_series"]) > 0
    assert len(body["weekly_volume"]) > 0
    assert len(body["hrv"]) > 0
    assert body["load"]["ctl_estimate"] == 48.0
    # Athlete-snapshot + TP-status (Jij-scherm, Fase 5)
    assert body["athlete"]["ftp"] > 0
    assert body["athlete"]["hrmax"] > 0
    assert body["tp_sync_enabled"] is False


# ── SPA-FALLBACK (Fase 5 deploy) ─────────────────────────────────────────

def test_spa_fallback_serves_index_and_files(mock_api, env, tmp_path):
    (tmp_path / "index.html").write_text("<html>SPA</html>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    env.setenv("WEB_DIST_DIR", str(tmp_path))
    _seed_state()
    from api.main import create_app

    with TestClient(create_app()) as client:
        # Root + diepe SPA-route → index.html
        r = client.get("/")
        assert r.status_code == 200 and "SPA" in r.text
        assert "SPA" in client.get("/season").text
        # Echt bestand → as-is
        assert client.get("/assets/app.js").text.startswith("console")
        # /api blijft API: geen index.html-fallback
        assert client.get("/api/bestaat-niet").status_code == 404


def test_no_dist_means_api_only(mock_api, env, tmp_path):
    """Zonder index.html in WEB_DIST_DIR geen catch-all → / is 404."""
    env.setenv("WEB_DIST_DIR", str(tmp_path))  # leeg: geen build
    _seed_state()
    from api.main import create_app

    with TestClient(create_app()) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/").status_code == 404


# ── TP SYNC ───────────────────────────────────────────────────────────────

def test_sync_tp_disabled_gives_409(client):
    r = client.post("/api/sync/tp/e_today")
    assert r.status_code == 409


def test_sync_tp_happy_path(client, env):
    import tp_sync_service

    env.setenv("TP_SYNC_ENABLED", "1")
    env.setenv("TP_AUTH_COOKIE", "test-cookie")

    captured = {}

    def fake_sync(event, cookie, *args, **kwargs):
        captured["event_id"] = str(event.get("id"))
        captured["cookie"] = cookie
        return {"tp_workout_id": 12345, "title": event.get("name"),
                "workout_day": event["start_date_local"][:10],
                "replaced": False}

    env.setattr(tp_sync_service, "sync_event", fake_sync)
    r = client.post("/api/sync/tp/e_today")
    assert r.status_code == 200
    assert r.json()["tp_workout_id"] == 12345
    assert captured == {"event_id": "e_today", "cookie": "test-cookie"}


def test_sync_tp_unknown_event_404(client, env):
    env.setenv("TP_SYNC_ENABLED", "1")
    r = client.post("/api/sync/tp/bestaat_niet")
    assert r.status_code == 404


# ── COACH FEEDBACK (SSE) ─────────────────────────────────────────────────

def test_coach_feedback_sse_rule_based_fallback(client):
    """Geen Gemini-key → rule-based fallback, non-streaming, wel SSE."""
    r = client.get("/api/coach/feedback?event_id=e_done")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    body = r.text
    assert body.startswith("data: ")
    assert '"fallback": true' in body
    assert "data: [DONE]" in body


def test_coach_feedback_unknown_event_404(client):
    r = client.get("/api/coach/feedback?event_id=bestaat_niet")
    assert r.status_code == 404


def test_coach_feedback_planned_but_not_done(client):
    """Event zonder activiteit → vriendelijke fallback-tekst."""
    r = client.get("/api/coach/feedback?event_id=e_today")
    assert r.status_code == 200
    assert "Nog geen voltooide activiteit" in r.text


# ── HEALTH ────────────────────────────────────────────────────────────────

def test_health_is_public(mock_api, env):
    env.setenv("API_TOKEN", "geheim-token")
    from api.main import create_app

    with TestClient(create_app()) as client:
        assert client.get("/api/health").status_code == 200
