from datetime import date, timedelta

from core import availability_v2 as av2
from tests.mock_intervals import MockIntervals, _event, install


def _session(name: str, day: str) -> dict:
    return {
        "naam": name,
        "type": "run_threshold_short",
        "duur_min": 60,
        "tss_geschat": 60,
        "sport": "Run",
        "beschrijving": "- 60m 4:20/km Pace",
        "dag": day,
        "plaatsing_reden": "test",
    }


def test_replan_lopende_week_laat_verleden_volledig_staan(monkeypatch):
    from agents import week_planner

    monday = date(2026, 8, 3)
    today = monday + timedelta(days=3)
    mock = MockIntervals(today=today)
    mock.events = [
        _event("past", monday, "Oude drempel", "Run", 70),
        _event("future", monday + timedelta(days=5), "Oude duurloop", "Run", 80),
    ]
    install(monkeypatch, mock)
    for weekday in range(7):
        av2.set_pattern(weekday, [("07:00", "09:00")])

    created = week_planner.build_week(
        monday,
        [_session("Nieuwe drempel", "maandag"),
         _session("Nieuwe duurloop", "zaterdag")],
        [],
        injury_guard={"status": "groen", "strength_allowed": False},
        load_manager={"current_phase": "basis_I", "recommended_weekly_tss": 200,
                      "ctl": 40, "atl": 40, "tsb": 0},
        dry_run=False,
        preplanned=True,
        today=today,
    )

    assert not any(call[:2] == ("delete_event", "past") for call in mock.calls)
    assert any(call[:2] == ("delete_event", "future") for call in mock.calls)
    assert all(event["start_date_local"][:10] >= today.isoformat()
               for event in created)
    assert any(event["name"] == "Oude drempel" for event in mock.events)
