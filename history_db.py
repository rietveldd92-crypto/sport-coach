"""
history_db — SQLite persistence voor Sport Coach.

Bevat wellness history, TP sync state, weekly summaries en (later)
morning check-ins. Minimaal migratie-systeem: een lijst van functies
met een version-nummer, idempotent toegepast bij elke app-start.

Gebruik:
    from history_db import db

    db.ensure_migrations()                  # altijd veilig
    db.record_wellness(date.today(), ...)   # API om data te schrijven
    rows = db.get_recent_wellness(days=14)  # API om data te lezen
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Optional


# ── CONFIG ─────────────────────────────────────────────────────────────────

DB_PATH = Path(__file__).parent / "history.db"


def _connect() -> sqlite3.Connection:
    """Open een nieuwe connectie. Callers sluiten 'm zelf via with."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # WAL voor betere concurrent reads (al is het single-user)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ── MIGRATIONS ─────────────────────────────────────────────────────────────

def _migration_001_initial_schema(conn: sqlite3.Connection) -> None:
    """v1: wellness_daily, workout_tp_sync, weekly_summary."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS wellness_daily (
            date TEXT PRIMARY KEY,
            sleep_score INTEGER,
            energy INTEGER,
            soreness INTEGER,
            motivation INTEGER,
            hrv REAL,
            resting_hr INTEGER,
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS workout_tp_sync (
            event_id TEXT PRIMARY KEY,
            tp_workout_id TEXT,
            last_sync_hash TEXT,
            last_synced_at TEXT,
            synced_event_name TEXT
        );

        CREATE TABLE IF NOT EXISTS weekly_summary (
            week_start TEXT PRIMARY KEY,
            planned_tss REAL,
            actual_tss REAL,
            sessions_planned INTEGER,
            sessions_done INTEGER,
            phase TEXT,
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        """
    )


# Registreer migraties in volgorde: (version, name, function)
_MIGRATIONS = [
    (1, "initial_schema", _migration_001_initial_schema),
]


def ensure_migrations() -> None:
    """Past alle pending migraties toe. Idempotent — veilig bij elke start."""
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT,
                applied_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        cursor = conn.execute("SELECT version FROM schema_migrations")
        applied = {row["version"] for row in cursor.fetchall()}

        for version, name, migration_fn in _MIGRATIONS:
            if version in applied:
                continue
            migration_fn(conn)
            conn.execute(
                "INSERT INTO schema_migrations (version, name) VALUES (?, ?)",
                (version, name),
            )
            conn.commit()


# ── WELLNESS API ───────────────────────────────────────────────────────────

def record_wellness(
    on_date: date,
    *,
    sleep_score: Optional[int] = None,
    energy: Optional[int] = None,
    soreness: Optional[int] = None,
    motivation: Optional[int] = None,
    hrv: Optional[float] = None,
    resting_hr: Optional[int] = None,
    notes: Optional[str] = None,
) -> None:
    """Upsert een wellness-record voor een datum. Overschrijft bestaande waarden."""
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO wellness_daily
                (date, sleep_score, energy, soreness, motivation, hrv, resting_hr, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                sleep_score=COALESCE(excluded.sleep_score, sleep_score),
                energy=COALESCE(excluded.energy, energy),
                soreness=COALESCE(excluded.soreness, soreness),
                motivation=COALESCE(excluded.motivation, motivation),
                hrv=COALESCE(excluded.hrv, hrv),
                resting_hr=COALESCE(excluded.resting_hr, resting_hr),
                notes=COALESCE(excluded.notes, notes)
            """,
            (
                on_date.isoformat(),
                sleep_score, energy, soreness, motivation,
                hrv, resting_hr, notes,
            ),
        )
        conn.commit()


def get_wellness(on_date: date) -> Optional[dict]:
    """Haal wellness-record voor een specifieke datum."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM wellness_daily WHERE date = ?",
            (on_date.isoformat(),),
        ).fetchone()
        return dict(row) if row else None


def get_recent_wellness(days: int = 14) -> list[dict]:
    """Haal wellness-records van de laatste N dagen, oudste eerst."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM wellness_daily
            WHERE date >= date('now', ?)
            ORDER BY date ASC
            """,
            (f"-{days} days",),
        ).fetchall()
        return [dict(r) for r in rows]


def morning_checkin_score(on_date: date) -> Optional[float]:
    """Gemiddelde score van de 4 morning-checkin velden. None als geen data."""
    rec = get_wellness(on_date)
    if not rec:
        return None
    values = [
        rec.get("sleep_score"),
        rec.get("energy"),
        rec.get("soreness"),
        rec.get("motivation"),
    ]
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


# ── TP SYNC STATE API ──────────────────────────────────────────────────────

def hash_workout_doc(workout_doc: dict | None) -> str:
    """Bereken een stabiele hash van de workout-structuur voor drift-detectie."""
    if workout_doc is None:
        return ""
    try:
        payload = json.dumps(workout_doc, sort_keys=True, default=str)
    except Exception:
        payload = str(workout_doc)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def record_tp_sync(
    event_id: str,
    *,
    tp_workout_id: Optional[str],
    event_name: str,
    sync_hash: str,
) -> None:
    """Registreer dat een event naar TP is gesynced (of swap-gepropageerd)."""
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO workout_tp_sync
                (event_id, tp_workout_id, last_sync_hash, last_synced_at, synced_event_name)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(event_id) DO UPDATE SET
                tp_workout_id=excluded.tp_workout_id,
                last_sync_hash=excluded.last_sync_hash,
                last_synced_at=excluded.last_synced_at,
                synced_event_name=excluded.synced_event_name
            """,
            (
                str(event_id),
                tp_workout_id,
                sync_hash,
                datetime.now().isoformat(),
                event_name,
            ),
        )
        conn.commit()


def get_tp_sync(event_id: str) -> Optional[dict]:
    """Haal TP-sync state voor een event. None als nooit gesynced."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM workout_tp_sync WHERE event_id = ?",
            (str(event_id),),
        ).fetchone()
        return dict(row) if row else None


def clear_tp_sync(event_id: str) -> None:
    """Verwijder TP sync state (bijv. na succesvolle delete in TP)."""
    with _connect() as conn:
        conn.execute(
            "DELETE FROM workout_tp_sync WHERE event_id = ?",
            (str(event_id),),
        )
        conn.commit()


# ── WEEKLY SUMMARY API ─────────────────────────────────────────────────────

def record_weekly_summary(
    week_start: date,
    *,
    planned_tss: float = 0,
    actual_tss: float = 0,
    sessions_planned: int = 0,
    sessions_done: int = 0,
    phase: str = "",
    notes: str = "",
) -> None:
    """Upsert een weekly summary."""
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO weekly_summary
                (week_start, planned_tss, actual_tss, sessions_planned,
                 sessions_done, phase, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(week_start) DO UPDATE SET
                planned_tss=excluded.planned_tss,
                actual_tss=excluded.actual_tss,
                sessions_planned=excluded.sessions_planned,
                sessions_done=excluded.sessions_done,
                phase=excluded.phase,
                notes=excluded.notes
            """,
            (
                week_start.isoformat(),
                planned_tss, actual_tss,
                sessions_planned, sessions_done,
                phase, notes,
            ),
        )
        conn.commit()


def get_weekly_summaries(weeks: int = 16) -> list[dict]:
    """Laatste N weekly summaries, oudste eerst."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM weekly_summary
            ORDER BY week_start DESC
            LIMIT ?
            """,
            (weeks,),
        ).fetchall()
        return list(reversed([dict(r) for r in rows]))


# ── SMOKE TEST ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ensure_migrations()
    print(f"OK: {DB_PATH} ready.")
    with _connect() as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        print("Tables:", [r["name"] for r in rows])
