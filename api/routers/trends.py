"""GET /api/trends — ctl/atl/tsb-series, weekvolume, hrv."""
from __future__ import annotations

from fastapi import APIRouter

from core import views

router = APIRouter(tags=["trends"])


@router.get("/trends")
def get_trends() -> dict:
    return views.trends_view()
