"""CRUD voor vaste terugkerende sessies."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import history_db

router = APIRouter(prefix="/fixed-sessions", tags=["fixed-sessions"])


class FixedSessionPut(BaseModel):
    name: str = "Forenzen-rit"
    sport: Literal["VirtualRide", "Ride", "Run", "WeightTraining"] = "VirtualRide"
    duration_min: int = Field(ge=1, le=600)
    if_estimate: float = Field(default=0.65, ge=0.1, le=1.5)
    enabled: bool = True


@router.get("")
def list_fixed_sessions() -> dict:
    return {"fixed_sessions": history_db.list_fixed_sessions()}


@router.put("/{weekday}")
def put_fixed_session(weekday: int, body: FixedSessionPut) -> dict:
    if not 0 <= weekday <= 6:
        raise HTTPException(status_code=422,
                            detail=f"weekday moet 0..6 zijn, kreeg {weekday}")
    history_db.upsert_fixed_session(
        weekday,
        name=body.name,
        sport=body.sport,
        duration_min=body.duration_min,
        if_estimate=body.if_estimate,
        enabled=body.enabled,
    )
    return {"fixed_session": history_db.get_fixed_session(weekday)}


@router.delete("/{weekday}")
def delete_fixed_session(weekday: int) -> dict:
    if not 0 <= weekday <= 6:
        raise HTTPException(status_code=422,
                            detail=f"weekday moet 0..6 zijn, kreeg {weekday}")
    history_db.delete_fixed_session(weekday)
    return {"ok": True}
