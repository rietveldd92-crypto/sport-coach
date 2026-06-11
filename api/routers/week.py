"""GET /api/week/{week_start} + POST /api/week/{week_start}/plan."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter

from core import views

router = APIRouter(tags=["week"])


@router.get("/week/{week_start}")
def get_week(week_start: date) -> dict:
    """Placements + events + activities (gematcht) + availability-slots."""
    return views.week_view(week_start)


@router.post("/week/{week_start}/plan")
def plan_week(week_start: date) -> dict:
    """(Her)plan de week via de bestaande plan-flow + slot-solver."""
    return views.plan_week(week_start)
