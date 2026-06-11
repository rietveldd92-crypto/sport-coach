"""Tests voor core/periodization_generator.py + core/replan_goal.py.

Plausibiliteit van niet-marathon-profielen (10k, gran fondo), B-doel
mini-taper, persist-alleen-toekomst en de rolling re-periodisatie.
Het marathon-snapshot zelf leeft in tests/test_periodization_snapshot.py.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from core import goal_engine
from core.goal_engine import Goal
from core.periodization_generator import (
    AthleteProfile,
    build_athlete_profile,
    generate_plan,
    load_plan_weeks,
    persist_plan_weeks,
    split_phases,
)
from core.replan_goal import weekly_recalibration

PLAN_START = date(2026, 4, 6)


def _builds(weeks):
    """Buildweken: geen deload, geen realisatie/taper."""
    return [w for w in weeks if not w.is_deload and w.phase != "realisatie"]


def _assert_deload_cadans(weeks):
    """Deload elke 3–4 weken (taper-staart uitgezonderd)."""
    deload_idx = [i for i, w in enumerate(weeks) if w.is_deload]
    assert deload_idx, "plan zonder deloads"
    assert deload_idx[0] <= 3, "eerste deload pas na week 4"
    for a, b in zip(deload_idx, deload_idx[1:]):
        assert 3 <= b - a <= 4, f"deload-gat van {b - a} weken (idx {a}->{b})"


def _assert_consistency(weeks):
    """Geen buildweek schendt de groei-cap; long ≤ 35% (deze profielen)."""
    builds = _builds(weeks)
    for prev, cur in zip(builds, builds[1:]):
        if prev.run_km <= 0:
            continue
        cap = 1.20 if prev.run_km < 27 else 1.15
        assert cur.run_km / prev.run_km <= cap * 1.01, (
            f"groei {prev.run_km}→{cur.run_km} km schendt +{cap:.0%}-cap"
        )
    for w in weeks:
        if w.run_km > 0 and w.long_run_km > 0:
            assert w.long_run_km / w.run_km <= 0.35 + 1e-6, (
                f"{w.week_start}: long {w.long_run_km} > 35% van {w.run_km}"
            )


# ── 10K-PROFIEL ───────────────────────────────────────────────────────────

@pytest.fixture()
def tienk_plan():
    goal = Goal(type="10k", sport="run", event_date=PLAN_START + timedelta(weeks=13, days=6),
                target_value="0:42:00")
    athlete = AthleteProfile(current_ctl=50, recent_run_km_avg=25,
                             recent_run_sessions=3)
    return generate_plan(goal, athlete, PLAN_START)


def test_10k_plausibel_plan(tienk_plan):
    weeks = tienk_plan.weeks
    assert len(weeks) == 14
    assert weeks[0].run_km == 25.0          # start = werkelijk startvolume

    # Monotone volume-opbouw buiten deloads, tot de piekweek
    builds = _builds(weeks)
    peak = max(w.run_km for w in builds)
    seen_peak = False
    for prev, cur in zip(builds, builds[1:]):
        if prev.run_km == peak:
            seen_peak = True
        if not seen_peak:
            assert cur.run_km >= prev.run_km - 1e-6, (
                f"volume daalt vóór de piek: {prev.run_km} → {cur.run_km}"
            )
    assert peak <= 50.0                      # §4.1: 10k → ~45 km piek
    assert peak >= 35.0

    _assert_deload_cadans(weeks)
    _assert_consistency(weeks)

    # Taper aanwezig: realisatie-fase + laatste week duidelijk onder piek
    assert weeks[-1].phase == "realisatie"
    assert weeks[-1].run_km < 0.5 * peak
    assert weeks[-1].long_run_km == 0.0

    # Geen korte-horizon-warning bij 14 weken
    assert not any("Korte aanloop" in w for w in tienk_plan.warnings)


def test_10k_vierde_run_pas_na_drempel(tienk_plan):
    for w in tienk_plan.weeks:
        if w.run_sessions >= 4 and not w.is_deload and w.phase.startswith("accumulatie"):
            assert w.run_km > 35, "4e run geactiveerd op te laag volume"


# ── GRAN-FONDO-PROFIEL (TSS-gedreven) ─────────────────────────────────────

@pytest.fixture()
def fondo_plan():
    goal = Goal(type="gran_fondo", sport="ride",
                event_date=PLAN_START + timedelta(weeks=15, days=6))
    athlete = AthleteProfile(current_ctl=62, recent_run_km_avg=10,
                             recent_run_sessions=2)
    return generate_plan(goal, athlete, PLAN_START)


def test_gran_fondo_plausibel_plan(fondo_plan):
    weeks = fondo_plan.weeks
    assert len(weeks) == 16

    # TSS-gedreven: stijgende TSS binnen elk build-blok
    prev = None
    for w in weeks:
        if w.is_deload or w.phase == "realisatie":
            prev = None
            continue
        if prev is not None:
            assert w.tss_target >= prev - 1, (
                f"TSS daalt binnen build-blok: {prev} → {w.tss_target}"
            )
        prev = w.tss_target

    # Sport-mix omgekeerd: fiets primair
    for w in _builds(weeks):
        assert w.bike_sessions >= 3
    assert all(w.run_km <= 20 for w in weeks)   # run hooguit ondersteunend

    _assert_deload_cadans(weeks)
    _assert_consistency(weeks)

    # Taper: laatste week onder het piek-TSS
    peak_tss = max(w.tss_target for w in weeks)
    assert weeks[-1].phase == "realisatie"
    assert weeks[-1].tss_target < 0.7 * peak_tss

    # CTL-pad respecteert max ~5/maand: totale stijging begrensd
    months = len(weeks) / 4.33
    rise = max(fondo_plan.ctl_projection) - 62
    assert rise <= 5.0 * months + 1


# ── KORTE HORIZON ─────────────────────────────────────────────────────────

def test_korte_horizon_geeft_warning():
    goal = Goal(type="10k", sport="run",
                event_date=PLAN_START + timedelta(weeks=7, days=6))
    res = generate_plan(goal, AthleteProfile(recent_run_km_avg=25), PLAN_START)
    assert len(res.weeks) == 8
    assert any("Korte aanloop" in w for w in res.warnings)
    phases, warns = split_phases(8)
    assert any("Korte aanloop" in w for w in warns)
    assert [p for p, _ in phases] == ["accumulatie_I", "transformatie_I", "realisatie"]


# ── B-DOEL → MINI-TAPER ───────────────────────────────────────────────────

def test_b_doel_geeft_mini_taper():
    goal = Goal(type="marathon", sport="run", event_date=date(2026, 10, 18),
                target_value="2:59:00")
    athlete = AthleteProfile(current_ctl=45, recent_run_km_avg=21,
                             recent_run_sessions=3)
    b_race = Goal(type="10k", sport="run", priority="B",
                  event_date=date(2026, 6, 21))   # zondag van planweek 11

    zonder = generate_plan(goal, athlete, PLAN_START)
    met = generate_plan(goal, athlete, PLAN_START, intermediate_goals=[b_race])

    idx = (b_race.event_date - PLAN_START).days // 7
    week_met = met.weeks[idx]
    week_zonder = zonder.weeks[idx]

    # Mini-taper: ~-25% volume + TSS in de raceweek, blokstructuur intact
    assert week_met.run_km == pytest.approx(week_zonder.run_km * 0.75, abs=0.2)
    assert week_met.tss_target < week_zonder.tss_target
    assert week_met.long_run_km <= week_met.run_km * 0.30 + 1e-6
    assert week_met.phase == week_zonder.phase
    # Recovery-week erna: licht gereduceerd
    assert met.weeks[idx + 1].run_km < zonder.weeks[idx + 1].run_km
    # De rest van het plan blijft gelijk
    assert met.weeks[idx - 1].run_km == zonder.weeks[idx - 1].run_km
    assert met.weeks[idx + 2].run_km == zonder.weeks[idx + 2].run_km


# ── PERSIST: OVERSCHRIJFT ALLEEN TOEKOMST ─────────────────────────────────

def _seed_goal_with_plan() -> Goal:
    goal = goal_engine.create_goal(Goal(
        type="marathon", sport="run", event_date=date(2026, 10, 18),
        target_value="2:59:00"))
    res = generate_plan(goal, AthleteProfile(
        current_ctl=45, recent_run_km_avg=21, recent_run_sessions=3), PLAN_START)
    persist_plan_weeks(goal.id, res.weeks)
    return goal


def test_persist_from_week_laat_verleden_staan():
    goal = _seed_goal_with_plan()
    before = load_plan_weeks(goal.id)

    # Hergenereer met afwijkend profiel en persisteer vanaf week 5
    res2 = generate_plan(goal, AthleteProfile(
        current_ctl=55, recent_run_km_avg=30, recent_run_sessions=4), PLAN_START)
    from_week = PLAN_START + timedelta(weeks=4)
    persist_plan_weeks(goal.id, res2.weeks, from_week=from_week)

    after = load_plan_weeks(goal.id)
    assert len(after) == 28
    for old, new in zip(before[:4], after[:4]):
        assert new.run_km == old.run_km, "verleden is overschreven"
    assert after[4].run_km != before[4].run_km, "toekomst is niet vernieuwd"


# ── ROLLING RE-PERIODISATIE (§4.2) ────────────────────────────────────────

def test_recalibration_binnen_band_doet_niets():
    goal = _seed_goal_with_plan()
    before = load_plan_weeks(goal.id)
    wk10_monday = PLAN_START + timedelta(weeks=9)
    today = wk10_monday + timedelta(days=6)            # zondag van wk 10

    report = weekly_recalibration(
        today=today,
        actual_ctl=58.0,
        actual_run_km=before[9].run_km,                 # exact op schema
    )
    assert report["status"] == "within_band"
    assert report["regenerated_from"] is None
    after = load_plan_weeks(goal.id)
    assert [w.run_km for w in after] == [w.run_km for w in before]


def test_recalibration_buiten_band_regenereert_alleen_toekomst():
    goal = _seed_goal_with_plan()
    before = load_plan_weeks(goal.id)
    wk10_monday = PLAN_START + timedelta(weeks=9)
    today = wk10_monday + timedelta(days=6)

    report = weekly_recalibration(
        today=today,
        actual_ctl=50.0,
        actual_run_km=before[9].run_km * 0.5,           # -50%: ver buiten band
        recent_run_sessions=3,
    )
    assert report["status"] == "replanned"
    assert report["regenerated_from"] == (wk10_monday + timedelta(days=7)).isoformat()

    after = load_plan_weeks(goal.id)
    assert len(after) == 28
    # Verleden + huidige week onaangetast
    for old, new in zip(before[:10], after[:10]):
        assert new.run_km == old.run_km
        assert new.generated_at == old.generated_at
    # Toekomst hergenereerd vanaf de werkelijkheid (lager volume)
    assert after[10].run_km < before[10].run_km
    assert after[10].generated_at != before[10].generated_at


def test_recalibration_injury_yellow_drukt_intensiteit():
    goal = _seed_goal_with_plan()
    wk10_monday = PLAN_START + timedelta(weeks=9)
    today = wk10_monday + timedelta(days=6)
    before = load_plan_weeks(goal.id)

    report = weekly_recalibration(
        today=today,
        actual_ctl=58.0,
        actual_run_km=before[9].run_km,                 # binnen band
        injury_status="geel",
    )
    assert report["status"] == "injury_adjusted"
    after = load_plan_weeks(goal.id)
    toekomst = [w for w in after if w.week_start > wk10_monday]
    assert toekomst
    for w in toekomst:
        assert w.intensity_gate in ("geen", "strides"), (
            f"{w.week_start}: gate {w.intensity_gate} ondanks injury GEEL"
        )
    # Verleden behoudt zijn gating
    assert any(w.intensity_gate not in ("geen", "strides") for w in after[:10])


def test_recalibration_zonder_goal():
    report = weekly_recalibration(today=date(2026, 6, 11))
    assert report["status"] == "no_goal"


# ── ATLEETPROFIEL-BUILDER ─────────────────────────────────────────────────

def test_build_athlete_profile_uit_activities():
    activities = []
    base = date(2026, 5, 4)   # maandag
    for week in range(3):
        for d, km in ((1, 8), (3, 8), (6, 14)):
            activities.append({
                "type": "Run",
                "start_date_local": (base + timedelta(weeks=week, days=d)).isoformat(),
                "distance": km * 1000,
            })
    activities.append({"type": "VirtualRide", "icu_ftp": 305,
                       "start_date_local": base.isoformat(), "distance": 40000})

    profile = build_athlete_profile(
        activities=activities,
        state={"load": {"ctl_estimate": 52.5}, "injury": {"days_symptom_free": 30}},
    )
    assert profile.current_ctl == 52.5
    assert profile.recent_run_km_avg == 30.0
    assert profile.recent_run_sessions == 3
    assert profile.ftp == 305
    assert profile.days_symptom_free == 30
