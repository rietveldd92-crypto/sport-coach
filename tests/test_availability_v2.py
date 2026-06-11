"""Tests voor core/availability_v2 — tijdvensters + compat-laag (Fase 1)."""
from datetime import date

import history_db
import shared
from core import availability_v2 as av2

MONDAY = date(2026, 6, 15)  # maandag
TUESDAY = date(2026, 6, 16)


# ── Overrides ───────────────────────────────────────────────────────────────

def test_set_override_en_lezen():
    av2.set_override(MONDAY, [("06:00", "07:30"), ("18:00", "19:00", "indoor_only")])
    slots, known = av2.day_slots(MONDAY)
    assert known
    assert [(s.start, s.end, s.context) for s in slots] == [
        ("06:00", "07:30", "any"),
        ("18:00", "19:00", "indoor_only"),
    ]
    assert av2.minutes_for_day(MONDAY) == 150


def test_rustdag_marker():
    av2.set_override(MONDAY, [])
    slots, known = av2.day_slots(MONDAY)
    assert known
    assert slots == []
    assert av2.minutes_for_day(MONDAY) == 0


def test_onbekende_dag_is_none():
    assert av2.minutes_for_day(MONDAY) is None
    slots, known = av2.day_slots(MONDAY)
    assert slots == [] and not known


def test_clear_override():
    av2.set_override(MONDAY, [("07:00", "08:00")])
    av2.clear_override(MONDAY)
    assert av2.minutes_for_day(MONDAY) is None


# ── Patroon ─────────────────────────────────────────────────────────────────

def test_pattern_fallback_wanneer_geen_override():
    av2.set_pattern(0, [("06:30", "08:00")])  # alle maandagen
    slots, known = av2.day_slots(MONDAY)
    assert known
    assert [(s.start, s.end) for s in slots] == [("06:30", "08:00")]
    # dinsdag heeft geen patroon → onbekend
    assert av2.minutes_for_day(TUESDAY) is None


def test_override_wint_van_pattern():
    av2.set_pattern(0, [("06:30", "08:00")])
    av2.set_override(MONDAY, [("12:00", "13:00")])
    slots, _ = av2.day_slots(MONDAY)
    assert [(s.start, s.end) for s in slots] == [("12:00", "13:00")]


def test_pattern_rustdag():
    av2.set_pattern(0, [])  # expliciete rustdag in patroon
    assert av2.minutes_for_day(MONDAY) == 0


def test_get_slots_for_week_combineert_bronnen():
    av2.set_pattern(0, [("06:00", "07:00")])
    av2.set_override(TUESDAY, [("18:00", "20:00")])
    week = av2.get_slots_for_week(MONDAY)
    assert len(week) == 7
    assert week[MONDAY][0].start == "06:00"
    assert week[TUESDAY][0].start == "18:00"
    assert week[date(2026, 6, 17)] == []  # niets ingesteld


# ── Legacy fallback (state.json minuten-dict) ──────────────────────────────

def test_legacy_minuten_fallback(tmp_path, monkeypatch):
    state_json = tmp_path / "state.json"
    state_json.write_text(
        '{"availability": {"%s": 90, "%s": 0}}' % (MONDAY, TUESDAY),
        encoding="utf-8",
    )
    monkeypatch.setattr(shared, "STATE_PATH", state_json)
    assert history_db.athlete_state_is_empty()

    slots, known = av2.day_slots(MONDAY)
    assert known
    assert [(s.start, s.end) for s in slots] == [("07:00", "08:30")]
    assert av2.minutes_for_day(TUESDAY) == 0  # expliciete rustdag


# ── Compat-laag agents/availability ─────────────────────────────────────────

def test_compat_get_week_afgeleid_van_slots():
    from agents import availability

    av2.set_override(MONDAY, [("06:00", "07:00"), ("18:00", "18:30")])
    week = availability.get_week(MONDAY)
    assert week[MONDAY.isoformat()] == 90
    assert week[TUESDAY.isoformat()] is None


def test_compat_set_week_schrijft_overrides():
    from agents import availability

    availability.set_week(MONDAY, {MONDAY.isoformat(): 120,
                                   TUESDAY.isoformat(): 0})
    assert av2.minutes_for_day(MONDAY) == 120
    assert av2.minutes_for_day(TUESDAY) == 0
    slots, _ = av2.day_slots(MONDAY)
    assert [(s.start, s.end) for s in slots] == [("07:00", "09:00")]


def test_set_week_behoudt_rijke_vensters_bij_ongewijzigd_totaal():
    """No-op save mag multi-slot detail niet platslaan naar één venster."""
    from agents import availability

    av2.set_override(MONDAY, [("06:00", "07:00"), ("18:00", "19:00")])
    availability.set_week(MONDAY, {MONDAY.isoformat(): 120})  # zelfde totaal
    slots, _ = av2.day_slots(MONDAY)
    assert len(slots) == 2  # detail behouden
    availability.set_week(MONDAY, {MONDAY.isoformat(): 60})  # echt gewijzigd
    slots, _ = av2.day_slots(MONDAY)
    assert [(s.start, s.end) for s in slots] == [("07:00", "08:00")]


def test_save_state_roundtrip_behoudt_vensters():
    """shared.save_state (whole-overwrite) laat ongewijzigde datums met
    rijke vensters intact."""
    shared.save_state({"x": 1, "availability": {}})
    av2.set_override(MONDAY, [("06:00", "07:30"), ("18:00", "19:00")])
    state = shared.load_state()
    assert state["availability"][MONDAY.isoformat()] == 150
    shared.save_state(state)  # roundtrip zonder wijziging
    slots, _ = av2.day_slots(MONDAY)
    assert len(slots) == 2


# ── Placements API (history_db) ─────────────────────────────────────────────

def test_placements_upsert_en_lock():
    history_db.upsert_placement(
        "ev1", date="2026-06-15", slot_start="07:00",
        session_kind="long", solver_score=30.0, solver_notes="test",
    )
    rec = history_db.get_placement("ev1")
    assert rec["session_kind"] == "long"
    assert rec["locked"] == 0

    history_db.set_placement_locked("ev1", True)
    # Een latere solver-update mag de lock niet wissen
    history_db.upsert_placement("ev1", date="2026-06-16", slot_start="08:00",
                                session_kind="long")
    rec = history_db.get_placement("ev1")
    assert rec["locked"] == 1
    assert rec["date"] == "2026-06-16"

    rows = history_db.get_placements("2026-06-15", "2026-06-21")
    assert len(rows) == 1
    history_db.delete_placement("ev1")
    assert history_db.get_placement("ev1") is None
