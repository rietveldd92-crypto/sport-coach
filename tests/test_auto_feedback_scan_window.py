"""Tests voor het scanvenster van auto_feedback.find_new_completed_workouts.

De job draait 's ochtends. Een sessie die daarna binnenkomt wacht op de run van
de volgende dag — behalve op zondag, want maandag keek voorheen alleen naar de
nieuwe week. Zo'n sessie kreeg dan nooit feedback en dus ook nooit een
drempelobservatie.
"""
from __future__ import annotations

from datetime import date

import auto_feedback


LAST_SUNDAY = "2026-07-19"   # zondag vóór de week van maandag 2026-07-20
THIS_WEDNESDAY = "2026-07-22"


class _MondayDate(date):
    """date.today() is niet patchbaar (immutable builtin), een subclass wel."""

    @classmethod
    def today(cls):
        return date(2026, 7, 20)


def _patch_window(monkeypatch, events, activities, processed=()):
    """Vang het opgevraagde venster af en lever vaste data terug."""
    seen: dict[str, date] = {}

    def fake_events(start, end):
        seen["start"], seen["end"] = start, end
        return events

    def fake_activities(start, end):
        return activities

    monkeypatch.setattr(auto_feedback.api, "get_events", fake_events)
    monkeypatch.setattr(auto_feedback.api, "get_activities", fake_activities)
    monkeypatch.setattr(auto_feedback, "_load_feedback_log",
                        lambda: {"processed_activities": list(processed)})
    monkeypatch.setattr(auto_feedback, "date", _MondayDate)
    return seen


def _run(day: str, name: str = "Korte drempel - 6x1.8km @ 4:10/km"):
    event = {"id": "e1", "category": "WORKOUT", "type": "Run", "name": name,
             "start_date_local": f"{day}T00:00:00"}
    activity = {"id": "a1", "type": "Run",
                "start_date_local": f"{day}T07:38:00"}
    return event, activity


def test_zondagsessie_van_vorige_week_wordt_alsnog_opgepakt(monkeypatch):
    event, activity = _run(LAST_SUNDAY)
    seen = _patch_window(monkeypatch, [event], [activity])

    found, week_events, week_activities = auto_feedback.find_new_completed_workouts()

    assert [i["activity_id"] for i in found] == ["a1"]
    # Het scanvenster reikt een week terug...
    assert seen["start"] == date(2026, 7, 13)
    # ...maar de weekbundel voor de adaptive cycle blijft déze week.
    assert week_events == []
    assert week_activities == []


def test_al_verwerkte_sessie_krijgt_geen_tweede_feedback(monkeypatch):
    event, activity = _run(LAST_SUNDAY)
    _patch_window(monkeypatch, [event], [activity], processed=["a1"])

    found, _, _ = auto_feedback.find_new_completed_workouts()

    assert found == []


def test_sessie_van_deze_week_blijft_in_de_weekbundel(monkeypatch):
    event, activity = _run(THIS_WEDNESDAY)
    _patch_window(monkeypatch, [event], [activity])

    found, week_events, week_activities = auto_feedback.find_new_completed_workouts()

    assert [i["activity_id"] for i in found] == ["a1"]
    assert week_events == [event]
    assert week_activities == [activity]
