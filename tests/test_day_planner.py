"""Tests voor day_planner — availability-first dagtoewijzing.

Regels die getest worden:
R1. Longs (>100 min) op dagen met meeste avail
R2. Hards met ≥1 dag afstand van andere hard + long
R3. Easy runs niet back-to-back
R4. Longs bij voorkeur niet adjacent (toegestaan als moet)
R5. Brick op dagen die al iets hebben
"""
from datetime import date

import pytest

from agents.day_planner import (
    DAYS_NL,
    SchedulingConflict,
    classify_intensity,
    plan_days,
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
    # 120 min marathon-tempo → long, niet hard
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
    result = plan_days(sessies, avail, WEEK_START)
    assert result[0]["dag"] == "zaterdag"


def test_two_longs_placed_on_top_two_avail_days():
    avail = {"maandag": 30, "dinsdag": 45, "woensdag": 60,
             "donderdag": 45, "vrijdag": 180, "zaterdag": 180, "zondag": 60}
    sessies = [_sessie("Long run", 120), _sessie("Long ride", 150, sport="VirtualRide",
                                                   type_="endurance_ride")]
    result = plan_days(sessies, avail, WEEK_START)
    days = sorted(s["dag"] for s in result)
    # beide op de twee hoogste dagen (vr/za)
    assert days == ["vrijdag", "zaterdag"]


def test_long_raises_when_no_day_has_enough_avail():
    avail = {d: 60 for d in DAYS_NL}  # geen enkele dag ≥ 90
    sessies = [_sessie("Long run", 120)]
    with pytest.raises(SchedulingConflict):
        plan_days(sessies, avail, WEEK_START, strict=True)


def test_long_best_effort_lands_on_highest_avail_when_tight():
    # Default (strict=False): long landt op hoogste avail dag, caller capt later.
    avail = {d: 60 for d in DAYS_NL}
    sessies = [_sessie("Long run", 120)]
    result = plan_days(sessies, avail, WEEK_START)
    assert len(result) == 1
    assert result[0]["dag"] == "maandag"  # alle dagen gelijk → DAYS_NL order


# ── R2: hards met spacing ───────────────────────────────────────────────────

def test_two_hards_not_adjacent():
    avail = {d: 90 for d in DAYS_NL}
    sessies = [_sessie("Threshold", 70, type_="threshold"),
               _sessie("VO2max", 60, type_="vo2max")]
    result = plan_days(sessies, avail, WEEK_START)
    days = [s["dag"] for s in result]
    idx = sorted(DAYS_NL.index(d) for d in days)
    assert idx[1] - idx[0] >= 2  # minimaal 1 dag ertussen


def test_hard_not_adjacent_to_long():
    # Long op zaterdag, hard mag niet op vrij of zo
    avail = {d: 90 for d in DAYS_NL}
    avail["zaterdag"] = 200
    sessies = [_sessie("Long run", 150),
               _sessie("Threshold", 60, type_="threshold")]
    result = plan_days(sessies, avail, WEEK_START)
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


# ── R3: geen back-to-back runs ──────────────────────────────────────────────

def test_easy_runs_not_back_to_back():
    avail = {d: 60 for d in DAYS_NL}
    sessies = [_sessie("Z2 run", 45), _sessie("Herstelrun", 40, type_="recovery"),
               _sessie("Z2 run", 50)]
    result = plan_days(sessies, avail, WEEK_START)
    run_dagen = sorted([s["dag"] for s in result if (s.get("sport") or "") == "Run"])
    indices = sorted(DAYS_NL.index(d) for d in run_dagen)
    for a, b in zip(indices, indices[1:]):
        assert b - a >= 2, f"Runs back-to-back: {run_dagen}"


def test_run_next_to_bike_is_fine():
    # Brick logica: run op een dag met bike (of omgekeerd) is OK
    avail = {d: 60 for d in DAYS_NL}
    sessies = [_sessie("Easy spin", 45, sport="VirtualRide", type_="endurance_ride"),
               _sessie("Z2 run", 45)]
    result = plan_days(sessies, avail, WEEK_START)
    assert len(result) == 2  # geen conflict


# ── R4: longs adjacent toegestaan als moet ──────────────────────────────────

def test_longs_may_be_adjacent_when_forced():
    # Alleen 2 hoge-avail dagen en ze zijn adjacent (vr/za)
    avail = {d: 0 for d in DAYS_NL}
    avail["vrijdag"] = 180
    avail["zaterdag"] = 180
    sessies = [_sessie("Long run", 120), _sessie("Long ride", 150, sport="VirtualRide",
                                                   type_="endurance_ride")]
    result = plan_days(sessies, avail, WEEK_START)  # allow_adjacent_longs=True
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
    # Vrijdag heeft veel avail, long landt daar; daarna moet een easy-bike
    # ook op vrijdag kunnen (brick) want er is nog ruimte + andere dagen krap.
    avail = {d: 60 for d in DAYS_NL}
    avail["vrijdag"] = 240
    sessies = [
        _sessie("Long run", 120),
        _sessie("Easy spin", 45, sport="VirtualRide", type_="endurance_ride"),
        _sessie("Z2 run", 45),
        _sessie("Herstelrun", 40, type_="recovery"),
    ]
    result = plan_days(sessies, avail, WEEK_START)
    # Ergens een dag met 2 sessies (brick)
    per_dag: dict[str, list] = {}
    for s in result:
        per_dag.setdefault(s["dag"], []).append(s)
    assert any(len(v) >= 2 for v in per_dag.values()), \
        f"Verwachtte brick-dag, kreeg {per_dag}"


# ── Avail tolerance (65 min op 60 min avail is OK) ──────────────────────────

def test_avail_tolerance_accepts_minor_overrun():
    avail = {d: 0 for d in DAYS_NL}
    avail["dinsdag"] = 60
    sessies = [_sessie("Threshold 65", 65, type_="threshold")]
    result = plan_days(sessies, avail, WEEK_START)
    assert result[0]["dag"] == "dinsdag"


def test_avail_tolerance_rejects_large_overrun():
    avail = {d: 0 for d in DAYS_NL}
    avail["dinsdag"] = 60
    sessies = [_sessie("Threshold 90", 90, type_="threshold")]
    with pytest.raises(SchedulingConflict):
        plan_days(sessies, avail, WEEK_START, strict=True)


# ── Echte week-scenario (2026-04-20 van gebruiker) ──────────────────────────

def test_real_week_scenario():
    """Week 2026-04-20: ma/wo/zo 90min, di/do 60min, vr/za 240min.

    Realistische workload: 2 longs + 2 hards + 2 easy runs.
    Verwachting: longs op vr/za (hoogste avail), hards met spacing,
    runs niet back-to-back. Brick op wo (hard bike + easy run).
    """
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
    result = plan_days(sessies, avail, WEEK_START)

    per_dag: dict[str, list] = {}
    for s in result:
        per_dag.setdefault(s["dag"], []).append(s)

    # R1: longs op de 2 hoogst-avail dagen (vr+za)
    long_dagen = {s["dag"] for s in result if classify_intensity(s) == "long"}
    assert long_dagen == {"vrijdag", "zaterdag"}

    # R2: hards ≥1 dag uit elkaar + niet adjacent aan long
    hard_dagen = sorted(s["dag"] for s in result if classify_intensity(s) == "hard")
    hard_idx = sorted(DAYS_NL.index(d) for d in hard_dagen)
    assert hard_idx[1] - hard_idx[0] >= 2
    # Hard niet op do (adjacent aan vr-long) of op zo (adj za-long)
    assert "donderdag" not in hard_dagen
    # Hard mag wel op ma/di/wo — alle vinkjes

    # R3: geen back-to-back runs
    run_indices = sorted({DAYS_NL.index(s["dag"]) for s in result
                           if (s.get("sport") or "") == "Run"})
    for a, b in zip(run_indices, run_indices[1:]):
        assert b - a >= 2, f"Runs back-to-back: {run_indices}"
