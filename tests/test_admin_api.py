"""Tests voor /api/admin (export/import van de SQLite-database)."""
from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

import config
import history_db
import shared

SQLITE_MAGIC = b"SQLite format 3\x00"


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.setattr(config, "_from_streamlit", lambda name: None)
    for var in ("API_TOKEN", "SCHEDULER_ENABLED"):
        monkeypatch.delenv(var, raising=False)
    yield monkeypatch


@pytest.fixture()
def client(env):
    shared.save_state({"current_phase": "accumulatie_I", "injury": {}})
    from api.main import create_app

    with TestClient(create_app()) as c:
        yield c


def test_export_roundtrip(client):
    """Export levert een geldig SQLite-bestand met onze tabellen."""
    r = client.get("/api/admin/export-db")
    assert r.status_code == 200
    assert r.content.startswith(SQLITE_MAGIC)
    assert b"athlete_state" in r.content


def test_import_replaces_db(client, tmp_path):
    """Geüploade DB vervangt de actieve; backup .pre-import blijft achter."""
    # Bouw een afwijkende maar geldige Sport-DB om te uploaden.
    src = tmp_path / "upload.db"
    conn = sqlite3.connect(src)
    conn.execute("CREATE TABLE athlete_state "
                 "(key TEXT PRIMARY KEY, value TEXT, updated_at TEXT)")
    conn.execute("INSERT INTO athlete_state VALUES "
                 "('current_phase', '\"transformatie_I\"', '2026-06-11')")
    conn.commit()
    conn.close()

    r = client.post("/api/admin/import-db", content=src.read_bytes())
    assert r.status_code == 200
    assert r.json()["imported"] is True

    state = shared.load_state()
    assert state["current_phase"] == "transformatie_I"
    assert history_db.DB_PATH.with_suffix(".pre-import").is_file()


def test_import_rejects_garbage(client):
    r = client.post("/api/admin/import-db", content=b"dit is geen sqlite")
    assert r.status_code == 422


def test_import_rejects_foreign_sqlite(client, tmp_path):
    """Wel SQLite, maar geen Sport Coach-database → 422."""
    src = tmp_path / "foreign.db"
    conn = sqlite3.connect(src)
    conn.execute("CREATE TABLE iets (x INTEGER)")
    conn.commit()
    conn.close()
    r = client.post("/api/admin/import-db", content=src.read_bytes())
    assert r.status_code == 422


def test_admin_requires_token(env):
    env.setenv("API_TOKEN", "geheim")
    from api.main import create_app

    with TestClient(create_app()) as c:
        assert c.get("/api/admin/export-db").status_code == 401
        assert c.post("/api/admin/import-db", content=b"x").status_code == 401
        ok = c.get("/api/admin/export-db",
                   headers={"Authorization": "Bearer geheim"})
        assert ok.status_code in (200, 404)
