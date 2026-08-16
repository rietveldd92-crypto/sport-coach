"""Tests voor day_planner — availability-first dagtoewijzing.

Tier-structuur (zie day_planner.py docstring):
- Tier 1 (heilig): 2 longs same day, runs B2B (toggle), long-over-avail
- Tier 2 (warn + plaatst): hard spacing, long krap op avail
- Tier 3 (stil): longs adjacent, brick, min avail easy/hard
"""
from datetime import date

import pytest

from agents.day_planner import (
    DAYS_NL,
    SchedulingConflict,
    classify_intensity,
    plan_days,
    suggest_fix,
)


# ── Fixtures ────────────────────────────────────────────────────────────────

def _sessie(naam, duur, sport="Run", type_="z2_standard"):
    return {
        "naam": naam,
        "duur_min": duur,
        "sport": sport,
        "type": type_,
        "tss_geschat": duur,
        "beschrijving": "test",
    }


WEEK_START = date(2026, 4, 20)  # maandag


# ── classify_intensity ──────────────────────────────────────────────────────

def test_classify_long_by_duur():
    s = _sessie("Z2 lang", duur=120, type_="z2_standard")
    assert classify_intensity(s) == "long"


def test_classify_long_wins_over_hard():
    s = _sessie("Marathon tempo", duur=120, type_="marathon_tempo")
    assert classify_intensity(s) == "long"


def test_classify_hard_by_type():
    s = _sessie("Threshold", duur=60, type_="threshold")
    assert classify_intensity(s) == "hard"


def test_classify_hard_by_name():
    s = _sessie("VO2max 30/30", duur=55, type_="vo2max")
    assert classify_intensity(s) == "hard"


def test_classify_sweetspot_as_hard():
    s = _sessie("Sweetspot 4x10", duur=75, type_="sweetspot", sport="VirtualRide")
    assert classify_intensity(s) == "hard"


def test_classify_easy_default():
    s = _sessie("Herstelrun", duur=40, type_="recovery")
    assert classify_intensity(s) == "easy"


# ── R1: longs op hoogst-avail dagen ─────────────────────────────────────────

def test_long_placed_on_highest_avail_day():
    avail = {"maandag": 30, "dinsdag": 60, "woensdag": 60,
             "donderdag": 60, "vrijdag": 60, "zaterdag": 180, "zondag": 60}
    sessies = [_sessie("Long run 120", 120)]
    result, _ = plan_days(sessies, avail, WEEK_START)
    assert result[0]["dag"] == "zaterdag"


def test_two_longs_placed_on_top_two_avail_days():
    avail = {"maandag": 30, "dinsdag": 45, "woensdag": 60,
             "donderdag": 45, "vrijdag": 180, "zaterdag": 180, "zondag": 60}
    sessies = [_sessie("Long run", 120), _sessie("Long ride", 150, sport="VirtualRide",
                                                   type_="endurance_ride")]
    result, _ = plan_days(sessies, avail, WEEK_START)
    days = sorted(s["dag"] for s in result)
    assert days == ["vrijdag", "zaterdag"]


def test_long_raises_when_no_day_has_enough_avail():
    avail = {d: 60 for d in DAYS_NL}  # geen enkele dag ≥ 90
    sessies = [_sessie("Long run", 120)]
    with pytest.raises(SchedulingConflict):
        plan_days(sessies, avail, WEEK_START, strict=True)


def test_long_best_effort_lands_on_highest_avail_when_tight():
    avail = {d: 60 for d in DAYS_NL}
    sessies = [_sessie("Long run", 120)]
    result, warnings = plan_days(sessies, avail, WEEK_START)
    assert len(result) == 1
    assert result[0]["dag"] == "maandag"
    # Tier-2 warning: long past niet op 60min avail
    assert any(w["code"] == "long_over_avail" for w in warnings)


# ── R2: hards met spacing ───────────────────────────────────────────────────

def test_two_hards_not_adjacent():
    avail = {d: 90 for d in DAYS_NL}
    sessies = [_sessie("Threshold", 70, type_="threshold"),
               _sessie("VO2max", 60, type_="vo2max")]
    result, _ = plan_days(sessies, avail, WEEK_START)
    days = [s["dag"] for s in result]
    idx = sorted(DAYS_NL.index(d) for d in days)
    assert idx[1] - idx[0] >= 2  # minimaal 1 dag ertussen


def test_hard_not_adjacent_to_long():
    avail = {d: 90 for d in DAYS_NL}
    avail["zaterdag"] = 200
    sessies = [_sessie("Long run", 150),
               _sessie("Threshold", 60, type_="threshold")]
    result, _ = plan_days(sessies, avail, WEEK_START)
    long_dag = next(s["dag"] for s in result if classify_intensity(s) == "long")
    hard_dag = next(s["dag"] for s in result if classify_intensity(s) == "hard")
    assert long_dag == "zaterdag"
    assert hard_dag not in ("vrijdag", "zondag")


def test_hard_raises_when_cant_space():
    avail = {d: 0 for d in DAYS_NL}
    avail["vrijdag"] = 180
    avail["zaterdag"] = 180
    sessies = [_sessie("Long run", 120),
               _sessie("Threshold", 60, type_="threshold")]
    with pytest.raises(SchedulingConflict):
        plan_days(sessies, avail, WEEK_START, strict=True)


def test_hard_best_effort_places_with_warning_when_spacing_impossible():
    """Tier-2: geen spacing-dag → plaats toch + warning (niet droppen)."""
    avail = {d: 0 for d in DAYS_NL}
    avail["vrijdag"] = 180
    avail["zaterdag"] = 180
    sessies = [_sessie("Long run", 120),
               _sessie("Threshold", 60, type_="threshold")]
    result, warnings = plan_days(sessies, avail, WEEK_START)
    # Beide sessies zijn geplaatst (ipv hard te droppen)
    assert len(result) == 2
    # Warning voor de hard-spacing violation
    assert any(w["code"] == "hard_no_spacing" for w in warnings)


# ── R3: runs back-to-back (Tier 1 default, Tier 3 met toggle) ───────────────

def test_easy_runs_not_back_to_back_by_default():
    avail = {d: 60 for d in DAYS_NL}
    sessies = [_sessie("Z2 run", 45), _sessie("Herstelrun", 40, type_="recovery"),
               _sessie("Z2 run", 50)]
    result, _ = plan_days(sessies, avail, WEEK_START)
    run_dagen = sorted([s["dag"] for s in result if (s.get("sport") or "") == "Run"])
    indices = sorted(DAYS_NL.index(d) for d in run_dagen)
    for a, b in zip(indices, indices[1:]):
        assert b - a >= 2, f"Runs back-to-back: {run_dagen}"


def test_run_next_to_bike_is_fine():
    avail = {d: 60 for d in DAYS_NL}
    sessies = [_sessie("Easy spin", 45, sport="VirtualRide", type_="endurance_ride"),
               _sessie("Z2 run", 45)]
    result, _ = plan_days(sessies, avail, WEEK_START)
    assert len(result) == 2


def test_runs_back_to_back_ok_allows_adjacent_runs():
    """Met toggle aan mogen runs op opeenvolgende dagen (geen 2 runs same-day)."""
    avail = {d: 0 for d in DAYS_NL}
    avail["vrijdag"] = 60
    avail["zaterdag"] = 60  # alleen vr+za avail → zou normaal skip triggeren
    sessies = [_sessie("Z2 run 1", 45), _sessie("Z2 run 2", 45)]
    result, _ = plan_days(sessies, avail, WEEK_START, runs_back_to_back_ok=True)
    dagen = sorted(s["dag"] for s in result)
    assert dagen == ["vrijdag", "zaterdag"]  # beide geplaatst


def test_runs_back_to_back_off_skips_when_only_adjacent_days():
    """Toggle uit: runs worden geskipt ipv adjacent geplaatst."""
    avail = {d: 0 for d in DAYS_NL}
    avail["vrijdag"] = 60
    avail["zaterdag"] = 60
    sessies = [_sessie("Z2 run 1", 45), _sessie("Z2 run 2", 45)]
    result, _ = plan_days(sessies, avail, WEEK_START, runs_back_to_back_ok=False)
    assert len(result) == 1  # 2e run geskipt (T1b heilig)


def test_runs_back_to_back_ok_blocks_same_day_runs():
    """Ook met toggle aan: NOOIT 2 runs op dezelfde dag."""
    avail = {d: 0 for d in DAYS_NL}
    avail["zaterdag"] = 180
    sessies = [_sessie("Z2 run 1", 45), _sessie("Z2 run 2", 45)]
    result, _ = plan_days(sessies, avail, WEEK_START, runs_back_to_back_ok=True)
    # Beide op za zou 2 runs same-day zijn → 2e wordt geskipt
    za_runs = [s for s in result if s["dag"] == "zaterdag"]
    assert len(za_runs) == 1


# ── R4: longs adjacent toegestaan als moet ──────────────────────────────────

def test_longs_may_be_adjacent_when_forced():
    avail = {d: 0 for d in DAYS_NL}
    avail["vrijdag"] = 180
    avail["zaterdag"] = 180
    sessies = [_sessie("Long run", 120), _sessie("Long ride", 150, sport="VirtualRide",
                                                   type_="endurance_ride")]
    result, _ = plan_days(sessies, avail, WEEK_START)
    assert len(result) == 2
    assert {s["dag"] for s in result} == {"vrijdag", "zaterdag"}


def test_longs_adjacent_blocked_when_disallowed():
    avail = {d: 0 for d in DAYS_NL}
    avail["vrijdag"] = 180
    avail["zaterdag"] = 180
    sessies = [_sessie("Long run", 120), _sessie("Long ride", 150, sport="VirtualRide",
                                                   type_="endurance_ride")]
    with pytest.raises(SchedulingConflict):
        plan_days(sessies, avail, WEEK_START,
                  allow_adjacent_longs=False, strict=True)


# ── R5: brick op pre-occupied dag ───────────────────────────────────────────

def test_brick_lands_on_long_day_when_avail_permits():
    avail = {d: 60 for d in DAYS_NL}
    avail["vrijdag"] = 240
    sessies = [
        _sessie("Long run", 120),
        _sessie("Easy spin", 45, sport="VirtualRide", type_="endurance_ride"),
        _sessie("Z2 run", 45),
        _sessie("Herstelrun", 40, type_="recovery"),
    ]
    result, _ = plan_days(sessies, avail, WEEK_START)
    per_dag: dict[str, list] = {}
    for s in result:
        per_dag.setdefault(s["dag"], []).append(s)
    assert any(len(v) >= 2 for v in per_dag.values()), \
        f"Verwachtte brick-dag, kreeg {per_dag}"


# ── Avail tolerance ─────────────────────────────────────────────────────────

def test_avail_tolerance_accepts_minor_overrun():
    avail = {d: 0 for d in DAYS_NL}
    avail["dinsdag"] = 60
    sessies = [_sessie("Threshold 65", 65, type_="threshold")]
    result, _ = plan_days(sessies, avail, WEEK_START)
    assert result[0]["dag"] == "dinsdag"


def test_avail_tolerance_rejects_large_overrun():
    avail = {d: 0 for d in DAYS_NL}
    avail["dinsdag"] = 60
    sessies = [_sessie("Threshold 90", 90, type_="threshold")]
    with pytest.raises(SchedulingConflict):
        plan_days(sessies, avail, WEEK_START, strict=True)


# ── suggest_fix ─────────────────────────────────────────────────────────────

def test_suggest_fix_on_long_conflict():
    avail = {d: 60 for d in DAYS_NL}
    sessies = [_sessie("Long run", 120)]
    with pytest.raises(SchedulingConflict) as exc_info:
        plan_days(sessies, avail, WEEK_START, strict=True)
    # suggestion is gezet door plan_days
    assert exc_info.value.suggestion
    assert "≥90" in exc_info.value.suggestion or "≥ 90" in exc_info.value.suggestion \
        or "lange" in exc_info.value.suggestion.lower()


def test_suggest_fix_standalone():
    avail = {d: 0 for d in DAYS_NL}
    avail["vrijdag"] = 60
    conflict = SchedulingConflict(
        reason="test", unplaced=[_sessie("Long run", 120)], partial=[]
    )
    suggestion = suggest_fix(conflict, avail)
    assert suggestion
    assert "maandag" in suggestion.lower() or "zaterdag" in suggestion.lower() \
        or "lange" in suggestion.lower()


# ── Echte week-scenario ─────────────────────────────────────────────────────

def test_real_week_scenario():
    """Week 2026-04-20: ma/wo/zo 90min, di/do 60min, vr/za 240min."""
    avail = {
        "maandag": 90, "dinsdag": 60, "woensdag": 90, "donderdag": 60,
        "vrijdag": 240, "zaterdag": 240, "zondag": 90,
    }
    sessies = [
        _sessie("Long run 120", 120),
        _sessie("Long ride 150", 150, sport="VirtualRide", type_="endurance_ride"),
        _sessie("Threshold 60", 60, type_="threshold"),
        _sessie("VO2max 45", 45, type_="vo2max", sport="VirtualRide"),
        _sessie("Z2 run 45", 45),
        _sessie("Herstel 40", 40, type_="recovery"),
    ]
    result, _ = plan_days(sessies, avail, WEEK_START)

    per_dag: dict[str, list] = {}
    for s in result:
        per_dag.setdefault(s["dag"], []).append(s)

    long_dagen = {s["dag"] for s in result if classify_intensity(s) == "long"}
    assert long_dagen == {"vrijdag", "zaterdag"}

    hard_dagen = sorted(s["dag"] for s in result if classify_intensity(s) == "hard")
    hard_idx = sorted(DAYS_NL.index(d) for d in hard_dagen)
    assert hard_idx[1] - hard_idx[0] >= 2
    assert "donderdag" not in hard_dagen

    run_indices = sorted({DAYS_NL.index(s["dag"]) for s in result
                           if (s.get("sport") or "") == "Run"})
    for a, b in zip(run_indices, run_indices[1:]):
        assert b - a >= 2, f"Runs back-to-back: {run_indices}"



# ── fill_empty_days_with_easy_bikes variety ─────────────────────────────────

def test_fill_empty_days_rotates_variants():
    """Meerdere lege dagen in dezelfde week krijgen verschillende workouts
    (anders is ma=vr een duplicate zoals de user zag: 2x Duurrit rolling Z2 75min)."""
    from agents.day_planner import fill_empty_days_with_easy_bikes
    week_start = date(2026, 4, 27)
    # Alle dagen leeg, ~75min avail overal
    avail = {d: 75 for d in DAYS_NL}
    result = fill_empty_days_with_easy_bikes([], avail, week_start, max_fills=3)
    # Er zijn tenminste 2 fills geplaatst
    assert len(result) >= 2
    # Niet alle namen hetzelfde
    namen = {r.get("naam") for r in result}
    assert len(namen) >= 2, f"Alle fillers identiek: {namen}"


def test_fill_empty_days_all_flagged_is_fill():
    from agents.day_planner import fill_empty_days_with_easy_bikes
    week_start = date(2026, 4, 27)
    avail = {d: 60 for d in DAYS_NL}
    result = fill_empty_days_with_easy_bikes([], avail, week_start)
    for r in result:
        assert r.get("is_fill") is True

