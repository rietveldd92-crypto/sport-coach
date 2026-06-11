"""POST /api/placements/{event_id}/move en /swap."""
from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core import views

router = APIRouter(tags=["placements"])


class MoveRequest(BaseModel):
    target_date: date


class SwapRequest(BaseModel):
    category: Literal["makkelijker", "vergelijkbaar", "anders", "harder"]


@router.post("/placements/{event_id}/move")
def move_placement(event_id: str, body: MoveRequest,
                   apply: bool = False) -> dict:
    """Drag → solver met deze sessie locked op de doeldatum → diff.

    ``?apply=true`` voert het diff ook echt door (intervals.icu +
    placements-tabel); zonder die query-param is het een preview.
    """
    try:
        return views.move_placement(event_id, body.target_date, apply=apply)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/placements/{event_id}/swap")
def swap_placement(event_id: str, body: SwapRequest) -> dict:
    """Workout-swap binnen een categorie (zelfde flow als de Streamlit-UI)."""
    try:
        return views.swap_event(event_id, body.category)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
