"""Tests voor replan.move_event(swap_availability=True): drag-to-reschedule
waarbij de beschikbaarheidsvensters van bron- en doeldag meeverhuizen."""
from datetime import date, timedelta

import pytest

from core import availability_v2 as av2
from core import replan

WEEK_START = date(2026, 9, 14)  # maandag
TODAY = WEEK_START


def _day(offset: int) -> date:
    return WEEK_START + timedelta(days=offset)


def _event(eid: str, naam: str, d: date, duur_min: int = 60,
           sport: str = "Run") -> dict:
    return {
        "id": eid,
        "name": naam,
        "category": "WORKOUT",
        "type": sport,
        "start_date_local": f"{d.isoformat()}T07:00:00",
        "moving_time": duur_min * 60,
        "icu_training_load": duur_min,
        "description": "test",
    }


@pytest.fixture
def week():
    """Ma en wo hebben een venster, di is rustdag. Sessie A staat op ma."""
    av2.set_override(_day(0), [("07:00", "08:30", "any")])
    av2.set_override(_day(1), [])
    av2.set_override(_day(2), [("06:00", "07:30", "any")])
    for i in range(3, 7):
        av2.set_override(_day(i), [("07:00", "09:00", "any")])
    return [_event("A", "Easy run", _day(0)), _event("B", "Tempo", _day(2))]


def test_zonder_swap_faalt_op_rustdag(week):
    with pytest.raises(ValueError, match="Geen beschikbaarheidsvenster"):
        replan.move_event("A", _day(1), events=week, today=TODAY)


def test_swap_preview_verplaatst_venster_mee(week):
    result = replan.move_event(
        "A", _day(1), events=week, today=TODAY, swap_availability=True)

    assert result["status"] != "INFEASIBLE"
    swap = result["availability_swap"]
    assert swap["from"] == _day(0).isoformat()
    assert swap["to"] == _day(1).isoformat()
    assert swap["to_slots"] == [{"start": "07:00", "end": "08:30", "context": "any"}]
    assert swap["from_slots"] == []  # ma wordt rustdag
    moved = {d["event_id"]: d["to"] for d in result["diff"]}
    assert moved["A"] == _day(1).isoformat()
    # Preview schrijft niets weg.
    assert av2.get_override(_day(1)) == []
    assert result["applied"] is False


def test_swap_apply_schrijft_beide_overrides(week, monkeypatch):
    from agents import workout_actions

    monkeypatch.setattr(workout_actions, "apply_move",
                        lambda *a, **k: None)
    result = replan.move_event(
        "A", _day(1), events=week, today=TODAY, apply=True,
        swap_availability=True)

    assert result["applied"] is True, result["errors"]
    di = av2.get_override(_day(1))
    assert [(s["start"], s["end"]) for s in di] == [("07:00", "08:30")]
    assert av2.get_override(_day(0)) == []  # rustdag-marker


def test_swap_met_sessie_op_doeldag_wisselt_beide(week, monkeypatch):
    """A (ma 07:00-08:30) naar wo (06:00-07:30, waar B staat): vensters
    wisselen en B schuift terug naar ma."""
    from agents import workout_actions

    monkeypatch.setattr(workout_actions, "apply_move",
                        lambda *a, **k: None)
    result = replan.move_event(
        "A", _day(2), events=week, today=TODAY, apply=True,
        swap_availability=True)

    assert result["applied"] is True, result["errors"]
    by_id = {p["event_id"]: p["date"] for p in result["placements"]}
    assert by_id["A"] == _day(2).isoformat()
    assert by_id["B"] == _day(0).isoformat()
    assert [(s["start"], s["end"]) for s in av2.get_override(_day(2))] \
        == [("07:00", "08:30")]
    assert [(s["start"], s["end"]) for s in av2.get_override(_day(0))] \
        == [("06:00", "07:30")]


def test_swap_zonder_venster_aan_beide_kanten_faalt(week):
    av2.set_override(_day(0), [])
    with pytest.raises(ValueError, match="Geen beschikbaarheidsvenster"):
        replan.move_event(
            "A", _day(1), events=week, today=TODAY, swap_availability=True)
