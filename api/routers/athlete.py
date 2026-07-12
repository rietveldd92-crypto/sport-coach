"""Athlete settings: threshold pace, suggestions and RPE."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agents import threshold_model

router = APIRouter(tags=["athlete"])


class ThresholdPacePut(BaseModel):
    sec_per_km: int = Field(ge=220, le=320)
    reason: str = "handmatig"


class SuggestionResolve(BaseModel):
    accepted: bool


class RaceResultIn(BaseModel):
    distance_m: int = Field(gt=0)
    time_sec: int = Field(gt=0)


class RpeIn(BaseModel):
    rpe: int = Field(ge=1, le=10)
    date: str | None = None


@router.get("/athlete/threshold-pace")
def get_threshold_pace() -> dict:
    return threshold_model.threshold_summary()


@router.put("/athlete/threshold-pace")
def put_threshold_pace(body: ThresholdPacePut) -> dict:
    log = threshold_model.set_threshold_pace(
        body.sec_per_km,
        body.reason or "handmatig",
        source="manual",
    )
    return {"threshold_pace_sec_per_km": threshold_model.get_threshold_pace(), "log": log}


@router.get("/athlete/threshold-pace/suggestion")
def get_threshold_suggestion() -> dict:
    return {"suggestion": threshold_model.pending_suggestion()}


@router.post("/athlete/threshold-pace/suggestion/{suggestion_id}")
def resolve_threshold_suggestion(suggestion_id: int, body: SuggestionResolve) -> dict:
    try:
        suggestion = threshold_model.resolve_suggestion(suggestion_id, body.accepted)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "suggestion": suggestion,
        "threshold_pace_sec_per_km": threshold_model.get_threshold_pace(),
    }


@router.post("/athlete/race-result")
def post_race_result(body: RaceResultIn) -> dict:
    suggestion = threshold_model.suggest_from_race(body.distance_m, body.time_sec)
    return {"suggestion": suggestion}


@router.post("/workout/{activity_id}/rpe")
def post_workout_rpe(activity_id: str, body: RpeIn) -> dict:
    try:
        rpe = threshold_model.record_rpe(activity_id, body.rpe, body.date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"rpe": rpe}
