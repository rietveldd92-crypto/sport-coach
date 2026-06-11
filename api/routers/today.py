"""GET /api/today — workout vandaag + checkin-status + morgen-preview."""
from __future__ import annotations

from fastapi import APIRouter

from core import views

router = APIRouter(tags=["today"])


@router.get("/today")
def get_today() -> dict:
    return views.today_view()
