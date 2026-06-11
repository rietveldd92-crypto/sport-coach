"""Snapshot-test (Fase 2, harde gate — UPGRADE_PLAN §8/§9).

De parametrische generator moet het huidige hardcoded Amsterdam-marathonplan
±10% reproduceren. De referentietabellen hieronder zijn een letterlijke kopie
van de (inmiddels verwijderde) tabellen uit agents/marathon_periodizer.py:
RUN_PROGRESSION_TABLE, WEEKLY_TSS_TABLE en de PHASES-weekranges.

Pas als deze test groen is mochten de tabellen uit marathon_periodizer weg —
deze fixtures zijn vanaf dat moment de regressiegarantie.
"""
from __future__ import annotations

from datetime import date

import pytest

from core.goal_engine import Goal
from core.periodization_generator import AthleteProfile, generate_plan

# ── FIXTURES: kopie van de oude hardcoded tabellen ────────────────────────

PLAN_START = date(2026, 4, 6)
RACE_DATE = date(2026, 10, 18)

# week: (run_km_totaal, run_sessies, lange_duurloop_km, is_recovery)
RUN_PROGRESSION_TABLE = {
    1:  (21, 3,  9, False),
    2:  (24, 3, 10, False),
    3:  (27, 3, 12, False),
    4:  (19, 3,  8, True),
    5:  (31, 3, 14, False),
    6:  (36, 3, 16, False),
    7:  (41, 3, 18, False),
    8:  (29, 3, 12, True),
    9:  (47, 4, 20, False),
    10: (54, 4, 22, False),
    11: (58, 4, 24, False),
    12: (40, 4, 16, True),
}

WEEKLY_TSS_TABLE = {
    1:  475,
    2:  510,
    3:  660,
    4:  290,
    5:  680,
    6:  720,
    7:  750,
    8:  340,
    9:  760,
    10: 800,
    11: 810,
    12: 530,
}

# fase → (eerste week, laatste week) uit de oude PHASES-definitie
PHASE_WEEK_RANGES = {
    "accumulatie_I": (1, 7),
    "accumulatie_II": (8, 14),
    "transformatie_I": (15, 18),
    "accumulatie_III": (19, 22),
    "transformatie_II": (23, 26),
    "realisatie": (27, 28),
}


def _reference_phase(week: int) -> str:
    for name, (lo, hi) in PHASE_WEEK_RANGES.items():
        if lo <= week <= hi:
            return name
    return "realisatie"


# ── HET ECHTE DOEL + STARTSITUATIE (april 2026) ───────────────────────────

@pytest.fixture(scope="module")
def marathon_plan():
    goal = Goal(
        type="marathon", sport="run", event_date=RACE_DATE,
        target_value="2:59:00", priority="A",
    )
    athlete = AthleteProfile(
        current_ctl=45.0,
        recent_run_km_avg=21.0,   # fysio-baseline bij plan_start
        recent_run_sessions=3,
        ftp=290, hrmax=192, days_symptom_free=99,
    )
    return generate_plan(goal, athlete, PLAN_START)


TOLERANCE = 0.10


def _within(generated: float, reference: float) -> bool:
    return abs(generated - reference) <= TOLERANCE * reference


# ── SNAPSHOT-ASSERTS ──────────────────────────────────────────────────────

def test_plan_heeft_28_weken_en_juiste_data(marathon_plan):
    weeks = marathon_plan.weeks
    assert len(weeks) == 28
    assert weeks[0].week_start == PLAN_START
    # Racedag (zo 18 okt) valt in de laatste planweek
    assert weeks[-1].week_start <= RACE_DATE <= weeks[-1].week_start.replace(day=18)


def test_run_km_binnen_10_procent(marathon_plan):
    devs = {}
    for wk, (km_ref, _, _, _) in RUN_PROGRESSION_TABLE.items():
        gen = marathon_plan.weeks[wk - 1].run_km
        devs[wk] = (gen - km_ref) / km_ref
        assert _within(gen, km_ref), (
            f"wk {wk}: run_km {gen} vs referentie {km_ref} "
            f"({devs[wk]*100:+.1f}% > ±10%)"
        )
    print("max run_km afwijking: "
          f"{max(devs.values(), key=abs)*100:+.1f}%")


def test_run_sessies_exact(marathon_plan):
    # ±10% op 3–4 sessies betekent in de praktijk: exact gelijk.
    for wk, (_, sessies_ref, _, _) in RUN_PROGRESSION_TABLE.items():
        gen = marathon_plan.weeks[wk - 1].run_sessions
        assert gen == sessies_ref, f"wk {wk}: {gen} sessies vs {sessies_ref}"


def test_long_run_binnen_10_procent(marathon_plan):
    devs = {}
    for wk, (_, _, long_ref, _) in RUN_PROGRESSION_TABLE.items():
        gen = marathon_plan.weeks[wk - 1].long_run_km
        devs[wk] = (gen - long_ref) / long_ref
        assert _within(gen, long_ref), (
            f"wk {wk}: long {gen} vs referentie {long_ref} "
            f"({devs[wk]*100:+.1f}% > ±10%)"
        )
    print("max long_run afwijking: "
          f"{max(devs.values(), key=abs)*100:+.1f}%")


def test_deload_weken_identiek(marathon_plan):
    for wk, (_, _, _, deload_ref) in RUN_PROGRESSION_TABLE.items():
        gen = marathon_plan.weeks[wk - 1].is_deload
        assert gen == deload_ref, f"wk {wk}: is_deload {gen} vs {deload_ref}"


def test_weekly_tss_binnen_10_procent(marathon_plan):
    devs = {}
    for wk, tss_ref in WEEKLY_TSS_TABLE.items():
        gen = marathon_plan.weeks[wk - 1].tss_target
        devs[wk] = (gen - tss_ref) / tss_ref
        assert _within(gen, tss_ref), (
            f"wk {wk}: TSS {gen} vs referentie {tss_ref} "
            f"({devs[wk]*100:+.1f}% > ±10%)"
        )
    print("max TSS afwijking: "
          f"{max(devs.values(), key=abs)*100:+.1f}%")


def test_faseverdeling_zelfde_week_plusminus_1(marathon_plan):
    """Zelfde fase op zelfde weeknummer, met ±1 week tolerantie op de
    fasegrenzen (blokverdeling mag 1 week schuiven)."""
    for wk in range(1, 29):
        gen = marathon_plan.weeks[wk - 1].phase
        acceptabel = {
            _reference_phase(max(1, wk - 1)),
            _reference_phase(wk),
            _reference_phase(min(28, wk + 1)),
        }
        assert gen in acceptabel, (
            f"wk {wk}: fase {gen} niet in {sorted(acceptabel)}"
        )


def test_geen_haalbaarheids_warning_voor_marathon(marathon_plan):
    """Het echte doel hoort haalbaar te zijn vanaf de echte startsituatie."""
    assert not any("niet haalbaar" in w for w in marathon_plan.warnings), \
        marathon_plan.warnings


# ── COMPAT: plan_provider levert het oude contract ────────────────────────

def test_plan_provider_compat_contract():
    """De fallback (lege test-DB) moet het oude marathon_periodizer-contract
    leveren: zelfde keys, zelfde clamping, plausibele waarden."""
    from core import plan_provider

    phase = plan_provider.get_current_phase(today=date(2026, 6, 11))  # wk 10
    for key in ("fase_naam", "fase_label", "week_nummer", "week_in_fase",
                "run_sessies_per_week", "fiets_sessies_per_week",
                "intensiteit_run", "intensiteit_fiets", "ctl_doel",
                "tss_doel", "weeks_to_race"):
        assert key in phase, f"key {key} ontbreekt in get_current_phase()"
    assert phase["week_nummer"] == 10
    assert phase["fase_naam"] == "accumulatie_II"

    vol = plan_provider.calculate_weekly_run_volume(9)
    for key in ("run_km_totaal", "run_sessies", "korte_sessies",
                "km_per_korte_sessie", "lange_duurloop_km", "fiets_sessies",
                "run_intensiteit", "fiets_intensiteit", "run_tss",
                "fiets_tss", "totaal_tss"):
        assert key in vol, f"key {key} ontbreekt in calculate_weekly_run_volume()"
    assert vol["run_sessies"] == 4
    assert _within(vol["run_km_totaal"], 47)

    # Weeknummer-clamping zoals vroeger (1..n)
    assert plan_provider.get_week_number(date(2020, 1, 1)) == 1
    assert plan_provider.get_week_number(date(2030, 1, 1)) == 28


def test_marathon_periodizer_reexport():
    """agents.marathon_periodizer blijft als dunne re-export werken."""
    from agents import marathon_periodizer as mp

    assert mp.get_week_number(date(2026, 4, 6)) == 1
    phase = mp.get_current_phase(today=date(2026, 4, 6))
    assert phase["fase_naam"] == "accumulatie_I"
    vol = mp.calculate_weekly_run_volume(1)
    assert _within(vol["run_km_totaal"], 21)
    # Proxies voor de oude module-tabellen
    assert mp.WEEKLY_PLAN[0]["is_recovery"] is False
    assert mp.WEEKLY_PLAN[3]["is_recovery"] is True
    assert 1 in mp.WEEKLY_TSS_TABLE
    assert _within(mp.WEEKLY_TSS_TABLE[1], 475)
