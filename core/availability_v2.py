"""Availability v2 — beschikbaarheid als tijdvensters (UPGRADE_PLAN §3/§5).

Bronnen, in volgorde van prioriteit per dag:

1. ``availability_override`` (history.db) — expliciete vensters voor een
   datum. Een ``00:00``–``00:00`` rij is de rustdag-marker ("bewust 0").
2. ``availability_pattern`` (history.db) — terugkerend weekpatroon per
   weekdag (0=ma .. 6=zo). Ook hier is een zero-length rij = rustdag.
3. Legacy minuten-dict uit ``shared.load_state()["availability"]`` —
   één venster vanaf 07:00 met de opgegeven minuten. Dit pad bestaat
   alleen nog zolang de DB niet gemigreerd is (state.json-fallback).

``agents/availability.py`` blijft de compat-laag voor code die in
minuten denkt; die leidt zijn minuten af van deze slots.
"""
from __future__ import annotations

from datetime import date as date_type, timedelta
from typing import Literal, Optional

from pydantic import BaseModel

DEFAULT_SLOT_START = "07:00"

Context = Literal["any", "indoor_only", "outdoor_only"]


# ── TIJD-HELPERS ────────────────────────────────────────────────────────────

def to_minutes(hhmm: str) -> int:
    """'HH:MM' → minuten sinds middernacht. Tolerant voor 'HH:MM:SS'."""
    try:
        parts = str(hhmm).split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except (ValueError, IndexError, AttributeError):
        return 0


def to_hhmm(minutes: int) -> str:
    minutes = max(0, min(int(minutes), 23 * 60 + 59))
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


# ── MODEL ───────────────────────────────────────────────────────────────────

class Slot(BaseModel):
    """Eén beschikbaarheidsvenster op een concrete datum."""

    date: date_type
    start: str  # "HH:MM"
    end: str    # "HH:MM"
    context: Context = "any"

    @property
    def start_min(self) -> int:
        return to_minutes(self.start)

    @property
    def end_min(self) -> int:
        return to_minutes(self.end)

    @property
    def duration_min(self) -> int:
        return max(0, self.end_min - self.start_min)


# ── DB-ACCESS ───────────────────────────────────────────────────────────────

def _conn():
    import history_db

    history_db.ensure_migrations()
    return history_db._connect()


def _override_rows(d: date_type) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT slot_start, slot_end, context FROM availability_override"
            " WHERE date = ? ORDER BY slot_start",
            (d.isoformat(),),
        ).fetchall()
    return [dict(r) for r in rows]


def _pattern_rows(weekday: int) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT slot_start, slot_end, context FROM availability_pattern"
            " WHERE weekday = ? ORDER BY slot_start",
            (weekday,),
        ).fetchall()
    return [dict(r) for r in rows]


def _rows_to_slots(d: date_type, rows: list[dict]) -> list[Slot]:
    """Zero-length rijen (rustdag-marker) worden weggefilterd."""
    out: list[Slot] = []
    for r in rows:
        start, end = r.get("slot_start") or "00:00", r.get("slot_end") or "00:00"
        if to_minutes(end) <= to_minutes(start):
            continue  # marker of corrupt — telt als 0 minuten
        out.append(Slot(date=d, start=start, end=end,
                        context=(r.get("context") or "any")))
    return out


# ── LEZEN ───────────────────────────────────────────────────────────────────

def day_slots(d: date_type) -> tuple[list[Slot], bool]:
    """Slots voor één dag. Returnt (slots, known).

    known=False betekent: geen override, geen patroon, geen legacy-waarde —
    de dag is simpelweg nooit ingesteld (legacy ``None``).
    Een rustdag is (lege lijst, known=True).
    """
    rows = _override_rows(d)
    if rows:
        return _rows_to_slots(d, rows), True

    rows = _pattern_rows(d.weekday())
    if rows:
        return _rows_to_slots(d, rows), True

    # Legacy fallback: minuten-dict (alleen relevant op het state.json-pad;
    # op de DB is availability_override al de bron en is dit dict leeg
    # voor datums zonder override).
    try:
        from shared import load_state

        minutes = (load_state() or {}).get("availability", {}).get(d.isoformat())
    except Exception:
        minutes = None
    if minutes is None:
        return [], False
    if int(minutes) <= 0:
        return [], True
    start_min = to_minutes(DEFAULT_SLOT_START)
    return [Slot(date=d, start=DEFAULT_SLOT_START,
                 end=to_hhmm(start_min + int(minutes)))], True


def get_slots_for_week(week_start: date_type) -> dict[date_type, list[Slot]]:
    """Slots per dag voor 7 dagen vanaf week_start (rustdag/onbekend = [])."""
    return {
        d: day_slots(d)[0]
        for d in (week_start + timedelta(days=i) for i in range(7))
    }


def get_override(d: date_type) -> Optional[list[dict]]:
    """Override-vensters voor één datum, of None als er geen override is.

    Een expliciete rustdag (00:00-marker) komt terug als lege lijst.
    Gebruikt door de API (GET /api/availability/override/{date}).
    """
    rows = _override_rows(d)
    if not rows:
        return None
    return [
        {"start": s.start, "end": s.end, "context": s.context}
        for s in _rows_to_slots(d, rows)
    ]


def minutes_for_day(d: date_type) -> Optional[int]:
    """Compat: totaal aantal minuten voor een dag, None = nooit ingesteld."""
    slots, known = day_slots(d)
    if not known:
        return None
    return sum(s.duration_min for s in slots)


# ── SCHRIJVEN ───────────────────────────────────────────────────────────────

def _normalize_slots(raw) -> list[tuple[str, str, str]]:
    """Accepteer Slot-objecten, dicts of (start, end[, context])-tuples."""
    out: list[tuple[str, str, str]] = []
    for item in raw or []:
        if isinstance(item, Slot):
            out.append((item.start, item.end, item.context))
        elif isinstance(item, dict):
            out.append((item["start"], item["end"], item.get("context") or "any"))
        else:
            start, end = item[0], item[1]
            ctx = item[2] if len(item) > 2 else "any"
            out.append((start, end, ctx))
    return out


def set_override(d: date_type, slots) -> None:
    """Vervang de override-vensters voor een datum.

    ``slots=[]`` schrijft de expliciete rustdag-marker (00:00–00:00).
    Gebruik :func:`clear_override` om de override te verwijderen (terug
    naar patroon/legacy).
    """
    norm = _normalize_slots(slots)
    with _conn() as conn:
        conn.execute("DELETE FROM availability_override WHERE date = ?",
                     (d.isoformat(),))
        if not norm:
            conn.execute(
                "INSERT INTO availability_override (date, slot_start, slot_end)"
                " VALUES (?, '00:00', '00:00')",
                (d.isoformat(),),
            )
        else:
            conn.executemany(
                "INSERT OR REPLACE INTO availability_override"
                " (date, slot_start, slot_end, context) VALUES (?, ?, ?, ?)",
                [(d.isoformat(), s, e, c) for s, e, c in norm],
            )
        conn.commit()


def clear_override(d: date_type) -> None:
    with _conn() as conn:
        conn.execute("DELETE FROM availability_override WHERE date = ?",
                     (d.isoformat(),))
        conn.commit()


def set_override_minutes(d: date_type, minutes: int) -> None:
    """Compat-setter: minuten → één venster 07:00 + minuten (0 = rustdag).

    Preserveert bestaande rijke vensters als het totaal niet wijzigt —
    een no-op save mag geen slot-detail (meerdere vensters, contexts)
    platslaan naar één 07:00-venster.
    """
    minutes = max(0, int(minutes or 0))
    existing = _override_rows(d)
    if existing:
        current = sum(
            max(0, to_minutes(r["slot_end"]) - to_minutes(r["slot_start"]))
            for r in existing
        )
        if current == minutes:
            return  # ongewijzigd — laat slot-detail intact
    if minutes <= 0:
        set_override(d, [])
        return
    start_min = to_minutes(DEFAULT_SLOT_START)
    set_override(d, [(DEFAULT_SLOT_START, to_hhmm(start_min + minutes))])


def set_pattern(weekday: int, slots) -> None:
    """Vervang het weekpatroon voor één weekdag (0=ma .. 6=zo).

    ``slots=[]`` = expliciete rustdag in het patroon;
    ``slots=None`` = verwijder het patroon voor die weekdag.
    """
    if not 0 <= int(weekday) <= 6:
        raise ValueError(f"weekday moet 0..6 zijn, kreeg {weekday}")
    with _conn() as conn:
        conn.execute("DELETE FROM availability_pattern WHERE weekday = ?",
                     (int(weekday),))
        if slots is None:
            conn.commit()
            return
        norm = _normalize_slots(slots)
        if not norm:
            conn.execute(
                "INSERT INTO availability_pattern (weekday, slot_start, slot_end)"
                " VALUES (?, '00:00', '00:00')",
                (int(weekday),),
            )
        else:
            conn.executemany(
                "INSERT OR REPLACE INTO availability_pattern"
                " (weekday, slot_start, slot_end, context) VALUES (?, ?, ?, ?)",
                [(int(weekday), s, e, c) for s, e, c in norm],
            )
        conn.commit()


def get_pattern() -> dict[int, list[dict]]:
    """Volledige weekpatroon: {weekday: [{slot_start, slot_end, context}]}."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT weekday, slot_start, slot_end, context"
            " FROM availability_pattern ORDER BY weekday, slot_start"
        ).fetchall()
    out: dict[int, list[dict]] = {}
    for r in rows:
        out.setdefault(r["weekday"], []).append(
            {"slot_start": r["slot_start"], "slot_end": r["slot_end"],
             "context": r["context"] or "any"}
        )
    return out
