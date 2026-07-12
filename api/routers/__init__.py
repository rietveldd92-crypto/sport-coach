"""Routers volgens UPGRADE_PLAN §7 — dun: Pydantic-modellen + core-calls."""
from __future__ import annotations

from api.routers import (
    admin,
    athlete,
    availability,
    checkin,
    coach,
    fixed_sessions,
    goals,
    placements,
    season,
    sync,
    today,
    trends,
    week,
)

ALL_ROUTERS = [
    admin.router,
    athlete.router,
    today.router,
    week.router,
    placements.router,
    availability.router,
    fixed_sessions.router,
    goals.router,
    season.router,
    checkin.router,
    trends.router,
    sync.router,
    coach.router,
]
