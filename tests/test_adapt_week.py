"""Tests voor agents.adapt_week."""
from datetime import date

from agents.adapt_week import adapt_week
from agents.models import Deviation


TODAY = date(2026, 4, 15)  # woensdag
STATE = {"load": {"ctl_estimate": 49.0}}


def _ev(eid, name, tss, dt, etype="Run"):
    return {
        "id": eid,
        "name": name,
        "type": etype,
        "load_target": tss,
        "start_date_local": f"{dt}T09:00:00",
        "duration": 3600,
        "category": "WORKOUT",
    }


def test_no_deviations_clean_narrative():
    events = [_ev("e1", "Z2 easy", 40, "2026-04-15")]
    result = adapt_week(events, [], STATE, today=TODAY)
    assert result.modifications == []
    assert "binnen tolerantie" in result.narrative


def test_sacred_skipped_wordt_herpland():
    # Week met skipped sacred long run op maandag, rustdag op vrijdag
    long_run = _ev("e_long", "Lange duurloop 20km", 120, "2026-04-13")
    events = [
        long_run,
        _ev("e_wo", "Threshold 3x10", 80, "2026-04-15", etype="Ride"),
        _ev("e_do", "Z2 easy", 40, "2026-04-16"),
        # geen event op vrijdag/zaterdag/zondag — vrije slots
    ]
    dev = Deviation(
        type="skipped",
        planned_event_id="e_long",
        tss_planned=120,
        tss_actual=0,
        severity="high",
        planned_date="2026-04-13",
        sacred=True,
    )
    result = adapt_week(events, [dev], STATE, today=TODAY)
    # Er moet minstens 1 create modification zijn
    creates = [m for m in result.modifications if m.action == "create"]
    assert len(creates) >= 1
    assert len(result.new_events) >= 1


def test_soft_skipped_wordt_geabsorbeerd():
    events = [_ev("e1", "Z2 easy", 40, "2026-04-14")]
    dev = Deviation(
        type="skipped",
        planned_event_id="e1",
        tss_planned=40,
        tss_actual=0,
        severity="low",
        planned_date="2026-04-14",
        sacred=False,
    )
    result = adapt_week(events, [dev], STATE, today=TODAY)
    # Geen modifications — silent absorb
    assert all(m.action != "create" for m in result.modifications)
    assert "geabsorbeerd" in result.narrative.lower() or "soft" in result.narrative.lower()


def test_replaced_harder_downgrade_next_hard():
    events = [
        _ev("e_now", "Zware rit", 120, "2026-04-15", etype="Ride"),
        _ev("e_next", "Threshold 3x10", 90, "2026-04-16", etype="Ride"),
    ]
    dev = Deviation(
        type="replaced_harder",
        planned_event_id="e_now",
        tss_planned=60,
        tss_actual=120,
        severity="high",
    )
    result = adapt_week(events, [dev], STATE, today=TODAY)
    modifies = [m for m in result.modifications if m.action == "modify"]
    assert len(modifies) == 1
    assert modifies[0].event_id == "e_next"
    assert modifies[0].after["load_target"] < 90


def test_longer_cut_next_day():
    events = [
        _ev("e_today", "Duurloop", 60, "2026-04-15"),
        _ev("e_tomorrow", "Threshold rit", 90, "2026-04-16", etype="Ride"),
    ]
    dev = Deviation(
        type="longer",
        planned_event_id="e_today",
        planned_date="2026-04-15",
        tss_planned=60,
        tss_actual=62,
        severity="low",
    )
    result = adapt_week(events, [dev], STATE, today=TODAY)
    mods = [m for m in result.modifications if m.event_id == "e_tomorrow"]
    assert len(mods) == 1
    assert mods[0].after["load_target"] < 90


def test_extras_waarschuwing_boven_drempel():
    events = []
    devs = [
        Deviation(type="extra", actual_activity_id=f"a{i}", tss_actual=40)
        for i in range(4)
    ]
    result = adapt_week(events, devs, STATE, today=TODAY)
    assert "junk miles" in result.narrative.lower()


def test_alle_sacred_skipped_geen_slot():
    # Volledig volgeplande week — geen slots over
    # Elke dag een sacred sessie → geen rust/soft slots beschikbaar
    events = [
        _ev("e1", "Lange duurloop", 120, "2026-04-13"),
        _ev("e2", "Threshold", 80, "2026-04-14", etype="Ride"),
        _ev("e3", "Drempel intervals", 75, "2026-04-15"),
        _ev("e4", "Sweetspot 2x20", 85, "2026-04-16", etype="Ride"),
        _ev("e5", "Drempel 4x1km", 75, "2026-04-17"),
        _ev("e6", "Lange duurloop 18km", 120, "2026-04-18"),
        _ev("e7", "Marathon_tempo 10km", 90, "2026-04-19"),
    ]
    dev = Deviation(
        type="skipped",
        planned_event_id="e1",
        tss_planned=120,
        tss_actual=0,
        severity="high",
        planned_date="2026-04-13",
        sacred=True,
    )
    result = adapt_week(events, [dev], STATE, today=TODAY)
    # Kon niet herplannen — narrative moet dat aangeven
    assert "valt weg" in result.narrative or "geen plek" in result.narrative.lower()


def test_invariant_altijd_aanwezig():
    result = adapt_week([], [], STATE, today=TODAY)
    assert result.invariant
    assert "CTL" in result.invariant
