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
import os
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Optional


# ── CONFIG ────────────────────────────────────────────────────────────────

# Overschrijfbaar via env (SPORT_DB_PATH) zodat smoke-runs en de
# INTERVALS_FAKE-modus een wegwerp-database kunnen gebruiken.
DB_PATH = Path(os.environ.get("SPORT_DB_PATH")
               or Path(__file__).parent / "history.db")


def _connect() -> sqlite3.Connection:
    """Open een nieuwe connectie. Callers sluiten 'm zelf via with."""
    # Op een verse Railway-mount kan de map (/data) nog niet bestaan; zonder
    # dit crasht sqlite3.connect met "unable to open database file" en faalt
    # de hele startup (502). mkdir is idempotent en goedkoop.
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000")
    # WAL voor betere concurrent reads (al is het single-user). In pytest op
    # Windows veroorzaakt WAL sidecar-locks bij admin import/export-tests.
    journal_mode = "DELETE" if os.environ.get("PYTEST_CURRENT_TEST") else "WAL"
    try:
        conn.execute(f"PRAGMA journal_mode={journal_mode}")
    except sqlite3.OperationalError as exc:
        if "locked" not in str(exc).lower():
            raise
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


def _migration_002_week_reflections(conn: sqlite3.Connection) -> None:
    """v2: week_reflections tabel voor weekreflecties."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS week_reflections (
            week_start TEXT PRIMARY KEY,
            enjoyed TEXT,
            drained TEXT,
            ai_summary TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        """
    )


def _migration_003_athlete_state_and_planner_v2(conn: sqlite3.Connection) -> None:
    """v3: athlete_state (vervangt state.json) + planner-v2 schema (UPGRADE_PLAN §3).

    De planner-v2 tabellen (goals, plan_weeks, availability_pattern,
    availability_override, placements) worden pas in latere fases gebruikt,
    maar het schema staat er alvast.
    """
    conn.executescript(
        """
        -- Athlete state: key/value met JSON-waarden, vervangt state.json
        CREATE TABLE IF NOT EXISTS athlete_state (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT
        );

        -- Doelen
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY,
            type TEXT NOT NULL,            -- marathon|half|10k|5k|gran_fondo|ftp|triathlon|custom
            sport TEXT NOT NULL,           -- run|ride|multi
            event_date TEXT NOT NULL,
            target_value TEXT,             -- "2:59:00" | "310W" | NULL
            priority TEXT DEFAULT 'A',     -- A|B|C
            status TEXT DEFAULT 'active',  -- active|completed|abandoned
            created_at TEXT
        );

        -- Gegenereerd macroplan (1 rij per week per actief A-doel)
        CREATE TABLE IF NOT EXISTS plan_weeks (
            goal_id INTEGER REFERENCES goals(id),
            week_start TEXT,
            phase TEXT,
            is_deload INTEGER,
            tss_target_min INTEGER,
            tss_target_max INTEGER,
            run_km REAL,
            run_sessions INTEGER,
            long_run_km REAL,
            bike_sessions INTEGER,
            intensity_gate TEXT,           -- geen|strides|tempoduur|drempel|race_specifiek
            generated_at TEXT,
            PRIMARY KEY (goal_id, week_start)
        );

        -- Beschikbaarheid: terugkerend weekpatroon
        CREATE TABLE IF NOT EXISTS availability_pattern (
            weekday INTEGER,               -- 0=ma .. 6=zo
            slot_start TEXT,
            slot_end TEXT,
            context TEXT DEFAULT 'any',    -- any|indoor_only|outdoor_only
            PRIMARY KEY (weekday, slot_start)
        );

        -- Overrides per datum (vervangt het hele patroon voor die dag)
        CREATE TABLE IF NOT EXISTS availability_override (
            date TEXT,
            slot_start TEXT,
            slot_end TEXT,
            context TEXT DEFAULT 'any',
            PRIMARY KEY (date, slot_start)
        );

        -- Plaatsing: koppelt intervals.icu events aan slots + solver-uitleg
        CREATE TABLE IF NOT EXISTS placements (
            event_id TEXT PRIMARY KEY,
            date TEXT,
            slot_start TEXT,
            session_kind TEXT,             -- long|hard|easy|strength|rehab
            locked INTEGER DEFAULT 0,
            solver_score REAL,
            solver_notes TEXT,
            goal_id INTEGER
        );
        """
    )
    # workout_tp_sync uitbreiden met workout_day (nodig voor de TP-synclog
    # die uit state.json verhuist). Idempotent via kolom-check.
    cols = {row[1] for row in conn.execute("PRAGMA table_info(workout_tp_sync)")}
    if "workout_day" not in cols:
        conn.execute("ALTER TABLE workout_tp_sync ADD COLUMN workout_day TEXT")


def _migration_004_adherence(conn: sqlite3.Connection) -> None:
    """v4: verplicht/optioneel-onderscheid voor de consistentie-laag (80-90%-filosofie).

    ``placements.priority`` volgt de sessie ("verplicht"/"optioneel") vanaf
    plaatsing. ``weekly_summary`` krijgt de required/optional-telling zodat
    ``agents.adherence`` een rolling venster kan berekenen i.p.v. een
    per-week-oordeel.
    """
    cols = {row[1] for row in conn.execute("PRAGMA table_info(placements)")}
    if "priority" not in cols:
        conn.execute("ALTER TABLE placements ADD COLUMN priority TEXT")

    cols = {row[1] for row in conn.execute("PRAGMA table_info(weekly_summary)")}
    for col in ("sessions_required", "sessions_required_done",
                "sessions_optional", "sessions_optional_done"):
        if col not in cols:
            conn.execute(f"ALTER TABLE weekly_summary ADD COLUMN {col} INTEGER")


def _migration_005_fixed_sessions(conn: sqlite3.Connection) -> None:
    """v5: vaste terugkerende sessies voor Planner V3."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS fixed_sessions (
            weekday INTEGER PRIMARY KEY,
            name TEXT,
            sport TEXT,
            duration_min INTEGER,
            if_estimate REAL,
            enabled INTEGER DEFAULT 1
        );
        """
    )


def _migration_006_threshold_pace(conn: sqlite3.Connection) -> None:
    """v6: drempelpace-dossier, suggesties en RPE."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS threshold_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            activity_id TEXT UNIQUE,
            pace_delta_sec REAL,
            hr_reps_avg REAL,
            hr_vs_band TEXT,
            rpe INTEGER,
            completed INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS threshold_pace_suggestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            old_sec INTEGER,
            proposed_sec INTEGER,
            reason TEXT,
            source TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT (datetime('now')),
            resolved_at TEXT
        );

        CREATE TABLE IF NOT EXISTS threshold_pace_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            old_sec INTEGER,
            new_sec INTEGER,
            reason TEXT,
            source TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS workout_rpe (
            activity_id TEXT PRIMARY KEY,
            rpe INTEGER,
            date TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        """
    )


# Registreer migraties in volgorde: (version, name, function)
_MIGRATIONS = [
    (1, "initial_schema", _migration_001_initial_schema),
    (2, "week_reflections", _migration_002_week_reflections),
    (3, "athlete_state_and_planner_v2", _migration_003_athlete_state_and_planner_v2),
    (4, "adherence", _migration_004_adherence),
    (5, "fixed_sessions", _migration_005_fixed_sessions),
    (6, "threshold_pace", _migration_006_threshold_pace),
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
    sync_hash: Optional[str],
    workout_day: Optional[str] = None,
    synced_at: Optional[str] = None,
) -> None:
    """Registreer dat een event naar TP is gesynced (of swap-gepropageerd).

    ``sync_hash=None`` laat een bestaande hash intact (handmatige syncs
    kennen de workout-doc-hash niet); idem voor ``workout_day``.
    """
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO workout_tp_sync
                (event_id, tp_workout_id, last_sync_hash, last_synced_at,
                 synced_event_name, workout_day)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id) DO UPDATE SET
                tp_workout_id=excluded.tp_workout_id,
                last_sync_hash=COALESCE(excluded.last_sync_hash, last_sync_hash),
                last_synced_at=excluded.last_synced_at,
                synced_event_name=excluded.synced_event_name,
                workout_day=COALESCE(excluded.workout_day, workout_day)
            """,
            (
                str(event_id),
                tp_workout_id,
                sync_hash,
                synced_at or datetime.now().isoformat(),
                event_name,
                workout_day,
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


def get_all_tp_sync() -> list[dict]:
    """Alle TP-sync records (voor de synclog-weergave)."""
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM workout_tp_sync").fetchall()
        return [dict(r) for r in rows]


# ── ATHLETE STATE API ─────────────────────────────────────────────────────
#
# Key/value store die state.json vervangt. Elke top-level sectie van het
# oude state.json is één rij; value is een JSON-string.

def get_athlete_state() -> dict:
    """Volledige athlete state als dict {key: python-waarde}.

    JSON-waarden worden geparsed; onparseerbare waarden komen als
    ruwe string terug (defensief, hoort niet voor te komen).
    """
    ensure_migrations()
    out: dict = {}
    with _connect() as conn:
        rows = conn.execute("SELECT key, value FROM athlete_state").fetchall()
    for row in rows:
        try:
            out[row["key"]] = json.loads(row["value"])
        except (TypeError, json.JSONDecodeError):
            out[row["key"]] = row["value"]
    return out


def set_athlete_state_value(key: str, value) -> None:
    """Upsert één athlete_state key. value wordt als JSON opgeslagen."""
    ensure_migrations()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO athlete_state (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value=excluded.value,
                updated_at=excluded.updated_at
            """,
            (key, json.dumps(value, ensure_ascii=False), datetime.now().isoformat()),
        )
        conn.commit()


def replace_athlete_state(state: dict) -> None:
    """Vervang de volledige athlete state door ``state`` (één transactie).

    Dit spiegelt de oude state.json-semantiek: save_state() overschreef
    het hele bestand, dus keys die niet meer in het dict zitten verdwijnen.
    """
    ensure_migrations()
    now = datetime.now().isoformat()
    with _connect() as conn:
        conn.execute("DELETE FROM athlete_state")
        conn.executemany(
            "INSERT INTO athlete_state (key, value, updated_at) VALUES (?, ?, ?)",
            [
                (key, json.dumps(value, ensure_ascii=False), now)
                for key, value in state.items()
            ],
        )
        conn.commit()


def athlete_state_is_empty() -> bool:
    """True als er nog niets gemigreerd is (→ fallback naar state.json)."""
    ensure_migrations()
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM athlete_state").fetchone()
        return (row["n"] or 0) == 0


# ── AVAILABILITY OVERRIDE API ─────────────────────────────────────────────
#
# Fase 0-brug: de app werkt nog met {date: minuten}. We bewaren dat als
# één slot per dag in availability_override (07:00 + minuten). Een rustdag
# (0 minuten) is een expliciete "00:00"–"00:00" rij zodat de informatie
# "bewust 0 ingesteld" behouden blijft. Fase 1 vervangt dit door echte
# tijdvensters.

_DEFAULT_SLOT_START = "07:00"


def _minutes_between(slot_start: str, slot_end: str) -> int:
    """Verschil in minuten tussen twee 'HH:MM' strings (negatief → 0)."""
    try:
        sh, sm = (int(p) for p in slot_start.split(":")[:2])
        eh, em = (int(p) for p in slot_end.split(":")[:2])
    except (ValueError, AttributeError):
        return 0
    return max(0, (eh * 60 + em) - (sh * 60 + sm))


def _minutes_to_slot(minutes: int) -> tuple[str, str]:
    """Map minuten naar (slot_start, slot_end). 0 → ('00:00', '00:00')."""
    if minutes <= 0:
        return "00:00", "00:00"
    start_h, start_m = (int(p) for p in _DEFAULT_SLOT_START.split(":"))
    total = min(start_h * 60 + start_m + int(minutes), 23 * 60 + 59)
    return _DEFAULT_SLOT_START, f"{total // 60:02d}:{total % 60:02d}"


def get_availability_minutes() -> dict[str, int]:
    """Reconstrueer {date_iso: minuten} uit availability_override.

    Meerdere slots op één datum worden gesommeerd; een '00:00'–'00:00'
    rij telt als expliciete rustdag (0 minuten).
    """
    ensure_migrations()
    out: dict[str, int] = {}
    with _connect() as conn:
        rows = conn.execute(
            "SELECT date, slot_start, slot_end FROM availability_override"
        ).fetchall()
    for row in rows:
        d = row["date"]
        out[d] = out.get(d, 0) + _minutes_between(row["slot_start"], row["slot_end"])
    return out


def replace_availability_minutes(minutes_by_date: dict[str, int]) -> None:
    """Vervang alle availability_override rijen door het gegeven dict.

    Spiegelt de oude state.json-semantiek (hele sectie overschrijven),
    met één uitzondering (Fase 1): datums waarvan het minuten-totaal
    NIET wijzigt behouden hun bestaande rijen. Zo slaat een legacy
    load→save-roundtrip de rijke v2-vensters (meerdere slots, contexts)
    niet plat naar één 07:00-venster.
    """
    ensure_migrations()
    existing = get_availability_minutes()
    with _connect() as conn:
        # Datums die uit het dict verdwenen zijn → weg (whole-overwrite).
        gone = [d for d in existing if d not in minutes_by_date]
        if gone:
            conn.executemany(
                "DELETE FROM availability_override WHERE date = ?",
                [(d,) for d in gone],
            )
        rows = []
        for date_iso, minutes in minutes_by_date.items():
            minutes = int(minutes or 0)
            if existing.get(date_iso) == minutes:
                continue  # ongewijzigd — slot-detail intact laten
            conn.execute(
                "DELETE FROM availability_override WHERE date = ?", (date_iso,)
            )
            slot_start, slot_end = _minutes_to_slot(minutes)
            rows.append((date_iso, slot_start, slot_end))
        if rows:
            conn.executemany(
                "INSERT OR REPLACE INTO availability_override (date, slot_start, slot_end)"
                " VALUES (?, ?, ?)",
                rows,
            )
        conn.commit()


# ── PLACEMENTS API ────────────────────────────────────────────────────────
#
# Fase 1 (Planner v2): koppelt intervals.icu events aan het slot waarin de
# solver ze plaatste, plus score/uitleg zodat keuzes inspecteerbaar zijn.

def upsert_placement(
    event_id: str,
    *,
    date: Optional[str] = None,
    slot_start: Optional[str] = None,
    session_kind: Optional[str] = None,
    locked: Optional[bool] = None,
    solver_score: Optional[float] = None,
    solver_notes: Optional[str] = None,
    goal_id: Optional[int] = None,
    priority: Optional[str] = None,
) -> None:
    """Upsert een placement. ``locked=None`` laat de bestaande lock intact.

    ``priority`` ("verplicht"/"optioneel", zie agents.adherence) volgt de
    sessie vanaf plaatsing zodat de consistentie-laag achteraf kan tellen
    welke gemiste sessies daadwerkelijk de trainingsstimulus droegen.
    """
    ensure_migrations()
    lock_val = None if locked is None else (1 if locked else 0)
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO placements
                (event_id, date, slot_start, session_kind, locked,
                 solver_score, solver_notes, goal_id, priority)
            VALUES (?, ?, ?, ?, COALESCE(?, 0), ?, ?, ?, ?)
            ON CONFLICT(event_id) DO UPDATE SET
                date=excluded.date,
                slot_start=excluded.slot_start,
                session_kind=COALESCE(excluded.session_kind, session_kind),
                locked=COALESCE(?, locked),
                solver_score=excluded.solver_score,
                solver_notes=excluded.solver_notes,
                goal_id=COALESCE(excluded.goal_id, goal_id),
                priority=COALESCE(excluded.priority, priority)
            """,
            (str(event_id), date, slot_start, session_kind, lock_val,
             solver_score, solver_notes, goal_id, priority, lock_val),
        )
        conn.commit()


def get_placement(event_id: str) -> Optional[dict]:
    ensure_migrations()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM placements WHERE event_id = ?", (str(event_id),)
        ).fetchone()
        return dict(row) if row else None


def get_placements(start_date: Optional[str] = None,
                   end_date: Optional[str] = None) -> list[dict]:
    """Placements, optioneel gefilterd op datumbereik (ISO, inclusief)."""
    ensure_migrations()
    query = "SELECT * FROM placements"
    params: list = []
    clauses = []
    if start_date:
        clauses.append("date >= ?")
        params.append(start_date)
    if end_date:
        clauses.append("date <= ?")
        params.append(end_date)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY date, slot_start"
    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def delete_placement(event_id: str) -> None:
    ensure_migrations()
    with _connect() as conn:
        conn.execute("DELETE FROM placements WHERE event_id = ?",
                     (str(event_id),))
        conn.commit()


def set_placement_locked(event_id: str, locked: bool) -> None:
    ensure_migrations()
    with _connect() as conn:
        conn.execute(
            "UPDATE placements SET locked = ? WHERE event_id = ?",
            (1 if locked else 0, str(event_id)),
        )
        conn.commit()


# ── WEEKLY SUMMARY API ─────────────────────────────────────────────────────

def list_fixed_sessions() -> list[dict]:
    ensure_migrations()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM fixed_sessions ORDER BY weekday"
        ).fetchall()
    return [dict(row) for row in rows]


def get_fixed_session(weekday: int) -> Optional[dict]:
    ensure_migrations()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM fixed_sessions WHERE weekday = ?",
            (int(weekday),),
        ).fetchone()
    return dict(row) if row else None


def upsert_fixed_session(
    weekday: int,
    *,
    name: str,
    sport: str,
    duration_min: int,
    if_estimate: float = 0.65,
    enabled: bool = True,
) -> None:
    if not 0 <= int(weekday) <= 6:
        raise ValueError(f"weekday moet 0..6 zijn, kreeg {weekday}")
    ensure_migrations()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO fixed_sessions
                (weekday, name, sport, duration_min, if_estimate, enabled)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(weekday) DO UPDATE SET
                name=excluded.name,
                sport=excluded.sport,
                duration_min=excluded.duration_min,
                if_estimate=excluded.if_estimate,
                enabled=excluded.enabled
            """,
            (
                int(weekday),
                name,
                sport,
                int(duration_min),
                float(if_estimate),
                1 if enabled else 0,
            ),
        )
        conn.commit()


def delete_fixed_session(weekday: int) -> None:
    ensure_migrations()
    with _connect() as conn:
        conn.execute(
            "DELETE FROM fixed_sessions WHERE weekday = ?",
            (int(weekday),),
        )
        conn.commit()


# ── THRESHOLD PACE API ─────────────────────────────────────────────────────

def insert_threshold_observation(
    *,
    date: str,
    activity_id: str,
    pace_delta_sec: float | None,
    hr_reps_avg: float | None,
    hr_vs_band: str | None,
    rpe: int | None,
    completed: bool = True,
) -> dict:
    ensure_migrations()
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO threshold_observations
                (date, activity_id, pace_delta_sec, hr_reps_avg, hr_vs_band, rpe, completed)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                date,
                str(activity_id),
                pace_delta_sec,
                hr_reps_avg,
                hr_vs_band,
                rpe,
                1 if completed else 0,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM threshold_observations WHERE activity_id = ?",
            (str(activity_id),),
        ).fetchone()
    return dict(row) if row else {}


def list_threshold_observations(
    *,
    since: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    ensure_migrations()
    query = "SELECT * FROM threshold_observations"
    params: list = []
    if since:
        query += " WHERE date >= ?"
        params.append(since)
    query += " ORDER BY date DESC, id DESC"
    if limit is not None:
        query += " LIMIT ?"
        params.append(int(limit))
    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def clear_threshold_observations() -> None:
    ensure_migrations()
    with _connect() as conn:
        conn.execute("DELETE FROM threshold_observations")
        conn.commit()


def insert_threshold_suggestion(
    *,
    date: str,
    old_sec: int,
    proposed_sec: int,
    reason: str,
    source: str,
) -> dict:
    ensure_migrations()
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO threshold_pace_suggestions
                (date, old_sec, proposed_sec, reason, source, status)
            VALUES (?, ?, ?, ?, ?, 'pending')
            """,
            (date, int(old_sec), int(proposed_sec), reason, source),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM threshold_pace_suggestions WHERE id = ?",
            (cur.lastrowid,),
        ).fetchone()
    return dict(row)


def get_pending_threshold_suggestion() -> Optional[dict]:
    ensure_migrations()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM threshold_pace_suggestions
            WHERE status = 'pending'
            ORDER BY id DESC LIMIT 1
            """
        ).fetchone()
    return dict(row) if row else None


def get_threshold_suggestion(suggestion_id: int) -> Optional[dict]:
    ensure_migrations()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM threshold_pace_suggestions WHERE id = ?",
            (int(suggestion_id),),
        ).fetchone()
    return dict(row) if row else None


def resolve_threshold_suggestion(suggestion_id: int, status: str) -> None:
    ensure_migrations()
    with _connect() as conn:
        conn.execute(
            """
            UPDATE threshold_pace_suggestions
            SET status = ?, resolved_at = ?
            WHERE id = ?
            """,
            (status, datetime.now().isoformat(), int(suggestion_id)),
        )
        conn.commit()


def latest_threshold_resolution() -> Optional[dict]:
    ensure_migrations()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM threshold_pace_suggestions
            WHERE status IN ('accepted', 'dismissed')
            ORDER BY resolved_at DESC, id DESC LIMIT 1
            """
        ).fetchone()
    return dict(row) if row else None


def insert_threshold_pace_log(
    *,
    date: str,
    old_sec: int,
    new_sec: int,
    reason: str,
    source: str,
) -> dict:
    ensure_migrations()
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO threshold_pace_log (date, old_sec, new_sec, reason, source)
            VALUES (?, ?, ?, ?, ?)
            """,
            (date, int(old_sec), int(new_sec), reason, source),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM threshold_pace_log WHERE id = ?",
            (cur.lastrowid,),
        ).fetchone()
    return dict(row)


def list_threshold_pace_log() -> list[dict]:
    ensure_migrations()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM threshold_pace_log ORDER BY date, id"
        ).fetchall()
    return [dict(row) for row in rows]


def upsert_workout_rpe(activity_id: str, rpe: int, date: str) -> dict:
    ensure_migrations()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO workout_rpe (activity_id, rpe, date)
            VALUES (?, ?, ?)
            ON CONFLICT(activity_id) DO UPDATE SET
                rpe=excluded.rpe,
                date=excluded.date
            """,
            (str(activity_id), int(rpe), date),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM workout_rpe WHERE activity_id = ?",
            (str(activity_id),),
        ).fetchone()
    return dict(row)


def get_workout_rpe(activity_id: str) -> Optional[dict]:
    ensure_migrations()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM workout_rpe WHERE activity_id = ?",
            (str(activity_id),),
        ).fetchone()
    return dict(row) if row else None


def record_weekly_summary(
    week_start: date,
    *,
    planned_tss: float = 0,
    actual_tss: float = 0,
    sessions_planned: int = 0,
    sessions_done: int = 0,
    phase: str = "",
    notes: str = "",
    sessions_required: int = 0,
    sessions_required_done: int = 0,
    sessions_optional: int = 0,
    sessions_optional_done: int = 0,
) -> None:
    """Upsert een weekly summary.

    ``sessions_required*``/``sessions_optional*`` splitsen de bestaande
    ``sessions_planned``/``sessions_done`` op verplicht vs. optioneel (zie
    agents.adherence) — nodig voor de rolling consistentie-band i.p.v. een
    per-week-oordeel.
    """
    ensure_migrations()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO weekly_summary
                (week_start, planned_tss, actual_tss, sessions_planned,
                 sessions_done, phase, notes, sessions_required,
                 sessions_required_done, sessions_optional, sessions_optional_done)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(week_start) DO UPDATE SET
                planned_tss=excluded.planned_tss,
                actual_tss=excluded.actual_tss,
                sessions_planned=excluded.sessions_planned,
                sessions_done=excluded.sessions_done,
                phase=excluded.phase,
                notes=excluded.notes,
                sessions_required=excluded.sessions_required,
                sessions_required_done=excluded.sessions_required_done,
                sessions_optional=excluded.sessions_optional,
                sessions_optional_done=excluded.sessions_optional_done
            """,
            (
                week_start.isoformat(),
                planned_tss, actual_tss,
                sessions_planned, sessions_done,
                phase, notes,
                sessions_required, sessions_required_done,
                sessions_optional, sessions_optional_done,
            ),
        )
        conn.commit()


def get_weekly_summaries(weeks: int = 16) -> list[dict]:
    """Laatste N weekly summaries, oudste eerst."""
    ensure_migrations()
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


# ── WEEK REFLECTIONS API ──────────────────────────────────────────────────

def record_week_reflection(
    week_start: date,
    *,
    enjoyed: str = "",
    drained: str = "",
    ai_summary: str = "",
) -> None:
    """Upsert een weekreflectie."""
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO week_reflections (week_start, enjoyed, drained, ai_summary)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(week_start) DO UPDATE SET
                enjoyed=excluded.enjoyed,
                drained=excluded.drained,
                ai_summary=COALESCE(excluded.ai_summary, ai_summary)
            """,
            (week_start.isoformat(), enjoyed, drained, ai_summary),
        )
        conn.commit()


def get_week_reflection(week_start: date) -> Optional[dict]:
    """Haal weekreflectie op. None als niet ingevuld."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM week_reflections WHERE week_start = ?",
            (week_start.isoformat(),),
        ).fetchone()
        return dict(row) if row else None


def get_recent_reflections(weeks: int = 4) -> list[dict]:
    """Laatste N weekreflecties, oudste eerst."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM week_reflections ORDER BY week_start DESC LIMIT ?",
            (weeks,),
        ).fetchall()
        return list(reversed([dict(r) for r in rows]))


# ── RECOVERY SCORE ────────────────────────────────────────────────────────

def compute_recovery_score(
    wellness: Optional[dict],
    tsb: float,
) -> dict:
    """Bereken een samengestelde recovery score.

    Combineert morning check-in (als beschikbaar) met TSB.
    Returns {score: float 0-100, level: "go"|"easy"|"rust", message: str}.
    """
    components = []

    # Morning check-in component (0-100 schaal)
    if wellness:
        checkin_vals = [
            wellness.get("sleep_score"),
            wellness.get("energy"),
            wellness.get("soreness"),
            wellness.get("motivation"),
        ]
        checkin_vals = [v for v in checkin_vals if v is not None]
        if checkin_vals:
            # 1-5 schaal → 0-100
            checkin_score = (sum(checkin_vals) / len(checkin_vals) - 1) / 4 * 100
            components.append(("checkin", checkin_score, 0.5))

    # TSB component (genormaliseerd: -30 = 0, +15 = 100)
    # Training in opbouw heeft TSB -10 tot -20, dat is normaal → "easy" range
    tsb_score = max(0, min(100, (tsb + 30) / 45 * 100))
    components.append(("tsb", tsb_score, 0.5 if not components else 0.5))

    # Gewogen gemiddelde
    if not components:
        return {"score": 50, "level": "easy", "message": "Onvoldoende data"}

    total_weight = sum(w for _, _, w in components)
    score = sum(v * w for _, v, w in components) / total_weight

    # Level bepalen — drempels afgestemd op marathontraining in opbouw.
    # TSB -15 met gemiddelde check-in (~47) = "easy", niet "rust".
    if score >= 60:
        level = "go"
        message = "Groen licht — klaar voor een kwaliteitssessie"
    elif score >= 30:
        level = "easy"
        message = "Doe het rustig aan — focus op herstel en Z2"
    else:
        level = "rust"
        message = "Rust is nu de beste training"

    return {"score": round(score, 0), "level": level, "message": message}


# ── SMOKE TEST ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ensure_migrations()
    print(f"OK: {DB_PATH} ready.")
    with _connect() as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        print("Tables:", [r["name"] for r in rows])
