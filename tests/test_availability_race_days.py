"""Racedagen zijn bezet voor de planner.

De planner kent alleen `WORKOUT`-events. Een RACE_A/B/C-event zag hij niet,
dus plande hij er vrolijk een sessie bovenop — en omgekeerd wiste de
weekplanner een race die als `WORKOUT` op de kalender stond.
"""
from datetime import date

import pytest

from agents import availability


MONDAY = date(2026, 8, 31)  # Big 10 valt op zaterdag 5 september


def _events(*rows):
    return [
        {"category": cat, "start_date_local": f"{day}T09:00:00", "name": name}
        for cat, day, name in rows
    ]


def test_race_event_maakt_de_dag_bezet(monkeypatch):
    fake = type("API", (), {"get_events": staticmethod(
        lambda *_a, **_k: _events(("RACE_B", "2026-09-05", "Big 10")))})
    monkeypatch.setitem(__import__("sys").modules, "intervals_client", fake)

    assert availability.get_race_day_names(MONDAY) == ["zaterdag"]


def test_gewone_workouts_blokkeren_niets(monkeypatch):
    fake = type("API", (), {"get_events": staticmethod(
        lambda *_a, **_k: _events(("WORKOUT", "2026-09-05", "Drempel 4x2km"),
                                  ("NOTE", "2026-09-03", "Dagelijkse rehab")))})
    monkeypatch.setitem(__import__("sys").modules, "intervals_client", fake)

    assert availability.get_race_day_names(MONDAY) == []


def test_race_buiten_de_week_telt_niet_mee(monkeypatch):
    fake = type("API", (), {"get_events": staticmethod(
        lambda *_a, **_k: _events(("RACE_A", "2026-10-18", "Amsterdam")))})
    monkeypatch.setitem(__import__("sys").modules, "intervals_client", fake)

    assert availability.get_race_day_names(MONDAY) == []


def test_onbereikbare_api_blokkeert_de_planner_niet(monkeypatch):
    def _boom(*_a, **_k):
        raise RuntimeError("intervals.icu down")

    fake = type("API", (), {"get_events": staticmethod(_boom)})
    monkeypatch.setitem(__import__("sys").modules, "intervals_client", fake)

    assert availability.get_race_day_names(MONDAY) == []
