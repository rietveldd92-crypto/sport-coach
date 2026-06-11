"""GET /api/season — macroplan + CTL-paden + haalbaarheidsadvies."""
from __future__ import annotations

from fastapi import APIRouter

from core import views

router = APIRouter(tags=["season"])


@router.get("/season")
def get_season() -> dict:
    return views.season_view()
