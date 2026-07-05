"""Tests voor agents/adherence.py — de consistentie-laag (80-90%-filosofie).

Dekt:
- classificatie verplicht/optioneel per sessie(-week)
- rolling analyze() over weekly_summary: streefband, geen kantelen op 1
  slechte week, trend
- record_week(): matcht placements tegen activities en telt required/optional
"""
from __future__ import annotations

from datetime import date

import history_db
from agents import adherence


# ── classify_priorities ─────────────────────────────────────────────────────

def test_long_run_and_quality_are_verplicht():
    week = [
        {"dag": "zondag", "type": "lange_duur", "naam": "Lange duurloop"},
        {"dag": "dinsdag", "type": "drempel", "naam": "Drempelduurloop"},
    ]
    tagged = adherence.classify_priorities(week)
    assert all(s["priority"] == "verplicht" for s in tagged)


def test_first_easy_run_verplicht_rest_optioneel():
    week = [
        {"dag": "maandag", "type": "herstelrun", "naam": "Herstelloop"},
        {"dag": "vrijdag", "type": "herstelrun", "naam": "Herstelloop"},
        {"dag": "zaterdag", "type": "aeroob_z2", "naam": "Z2 duurloop"},
    ]
    tagged = adherence.classify_priorities(week)
    by_dag = {s["dag"]: s["priority"] for s in tagged}
    # maandag komt eerst in de weekvolgorde -> verplicht (basisfrequentie)
    assert by_dag["maandag"] == "verplicht"
    assert by_dag["vrijdag"] == "optioneel"
    assert by_dag["zaterdag"] == "optioneel"


def test_first_easy_run_verplicht_regardless_of_input_order():
    # Zelfde week, maar sessies niet in dag-volgorde aangeleverd — classify
    # moet zelf op 'dag' sorteren, niet op input-volgorde.
    week = [
        {"dag": "zaterdag", "type": "aeroob_z2", "naam": "Z2 duurloop"},
        {"dag": "maandag", "type": "herstelrun", "naam": "Herstelloop"},
    ]
    tagged = adherence.classify_priorities(week)
    by_dag = {s["dag"]: s["priority"] for s in tagged}
    assert by_dag["maandag"] == "verplicht"
    assert by_dag["zaterdag"] == "optioneel"


def test_brick_is_always_optioneel():
    week = [{"dag": "dinsdag", "type": "recovery", "naam": "Brick", "is_brick": True}]
    tagged = adherence.classify_priorities(week)
    assert tagged[0]["priority"] == "optioneel"


def test_classify_priorities_does_not_mutate_input():
    week = [{"dag": "zondag", "type": "lange_duur", "naam": "Lange duurloop"}]
    adherence.classify_priorities(week)
    assert "priority" not in week[0]


# ── analyze() ────────────────────────────────────────────────────────────────

def _seed_week(week_start: date, required_done: int, required: int,
                optional_done: int = 0, optional: int = 0) -> None:
    history_db.record_weekly_summary(
        week_start,
        sessions_required=required,
        sessions_required_done=required_done,
        sessions_optional=optional,
        sessions_optional_done=optional_done,
    )


def test_analyze_no_data_is_onbekend():
    result = adherence.analyze(weeks=4)
    assert result["band"] == "onbekend"
    assert result["weeks_counted"] == 0


def test_analyze_within_band():
    # 4 weken, elk 4/5 verplicht (80%) -> binnen streefband
    for i in range(4):
        _seed_week(date(2026, 6, 1 + i * 7), required_done=4, required=5)
    result = adherence.analyze(weeks=4)
    assert result["band"] == "op_streef"
    assert result["required_pct"] == 80


def test_one_bad_week_does_not_tip_rolling_band():
    """Kernregel van de filosofie: één gemiste-sessies-week mag het
    4-weeks-oordeel niet laten kantelen als de rest goed zit."""
    good_weeks = [(5, 5), (5, 5), (5, 5)]  # 100%
    bad_week = (1, 5)  # 20% — één zware misser
    weeks = good_weeks + [bad_week]
    for i, (done, planned) in enumerate(weeks):
        _seed_week(date(2026, 6, 1 + i * 7), required_done=done, required=planned)
    result = adherence.analyze(weeks=4)
    # (5+5+5+1)/(5+5+5+5) = 80% -> nog net op streefband, geen alarm
    assert result["band"] != "onder_streef"
    assert "Geen paniek" not in result["message"] or result["band"] == "op_streef"


def test_sustained_low_adherence_is_onder_streef():
    for i in range(4):
        _seed_week(date(2026, 6, 1 + i * 7), required_done=2, required=5)  # 40%
    result = adherence.analyze(weeks=4)
    assert result["band"] == "onder_streef"
    assert "Geen paniek" in result["message"]


def test_missed_optional_never_flagged_as_risk():
    # Verplicht 100%, optioneel 0% -> mag nooit onder_streef triggeren puur
    # door gemiste optionele sessies (70/30-weging, verplicht domineert).
    for i in range(4):
        _seed_week(date(2026, 6, 1 + i * 7), required_done=5, required=5,
                    optional_done=0, optional=3)
    result = adherence.analyze(weeks=4)
    assert result["band"] != "onder_streef"
    assert result["optional_pct"] == 0
    assert result["required_pct"] == 100


def test_structurally_high_is_boven_streef_not_alarm():
    for i in range(4):
        _seed_week(date(2026, 6, 1 + i * 7), required_done=5, required=5,
                    optional_done=3, optional=3)
    result = adherence.analyze(weeks=4)
    assert result["band"] == "boven_streef"
    assert "Prima" in result["message"]


# ── record_week() ────────────────────────────────────────────────────────────

def test_record_week_splits_required_optional(monkeypatch):
    week_start = date(2026, 6, 1)  # maandag
    history_db.upsert_placement("101", date=week_start.isoformat(), priority="verplicht")
    history_db.upsert_placement("102", date=week_start.isoformat(), priority="optioneel")

    events = [
        {"id": "101", "category": "WORKOUT", "type": "Run",
         "start_date_local": "2026-06-01T07:00:00", "name": "Lange duurloop",
         "load_target": 80},
        {"id": "102", "category": "WORKOUT", "type": "Run",
         "start_date_local": "2026-06-02T07:00:00", "name": "Brick",
         "load_target": 40},
    ]
    activities = [
        {"id": "a1", "type": "Run", "start_date_local": "2026-06-01T07:05:00",
         "name": "Ochtendloop", "icu_training_load": 82},
        # geen activity op 2026-06-02 -> optionele sessie gemist
    ]

    import intervals_client
    monkeypatch.setattr(intervals_client, "get_events", lambda *a, **k: events)
    monkeypatch.setattr(intervals_client, "get_activities", lambda *a, **k: activities)

    result = adherence.record_week(week_start)
    assert result == {
        "sessions_required": 1, "sessions_required_done": 1,
        "sessions_optional": 1, "sessions_optional_done": 0,
    }

    summaries = history_db.get_weekly_summaries(weeks=1)
    assert summaries[0]["sessions_required"] == 1
    assert summaries[0]["sessions_optional_done"] == 0


def test_record_week_returns_none_without_placements():
    assert adherence.record_week(date(2026, 6, 1)) is None
