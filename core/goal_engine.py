"""Goal-engine — CRUD op de ``goals``-tabel (UPGRADE_PLAN §4, Fase 2).

Een doel (Goal) is een race of prestatiedoel waar een macroplan
(``plan_weeks``) aan hangt. Regels:

- Hoogstens één *actief A-doel* tegelijk — dat doel bezit het macroplan.
- B/C-doelen zijn tussendoelen (mini-taper in het macroplan van het A-doel).

Gebruik:
    from core import goal_engine

    goal = goal_engine.create_goal(goal_engine.Goal(
        type="marathon", sport="run", event_date=date(2026, 10, 18),
        target_value="2:59:00", priority="A",
    ))
    active = goal_engine.get_active_goal()
    weeks = goal_engine.weeks_to_goal(active)
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

GOAL_TYPES = (
    "marathon", "half", "10k", "5k", "gran_fondo", "ftp", "triathlon", "custom",
)


class Goal(BaseModel):
    """Pydantic-model voor één rij in de ``goals``-tabel."""

    id: Optional[int] = None
    type: Literal[
        "marathon", "half", "10k", "5k", "gran_fondo", "ftp", "triathlon", "custom"
    ]
    sport: Literal["run", "ride", "multi"] = "run"
    event_date: date
    target_value: Optional[str] = None       # "2:59:00" | "310W" | None
    priority: Literal["A", "B", "C"] = "A"
    status: Literal["active", "completed", "abandoned"] = "active"
    created_at: Optional[str] = None

    model_config = {"extra": "forbid"}


def _connect():
    import history_db
    history_db.ensure_migrations()
    return history_db._connect()


def _row_to_goal(row) -> Goal:
    return Goal(
        id=row["id"],
        type=row["type"],
        sport=row["sport"],
        event_date=date.fromisoformat(row["event_date"]),
        target_value=row["target_value"],
        priority=row["priority"] or "A",
        status=row["status"] or "active",
        created_at=row["created_at"],
    )


# ── CRUD ──────────────────────────────────────────────────────────────────

def create_goal(goal: Goal) -> Goal:
    """Maak een goal aan. Hoogstens één actief A-doel tegelijk (ValueError)."""
    if goal.priority == "A" and goal.status == "active":
        existing = get_active_goal()
        if existing is not None:
            raise ValueError(
                f"Er is al een actief A-doel (id={existing.id}, {existing.type} "
                f"op {existing.event_date}). Sluit dat eerst af (completed/"
                f"abandoned) of maak dit doel B/C."
            )
    created_at = goal.created_at or datetime.now().isoformat()
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO goals (type, sport, event_date, target_value,
                               priority, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (goal.type, goal.sport, goal.event_date.isoformat(),
             goal.target_value, goal.priority, goal.status, created_at),
        )
        conn.commit()
        new_id = cur.lastrowid
    return goal.model_copy(update={"id": new_id, "created_at": created_at})


def get_goal(goal_id: int) -> Optional[Goal]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM goals WHERE id = ?", (goal_id,)
        ).fetchone()
    return _row_to_goal(row) if row else None


def list_goals(status: Optional[str] = None,
               priority: Optional[str] = None) -> list[Goal]:
    """Alle goals, optioneel gefilterd, gesorteerd op event_date."""
    query = "SELECT * FROM goals"
    clauses, params = [], []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if priority:
        clauses.append("priority = ?")
        params.append(priority)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY event_date"
    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [_row_to_goal(r) for r in rows]


def update_goal(goal_id: int, **fields) -> Goal:
    """Update velden van een goal. Bewaakt de één-actief-A-doel-regel."""
    current = get_goal(goal_id)
    if current is None:
        raise ValueError(f"Goal {goal_id} bestaat niet.")

    updated = current.model_copy(update=fields)
    # Validatie via Pydantic (Literal-velden)
    updated = Goal(**updated.model_dump())

    if updated.priority == "A" and updated.status == "active":
        other = get_active_goal()
        if other is not None and other.id != goal_id:
            raise ValueError(
                f"Er is al een actief A-doel (id={other.id}). "
                f"Hoogstens één actief A-doel tegelijk."
            )

    with _connect() as conn:
        conn.execute(
            """
            UPDATE goals SET type=?, sport=?, event_date=?, target_value=?,
                             priority=?, status=?
            WHERE id=?
            """,
            (updated.type, updated.sport, updated.event_date.isoformat(),
             updated.target_value, updated.priority, updated.status, goal_id),
        )
        conn.commit()
    return updated


def delete_goal(goal_id: int) -> None:
    """Verwijder een goal inclusief bijbehorende plan_weeks."""
    with _connect() as conn:
        conn.execute("DELETE FROM plan_weeks WHERE goal_id = ?", (goal_id,))
        conn.execute("DELETE FROM goals WHERE id = ?", (goal_id,))
        conn.commit()


# ── HELPERS ───────────────────────────────────────────────────────────────

def get_active_goal() -> Optional[Goal]:
    """Het actieve A-doel, of None. (Er is er hoogstens één.)"""
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM goals
            WHERE status = 'active' AND priority = 'A'
            ORDER BY event_date LIMIT 1
            """
        ).fetchone()
    return _row_to_goal(row) if row else None


def get_intermediate_goals(a_goal: Goal) -> list[Goal]:
    """Actieve B/C-doelen met event_date vóór het A-doel (mini-tapers)."""
    out = []
    for g in list_goals(status="active"):
        if g.priority in ("B", "C") and g.event_date < a_goal.event_date:
            out.append(g)
    return out


def weeks_to_goal(goal: Optional[Goal] = None, today: Optional[date] = None) -> int:
    """Hele weken tot de event_date van ``goal`` (default: actieve A-doel)."""
    if goal is None:
        goal = get_active_goal()
    if goal is None:
        return 0
    if today is None:
        today = date.today()
    return max(0, (goal.event_date - today).days // 7)
