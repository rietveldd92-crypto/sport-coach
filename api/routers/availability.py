"""GET/PUT /api/availability/pattern · GET/PUT /api/availability/override/{date}."""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core import availability_v2 as av2

router = APIRouter(tags=["availability"])

TIME_PATTERN = r"^\d{2}:\d{2}$"


class SlotIn(BaseModel):
    start: str = Field(pattern=TIME_PATTERN, examples=["06:00"])
    end: str = Field(pattern=TIME_PATTERN, examples=["07:30"])
    context: Literal["any", "indoor_only", "outdoor_only"] = "any"


class PatternPut(BaseModel):
    """Per weekdag (0=ma..6=zo) de nieuwe vensters.

    ``[]`` = expliciete rustdag, ``null`` = patroon voor die dag wissen.
    Alleen meegegeven weekdagen worden vervangen.
    """

    days: dict[int, Optional[list[SlotIn]]]


class OverridePut(BaseModel):
    """``[]`` = rustdag-marker, ``null`` = override verwijderen
    (terug naar het weekpatroon)."""

    slots: Optional[list[SlotIn]] = None


def _to_tuples(slots: list[SlotIn]) -> list[tuple[str, str, str]]:
    return [(s.start, s.end, s.context) for s in slots]


@router.get("/availability/pattern")
def get_pattern() -> dict:
    return {"pattern": av2.get_pattern()}


@router.put("/availability/pattern")
def put_pattern(body: PatternPut) -> dict:
    for weekday, slots in body.days.items():
        if not 0 <= weekday <= 6:
            raise HTTPException(status_code=422,
                                detail=f"weekday moet 0..6 zijn, kreeg {weekday}")
        av2.set_pattern(weekday, None if slots is None else _to_tuples(slots))
    return {"pattern": av2.get_pattern()}


@router.get("/availability/override/{day}")
def get_override(day: date) -> dict:
    return {"date": day.isoformat(), "slots": av2.get_override(day)}


@router.put("/availability/override/{day}")
def put_override(day: date, body: OverridePut) -> dict:
    if body.slots is None:
        av2.clear_override(day)
    else:
        av2.set_override(day, _to_tuples(body.slots))
    return {"date": day.isoformat(), "slots": av2.get_override(day)}
