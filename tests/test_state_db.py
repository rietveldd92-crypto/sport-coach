"""Tests voor de DB-backed athlete state (Fase 0, UPGRADE_PLAN §3/§8).

Dekt:
- round-trip load_state/save_state via SQLite (athlete_state)
- fallback naar state.json zolang athlete_state leeg is
- availability-reconstructie ({date: minuten} ⇆ availability_override slots)
- idempotentie + backup van scripts/migrate_state_json.py
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import history_db
import shared
from scripts.migrate_state_json import migrate

SAMPLE_STATE = {
    "athlete_id": "i85836",
    "race_date": "2026-10-18",
    "current_phase": "accumulatie_I",
    "week_number": 6,
    "plan_start": "2026-04-06",
    "injury": {
        "active_signals": [],
        "days_symptom_free": 64,
        "history": [{"date": "2026-03-08", "signals": ["knie_twinge"]}],
    },
    "signal_buffer": {},
    "load": {"ctl_estimate": 51.8, "tsb_estimate": 8.0, "weekly_tss_target": 680},
    "build_deload": {"consecutive_build_weeks": 3, "is_deload_week": False},
    "progression": {"threshold_step": 4, "long_ride_min": 150},
    "weekly_log": [{"week_start": "2026-06-01", "planned_tss": 377}],
    "tp_sync_log": {
        "102842985": {
            "tp_workout_id": 3672397106,
            "synced_at": "2026-04-08T22:35:09",
            "title": "Threshold",
            "workout_day": "2026-04-08",
        }
    },
    "availability": {
        "2026-05-06": 60,
        "2026-05-07": 0,
        "2026-05-08": 120,
        "2026-05-09": 180,
    },
}


# ---------------------------------------------------------------------------
# Round-trip via SQLite
# ---------------------------------------------------------------------------


def test_save_load_round_trip_exact_dict():
    shared.save_state(SAMPLE_STATE)
    loaded = shared.load_state()
    assert loaded == SAMPLE_STATE


def test_save_state_does_not_mutate_caller_dict():
    state = dict(SAMPLE_STATE)
    shared.save_state(state)
    assert "availability" in state


def test_whole_state_overwrite_semantics():
    """save_state vervangt de hele state — keys die verdwijnen zijn weg
    (zelfde semantiek als het oude state.json-bestand overschrijven)."""
    shared.save_state(SAMPLE_STATE)
    smaller = {"athlete_id": "i85836", "week_number": 7}
    shared.save_state(smaller)
    loaded = shared.load_state()
    assert loaded == smaller
    assert "injury" not in loaded


def test_nested_types_survive_round_trip():
    shared.save_state(SAMPLE_STATE)
    loaded = shared.load_state()
    assert isinstance(loaded["week_number"], int)
    assert isinstance(loaded["load"]["ctl_estimate"], float)
    assert loaded["build_deload"]["is_deload_week"] is False
    assert isinstance(loaded["weekly_log"], list)


# ---------------------------------------------------------------------------
# Availability-reconstructie
# ---------------------------------------------------------------------------


def test_availability_minutes_to_slots_and_back():
    shared.save_state(SAMPLE_STATE)
    loaded = shared.load_state()
    assert loaded["availability"] == SAMPLE_STATE["availability"]


def test_availability_slot_encoding_in_db():
    """60 min → 07:00-08:00; 0 min (rustdag) → expliciete 00:00-00:00 rij."""
    shared.save_state(SAMPLE_STATE)
    with sqlite3.connect(history_db.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = {
            r["date"]: (r["slot_start"], r["slot_end"])
            for r in conn.execute(
                "SELECT date, slot_start, slot_end FROM availability_override"
            )
        }
    assert rows["2026-05-06"] == ("07:00", "08:00")
    assert rows["2026-05-07"] == ("00:00", "00:00")  # rustdag blijft geregistreerd
    assert rows["2026-05-08"] == ("07:00", "09:00")
    assert rows["2026-05-09"] == ("07:00", "10:00")


def test_multiple_slots_per_day_sum_to_minutes():
    """Toekomstvast: meerdere vensters per dag sommeren naar minuten."""
    history_db.ensure_migrations()
    with sqlite3.connect(history_db.DB_PATH) as conn:
        conn.executemany(
            "INSERT INTO availability_override (date, slot_start, slot_end)"
            " VALUES (?, ?, ?)",
            [
                ("2026-05-11", "06:00", "07:00"),
                ("2026-05-11", "18:00", "18:45"),
            ],
        )
        conn.commit()
    assert history_db.get_availability_minutes()["2026-05-11"] == 105


def test_agents_availability_module_reads_and_writes_db():
    """agents/availability.py werkt ongewijzigd door op de DB-backed state."""
    from datetime import date

    from agents import availability

    shared.save_state(SAMPLE_STATE)
    week_start = date(2026, 5, 4)  # maandag van de week met 2026-05-06 e.d.
    week = availability.get_week(week_start)
    assert week["2026-05-06"] == 60
    assert week["2026-05-07"] == 0
    assert week["2026-05-04"] is None  # niet ingesteld

    availability.set_week(week_start, {"2026-05-04": 90})
    assert availability.get_week(week_start)["2026-05-04"] == 90
    # andere state-secties zijn niet kapotgegaan
    assert shared.load_state()["injury"]["days_symptom_free"] == 64


# ---------------------------------------------------------------------------
# Fallback naar state.json
# ---------------------------------------------------------------------------


def test_load_state_falls_back_to_json_when_db_empty(tmp_path, monkeypatch):
    state_json = tmp_path / "state.json"
    state_json.write_text(
        json.dumps(SAMPLE_STATE, ensure_ascii=False), encoding="utf-8"
    )
    monkeypatch.setattr(shared, "STATE_PATH", state_json)

    # athlete_state is leeg (verse test-DB) → fallback levert de JSON-inhoud
    assert history_db.athlete_state_is_empty()
    assert shared.load_state() == SAMPLE_STATE


def test_db_wins_over_json_once_populated(tmp_path, monkeypatch):
    state_json = tmp_path / "state.json"
    state_json.write_text(json.dumps({"week_number": 1}), encoding="utf-8")
    monkeypatch.setattr(shared, "STATE_PATH", state_json)

    shared.save_state({"week_number": 42})
    assert shared.load_state() == {"week_number": 42}


def test_explicit_custom_path_stays_pure_json(tmp_path):
    """Tests/callers met een expliciet pad krijgen legacy JSON-gedrag."""
    custom = tmp_path / "other_state.json"
    shared.save_state({"a": 1}, custom)
    assert json.loads(custom.read_text(encoding="utf-8")) == {"a": 1}
    assert shared.load_state(custom) == {"a": 1}
    # en de DB is hierdoor niet gevuld
    assert history_db.athlete_state_is_empty()


def test_load_state_empty_everywhere_returns_empty_dict(tmp_path, monkeypatch):
    monkeypatch.setattr(shared, "STATE_PATH", tmp_path / "missing.json")
    assert shared.load_state() == {}


# ---------------------------------------------------------------------------
# Migratiescript
# ---------------------------------------------------------------------------


def _write_sample_json(tmp_path: Path) -> Path:
    p = tmp_path / "state.json"
    p.write_text(json.dumps(SAMPLE_STATE, ensure_ascii=False), encoding="utf-8")
    return p


def test_migrate_state_json_populates_all_tables(tmp_path, monkeypatch):
    state_json = _write_sample_json(tmp_path)
    backup = tmp_path / "state.json.bak"
    monkeypatch.setattr(shared, "STATE_PATH", state_json)

    report = migrate(state_path=state_json, backup_path=backup)
    assert report["ok"] is True
    assert report["backup_created"] is True
    assert backup.exists()

    # load_state geeft exact het oude dict terug (incl. availability)
    assert shared.load_state() == SAMPLE_STATE

    # tp_sync_log is ook in workout_tp_sync beland
    import tp_sync_service
    entry = tp_sync_service.is_synced("102842985")
    assert entry is not None
    assert entry["tp_workout_id"] == 3672397106
    assert entry["workout_day"] == "2026-04-08"


def test_migrate_is_idempotent(tmp_path, monkeypatch):
    state_json = _write_sample_json(tmp_path)
    backup = tmp_path / "state.json.bak"
    monkeypatch.setattr(shared, "STATE_PATH", state_json)

    migrate(state_path=state_json, backup_path=backup)
    first = shared.load_state()
    report2 = migrate(state_path=state_json, backup_path=backup)
    assert report2["ok"] is True
    assert report2["backup_created"] is False  # backup niet overschreven
    assert shared.load_state() == first == SAMPLE_STATE
