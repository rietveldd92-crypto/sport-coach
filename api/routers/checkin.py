"""POST /api/checkin — wellness-sliders + blessuresignalen.

Vervangt het adjust.py-CLI-pad: signalen gaan door dezelfde
injury_guard.analyze()-buffer (direct vs buffered).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from core import views

router = APIRouter(tags=["checkin"])


class CheckinRequest(BaseModel):
    sleep_score: Optional[int] = Field(default=None, ge=1, le=5)
    energy: Optional[int] = Field(default=None, ge=1, le=5)
    soreness: Optional[int] = Field(default=None, ge=1, le=5)
    motivation: Optional[int] = Field(default=None, ge=1, le=5)
    injury_signals: list[str] = Field(
        default_factory=list,
        description="bijv. knie_pijn, rug_trekkend, heup_instabiel",
    )
    notes: Optional[str] = None


@router.post("/checkin")
def post_checkin(body: CheckinRequest) -> dict:
    return views.process_checkin(
        sleep_score=body.sleep_score,
        energy=body.energy,
        soreness=body.soreness,
        motivation=body.motivation,
        injury_signals=body.injury_signals,
        notes=body.notes,
    )


@router.get("/checkin/history")
def get_checkin_history(days: int = Query(default=14, ge=1, le=90)) -> dict:
    """Signaalhistorie + wellness-records voor het Jij-scherm
    (maakt de injury_guard-buffer transparant, UPGRADE_PLAN §6)."""
    return views.checkin_history(days=days)
