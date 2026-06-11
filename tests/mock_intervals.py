"""Mock van intervals_client voor integratietests (Fase 3, UPGRADE_PLAN §8).

Sinds Fase 4 leeft de fixture-data in :mod:`core.fake_intervals`, zodat
de pytest-suite en de offline ``INTERVALS_FAKE``-modus exact dezelfde
bron delen. Deze module blijft bestaan als test-facing import-pad.

Monkeypatch-gebaseerd: :func:`install` vervangt de netwerk-functies van
``intervals_client`` door een in-memory fixture. Omdat alle modules
``import intervals_client as api`` doen (module-object, geen
from-imports), werkt patchen op moduleniveau overal door — ook diep in
plan_week/week_planner/auto_feedback.
"""
from __future__ import annotations

from core.fake_intervals import (  # noqa: F401
    PATCHED,
    MockIntervals,
    _activity,
    _event,
    install,
)
