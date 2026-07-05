"""GET/POST /api/goals · DELETE /api/goals/{id} · POST /api/goals/{id}/regenerate."""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core import goal_engine, views

router = APIRouter(tags=["goals"])


class GoalCreate(BaseModel):
    type: Literal["marathon", "half", "10k", "5k", "gran_fondo", "ftp",
                  "triathlon", "custom"]
    sport: Literal["run", "ride", "multi"] = "run"
    event_date: date
    target_value: Optional[str] = None      # "2:59:00" | "310W"
    priority: Literal["A", "B", "C"] = "A"


@router.get("/goals")
def list_goals(status: Optional[str] = None,
               priority: Optional[str] = None) -> dict:
    goals = goal_engine.list_goals(status=status, priority=priority)
    return {"goals": [g.model_dump(mode="json") for g in goals]}


@router.post("/goals", status_code=201)
def create_goal(body: GoalCreate) -> dict:
    """Maak een doel aan; A-doelen krijgen direct een gegenereerd +
    gepersisteerd macroplan (plan_weeks)."""
    try:
        return views.create_goal_with_plan(body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.delete("/goals/{goal_id}", status_code=204)
def delete_goal(goal_id: int) -> None:
    try:
        views.delete_goal(goal_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/goals/{goal_id}/regenerate")
def regenerate_goal(goal_id: int, force: bool = False) -> dict:
    """Rolling re-periodisatie (weekly_recalibration, UPGRADE_PLAN §4.2).

    ``force=true`` negeert de ±10%-uitvoeringsband — nodig om een net
    toegevoegd B/C-tussendoel (mini-taper) meteen te stansen.
    """
    try:
        return views.regenerate_goal(goal_id, force=force)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
