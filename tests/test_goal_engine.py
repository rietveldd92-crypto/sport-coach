"""Tests voor core/goal_engine.py — CRUD, één-A-doel-regel, weeks_to_goal."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from core import goal_engine
from core.goal_engine import Goal


def _marathon(**overrides) -> Goal:
    base = dict(
        type="marathon", sport="run", event_date=date(2026, 10, 18),
        target_value="2:59:00", priority="A", status="active",
    )
    base.update(overrides)
    return Goal(**base)


def test_create_get_list_roundtrip():
    created = goal_engine.create_goal(_marathon())
    assert created.id is not None
    assert created.created_at

    fetched = goal_engine.get_goal(created.id)
    assert fetched is not None
    assert fetched.type == "marathon"
    assert fetched.event_date == date(2026, 10, 18)
    assert fetched.target_value == "2:59:00"

    all_goals = goal_engine.list_goals()
    assert [g.id for g in all_goals] == [created.id]


def test_hoogstens_een_actief_a_doel():
    goal_engine.create_goal(_marathon())
    with pytest.raises(ValueError, match="actief A-doel"):
        goal_engine.create_goal(_marathon(type="10k",
                                          event_date=date(2026, 7, 1),
                                          target_value="0:42:00"))


def test_b_doel_mag_naast_a_doel():
    a = goal_engine.create_goal(_marathon())
    b = goal_engine.create_goal(_marathon(
        type="10k", priority="B", event_date=date(2026, 7, 5),
        target_value="0:42:00"))
    assert b.id != a.id
    assert goal_engine.get_active_goal().id == a.id
    inter = goal_engine.get_intermediate_goals(a)
    assert [g.id for g in inter] == [b.id]


def test_nieuw_a_doel_na_afsluiten():
    a = goal_engine.create_goal(_marathon())
    goal_engine.update_goal(a.id, status="completed")
    assert goal_engine.get_active_goal() is None
    a2 = goal_engine.create_goal(_marathon(event_date=date(2027, 4, 11)))
    assert goal_engine.get_active_goal().id == a2.id


def test_update_bewaakt_een_a_doel_regel():
    a = goal_engine.create_goal(_marathon())
    b = goal_engine.create_goal(_marathon(
        type="10k", priority="B", event_date=date(2026, 7, 5)))
    with pytest.raises(ValueError, match="actief A-doel"):
        goal_engine.update_goal(b.id, priority="A")
    # Na afronden van het A-doel mag de promotie wél
    goal_engine.update_goal(a.id, status="abandoned")
    promoted = goal_engine.update_goal(b.id, priority="A")
    assert promoted.priority == "A"
    assert goal_engine.get_active_goal().id == b.id


def test_delete_verwijdert_ook_plan_weeks():
    from core.periodization_generator import (
        AthleteProfile, generate_plan, load_plan_weeks, persist_plan_weeks,
    )
    a = goal_engine.create_goal(_marathon())
    result = generate_plan(a, AthleteProfile(), date(2026, 4, 6))
    persist_plan_weeks(a.id, result.weeks)
    assert len(load_plan_weeks(a.id)) == 28

    goal_engine.delete_goal(a.id)
    assert goal_engine.get_goal(a.id) is None
    assert load_plan_weeks(a.id) == []


def test_weeks_to_goal():
    a = goal_engine.create_goal(_marathon())
    today = a.event_date - timedelta(weeks=10)
    assert goal_engine.weeks_to_goal(a, today=today) == 10
    assert goal_engine.weeks_to_goal(a, today=a.event_date) == 0
    # Na de racedag niet negatief
    assert goal_engine.weeks_to_goal(a, today=a.event_date + timedelta(days=30)) == 0
    # Default: actieve A-doel
    assert goal_engine.weeks_to_goal(today=today) == 10


def test_ongeldige_velden_geweigerd():
    with pytest.raises(Exception):
        Goal(type="ultra", sport="run", event_date=date(2026, 10, 18))
    with pytest.raises(Exception):
        _marathon(priority="D")
