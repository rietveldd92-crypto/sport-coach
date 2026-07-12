"""Plan-provider — compatibiliteitslaag over de ``plan_weeks``-tabel (Fase 2).

Biedt dezelfde functiesignaturen als het oude ``agents/marathon_periodizer``
(get_current_phase, calculate_weekly_run_volume, get_week_number, ...) maar
leest uit het macroplan van het actieve A-doel in SQLite.

Fallback: zolang er geen actief doel met plan_weeks in de DB staat, wordt
het standaard Amsterdam-marathonplan in-memory gegenereerd (deterministisch,
zelfde parameters als scripts/seed_goal.py) zodat alle bestaande consumers
blijven werken — ook in tests met een lege DB.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from core.goal_engine import Goal
from core.periodization_generator import (
    AthleteProfile,
    PlanWeek,
    generate_plan,
    load_plan_weeks,
)

# Standaarddoel (Amsterdam Marathon 2026) — gebruikt als DB-fallback.
RACE_DATE = date(2026, 10, 18)
PLAN_START = date(2026, 4, 6)
DEFAULT_GOAL = Goal(
    id=0, type="marathon", sport="run", event_date=RACE_DATE,
    target_value="2:59:00", priority="A", status="active",
)
DEFAULT_PROFILE = AthleteProfile(
    current_ctl=45.0, recent_run_km_avg=21.0, recent_run_sessions=3,
    ftp=290, hrmax=192, days_symptom_free=99,
)

_FALLBACK_CACHE: Optional[list[PlanWeek]] = None

PHASE_LABELS = {
    "accumulatie_I": "Accumulatie I — Herstel & Basis",
    "accumulatie_II": "Accumulatie II — Volume",
    "transformatie_I": "Transformatie I — Scherpte",
    "accumulatie_III": "Accumulatie III — Piekvolume",
    "transformatie_II": "Transformatie II — Race-specifiek",
    "realisatie": "Realisatie — Taper & Race",
}

PHASE_DESCRIPTIONS = {
    "accumulatie_I": "Aerobe basis opbouwen. Volume eerst, intensiteit volgt.",
    "accumulatie_II": "Volume verder uitbouwen; tempoduur als sleutelsessie.",
    "transformatie_I": "Drempelwerk en scherpte; 90/10-verdeling.",
    "accumulatie_III": "Terug naar Z1-dominantie op piekvolume.",
    "transformatie_II": "Race-specifieke kwaliteit vanuit algemene fitheid.",
    "realisatie": "Taper: volumereductie met behoud van prikkels.",
}

_PHASE_BIKE_TOOLKIT = {
    "acc": ["threshold", "fatmax_medium", "fatmax_lang", "cp_intervals", "long_slow"],
    "trans": ["threshold", "cp_intervals", "fatmax_medium"],
    "real": [],
}


def _block_type(phase: str) -> str:
    if phase.startswith("accumulatie"):
        return "acc"
    if phase.startswith("transformatie"):
        return "trans"
    return "real"


# ── PLAN-RESOLUTIE ────────────────────────────────────────────────────────

def _fallback_plan() -> list[PlanWeek]:
    """Deterministisch in-memory standaardplan (geen DB nodig)."""
    global _FALLBACK_CACHE
    if _FALLBACK_CACHE is None:
        result = generate_plan(DEFAULT_GOAL, DEFAULT_PROFILE, PLAN_START)
        _FALLBACK_CACHE = result.weeks
    return _FALLBACK_CACHE


def get_active_plan() -> tuple[Goal, list[PlanWeek]]:
    """(goal, plan_weeks) van het actieve A-doel; anders de fallback."""
    try:
        from core import goal_engine
        goal = goal_engine.get_active_goal()
        if goal is not None and goal.id is not None:
            weeks = load_plan_weeks(goal.id)
            if weeks:
                return goal, weeks
    except Exception:
        pass
    return DEFAULT_GOAL, _fallback_plan()


# ── LEGACY-MAPPING ────────────────────────────────────────────────────────

def _legacy_run_intensity(phase: str, gate: str) -> str:
    """Map (fase, intensity_gate) → het run_intensiteit-vocabulaire dat
    endurance_coach verwacht (zie _plan_marathon_sessions)."""
    if phase.startswith("realisatie"):
        return "lichte_strides"
    if gate == "race_specifiek":
        return "marathon_tempo"
    if gate == "drempel":
        # Gate drempel = drempel, ook in transformatie. Historisch mapten we
        # transformatie naar marathon_tempo, maar dan bevat het plan na wk 14
        # géén LT-werk meer — terwijl de doelen (10K 5 sep, marathon 18 okt)
        # juist een hogere drempel + meer tijd-op-drempel vragen. MP-werk
        # blijft bestaan via transformatie_II (gate race_specifiek, sep).
        return "drempel"
    if gate == "tempoduur":
        return "tempoduur_strides" if phase == "accumulatie_III" else "tempoduur"
    return gate  # geen | strides


def _legacy_week_dict(week: PlanWeek, week_number: int) -> dict:
    """PlanWeek → het dict-formaat van het oude WEEKLY_PLAN."""
    run_tss = round(week.run_km * 5.5)
    total_tss = week.tss_target
    fiets_tss = max(0, total_tss - run_tss)
    medium = 1 if week.run_sessions >= 5 else 0
    korte = max(0, week.run_sessions - medium - (1 if week.long_run_km > 0 else 0))
    block = _block_type(week.phase)
    return {
        "week": week_number,
        "monday": week.week_start.isoformat(),
        "fase": week.phase,
        "fase_label": PHASE_LABELS.get(week.phase, week.phase.replace("_", " ").title()),
        "run_km_totaal": week.run_km,
        "run_sessies": week.run_sessions,
        "korte_sessies": korte,
        "medium_sessies": medium,
        "lange_duurloop_km": week.long_run_km,
        "fiets_sessies": week.bike_sessions,
        "run_tss": run_tss,
        "fiets_tss": fiets_tss,
        "totaal_tss": total_tss,
        "run_intensiteit": _legacy_run_intensity(week.phase, week.intensity_gate),
        "fiets_intensiteit": "toolkit" if week.bike_sessions > 0 else "geen",
        "bike_slot2": "",
        "intensity_gate": week.intensity_gate,
        "is_recovery": week.is_deload,
        "tss_target_min": week.tss_target_min,
        "tss_target_max": week.tss_target_max,
    }


# ── PUBLIEKE API (zelfde signaturen als marathon_periodizer) ──────────────

def get_weekly_plan() -> list[dict]:
    """Volledig plan als legacy WEEKLY_PLAN-lijst (1 dict per week)."""
    _, weeks = get_active_plan()
    return [_legacy_week_dict(w, i + 1) for i, w in enumerate(weeks)]


def get_weekly_tss_table() -> dict[int, int]:
    """Legacy WEEKLY_TSS_TABLE: weeknummer → TSS-doel (bandmidden)."""
    _, weeks = get_active_plan()
    return {i + 1: w.tss_target for i, w in enumerate(weeks)}


def get_week_number(today: Optional[date] = None) -> int:
    """Weeknummer (1..n) binnen het actieve macroplan."""
    if today is None:
        today = date.today()
    _, weeks = get_active_plan()
    if not weeks:
        return 1
    days = (today - weeks[0].week_start).days
    week = days // 7 + 1
    return max(1, min(len(weeks), week))


def get_current_phase(today: Optional[date] = None) -> dict:
    """Huidige fase + context — zelfde dict-shape als het oude
    marathon_periodizer.get_current_phase()."""
    if today is None:
        today = date.today()
    goal, weeks = get_active_plan()
    wk = get_week_number(today)
    week = weeks[wk - 1]
    phase = week.phase
    block = _block_type(phase)

    phase_weeks = [w for w in weeks if w.phase == phase]
    first_idx = next(i for i, w in enumerate(weeks) if w.phase == phase)
    tss_doel = (
        min(w.tss_target_min for w in phase_weeks),
        max(w.tss_target_max for w in phase_weeks),
    )

    try:
        from agents.load_manager import PHASE_CTL_TARGETS
        ctl_doel = PHASE_CTL_TARGETS.get(phase, (50, 65))
    except ImportError:                                    # pragma: no cover
        ctl_doel = (50, 65)

    legacy = _legacy_week_dict(week, wk)
    return {
        "fase_naam": phase,
        "fase_label": legacy["fase_label"],
        "week_nummer": wk,
        "week_in_fase": wk - first_idx,
        "beschrijving": PHASE_DESCRIPTIONS.get(phase, ""),
        "run_sessies_per_week": week.run_sessions,
        "fiets_sessies_per_week": week.bike_sessions,
        "lange_duurloop": week.long_run_km > 0,
        "intensiteit_run": legacy["run_intensiteit"],
        "intensiteit_fiets": legacy["fiets_intensiteit"],
        "run_intensiteit_gating": legacy["run_intensiteit"],
        "intensity_gate": week.intensity_gate,
        "bike_toolkit": _PHASE_BIKE_TOOLKIT[block],
        "ctl_doel": ctl_doel,
        "tss_doel": tss_doel,
        "weeks_to_race": max(0, (goal.event_date - today).days // 7),
    }


def calculate_weekly_run_volume(week_number: int) -> dict:
    """Loopvolume voor een specifieke week — zelfde dict-shape als het
    oude marathon_periodizer.calculate_weekly_run_volume()."""
    _, weeks = get_active_plan()
    week_number = max(1, min(len(weeks), week_number))
    legacy = _legacy_week_dict(weeks[week_number - 1], week_number)

    total_km = legacy["run_km_totaal"]
    long_km = legacy["lange_duurloop_km"]
    korte = legacy["korte_sessies"]
    medium = legacy["medium_sessies"]

    km_per_korte = km_per_medium = 0.0
    if korte + medium > 0:
        rest_km = max(0.0, total_km - long_km)
        if medium > 0 and korte > 0:
            medium_km = rest_km * 0.35
            km_per_korte = round((rest_km - medium_km) / korte, 1)
            km_per_medium = round(medium_km / medium, 1)
        elif korte > 0:
            km_per_korte = round(rest_km / korte, 1)

    return {
        "week": week_number,
        "fase": legacy["fase"],
        "fase_label": legacy["fase_label"],
        "run_km_totaal": total_km,
        "run_sessies": legacy["run_sessies"],
        "korte_sessies": korte,
        "km_per_korte_sessie": km_per_korte,
        "medium_sessies": medium,
        "km_per_medium_sessie": km_per_medium,
        "lange_duurloop_km": long_km,
        "fiets_sessies": legacy["fiets_sessies"],
        "run_intensiteit": legacy["run_intensiteit"],
        "intensity_gate": legacy["intensity_gate"],
        "fiets_intensiteit": legacy["fiets_intensiteit"],
        "run_tss": legacy["run_tss"],
        "fiets_tss": legacy["fiets_tss"],
        "totaal_tss": legacy["totaal_tss"],
    }


def get_run_intensiteit_gating(week_number: int) -> str:
    """Week-gating in het legacy-vocabulaire (geen/strides/tempoduur/...)."""
    _, weeks = get_active_plan()
    week_number = max(1, min(len(weeks), week_number))
    w = weeks[week_number - 1]
    return _legacy_run_intensity(w.phase, w.intensity_gate)


def print_full_plan() -> None:
    """Print het volledige macroplan (CLI-inspectie)."""
    goal, weeks = get_active_plan()
    print(f"\n{'=' * 90}")
    print(f"  MACROPLAN — {goal.type} op {goal.event_date} "
          f"(doel: {goal.target_value or '-'})")
    print(f"{'=' * 90}")
    print(f"  {'Wk':>3} | {'Maandag':>10} | {'Fase':18} | {'Run km':>6} | "
          f"{'Sess':>4} | {'Long':>5} | {'Fiets':>5} | {'TSS':>4} | "
          f"{'Deload':>6} | Gate")
    for i, w in enumerate(weeks, 1):
        print(f"  {i:3d} | {w.week_start.isoformat():>10} | {w.phase:18} | "
              f"{w.run_km:6.1f} | {w.run_sessions:4d} | {w.long_run_km:5.1f} | "
              f"{w.bike_sessions:5d} | {w.tss_target:4d} | "
              f"{'ja' if w.is_deload else '':>6} | {w.intensity_gate}")
    print(f"{'=' * 90}\n")


# ── PROXIES voor module-level tabellen (load_manager importeert deze) ─────

class WeeklyPlanProxy:
    """Lijst-achtige view op get_weekly_plan() — altijd vers uit de DB."""

    def __getitem__(self, idx):
        return get_weekly_plan()[idx]

    def __len__(self):
        return len(get_weekly_plan())

    def __iter__(self):
        return iter(get_weekly_plan())


class WeeklyTssTableProxy:
    """Dict-achtige view op get_weekly_tss_table()."""

    def __getitem__(self, key):
        return get_weekly_tss_table()[key]

    def __contains__(self, key):
        return key in get_weekly_tss_table()

    def get(self, key, default=None):
        return get_weekly_tss_table().get(key, default)

    def keys(self):
        return get_weekly_tss_table().keys()

    def items(self):
        return get_weekly_tss_table().items()

    def __iter__(self):
        return iter(get_weekly_tss_table())

    def __len__(self):
        return len(get_weekly_tss_table())
