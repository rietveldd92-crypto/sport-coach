"""Parametrische periodisatie-generator (UPGRADE_PLAN §4.1, Fase 2).

Vervangt de hardcoded tabellen in ``agents/marathon_periodizer.py`` door een
generator: doel (type, datum, streeftijd) + atleetprofiel → lijst
``PlanWeek``-objecten met exact de velden van de ``plan_weeks``-tabel.

Algoritme (Issurin-blokken, Delahaije-invulling):
  1. Blokverdeling — weken-tot-doel over fasen volgens horizon-variant.
  2. Volumecurve — vanaf werkelijk startvolume, +15%/wk groei (binnen de
     consistency-regels van load_manager), deloads volgens meso-ritme
     (accumulatie 3:1, transformatie 2:1).
  3. Intensiteits-gating — fase-gedreven i.p.v. weeknummer-gedreven.
  4. CTL-doelpad — projectie + haalbaarheids-warnings (max ~5 CTL/maand).
  5. Sport-mix — per doeltype (run-primair, bike-primair, multi).
  6. B/C-doelen — mini-taper + korte recovery, lokaal gestanst.

Doeltype-profielen zijn data (``GOAL_TYPE_PROFILES``), geen if-bomen.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from pydantic import BaseModel

from core.goal_engine import Goal


# ── OUTPUT-MODEL (exact de kolommen van de plan_weeks-tabel) ──────────────

class PlanWeek(BaseModel):
    goal_id: int = 0
    week_start: date
    phase: str
    is_deload: bool = False
    tss_target_min: int
    tss_target_max: int
    run_km: float
    run_sessions: int
    long_run_km: float
    bike_sessions: int
    intensity_gate: str            # geen|strides|tempoduur|drempel|race_specifiek
    generated_at: Optional[str] = None

    model_config = {"extra": "forbid"}

    @property
    def tss_target(self) -> int:
        """Midden van de TSS-band — de puntschatting voor deze week."""
        return round((self.tss_target_min + self.tss_target_max) / 2)


@dataclass
class GenerationResult:
    weeks: list[PlanWeek]
    warnings: list[str]
    ctl_projection: list[float]
    peak_km: float


# ── ATLEETPROFIEL ─────────────────────────────────────────────────────────

@dataclass
class AthleteProfile:
    """Startsituatie van de atleet — injecteerbaar in tests."""

    current_ctl: float = 45.0
    recent_run_km_avg: float = 21.0    # gem. weekvolume, laatste ~6 wk
    recent_run_sessions: int = 3       # gem. run-sessies per week
    ftp: int = 290
    hrmax: int = 192
    days_symptom_free: int = 99        # injury-context (4e-run-trigger)


def build_athlete_profile(activities: Optional[list] = None,
                          state: Optional[dict] = None) -> AthleteProfile:
    """Bouw het profiel uit load_manager-state + intervals.icu activities.

    Beide bronnen zijn optioneel/injecteerbaar; ontbrekende data valt
    terug op conservatieve defaults.
    """
    if state is None:
        try:
            from shared import load_state
            state = load_state() or {}
        except Exception:
            state = {}

    load = state.get("load", {}) or {}
    ctl = float(load.get("ctl_estimate") or 45.0)
    days_free = int(state.get("injury", {}).get("days_symptom_free", 99) or 99)

    run_km_avg, run_sessions = 21.0, 3
    ftp = 290
    if activities:
        km_by_week: dict[str, float] = {}
        sessions_by_week: dict[str, int] = {}
        for act in activities:
            if act.get("icu_ftp") and act.get("type") in ("Ride", "VirtualRide"):
                ftp = act["icu_ftp"]
            if act.get("type") != "Run":
                continue
            day_str = (act.get("start_date_local") or "")[:10]
            try:
                d = date.fromisoformat(day_str)
            except ValueError:
                continue
            monday = (d - timedelta(days=d.weekday())).isoformat()
            km = (act.get("distance") or 0) / 1000.0
            km_by_week[monday] = km_by_week.get(monday, 0.0) + km
            sessions_by_week[monday] = sessions_by_week.get(monday, 0) + 1
        if km_by_week:
            run_km_avg = round(sum(km_by_week.values()) / len(km_by_week), 1)
            run_sessions = round(
                sum(sessions_by_week.values()) / len(sessions_by_week)
            )

    return AthleteProfile(
        current_ctl=ctl,
        recent_run_km_avg=run_km_avg,
        recent_run_sessions=max(1, run_sessions),
        ftp=int(state.get("ftp") or ftp),
        hrmax=int(state.get("hrmax") or 192),
        days_symptom_free=days_free,
    )


# ── DOELTYPE-PROFIELEN (data, geen if-bomen) ──────────────────────────────

@dataclass(frozen=True)
class GoalTypeProfile:
    sport: str                          # run|ride|multi
    volume_driver: str                  # "km" | "tss"
    # Piekvolume-formule: peak_km = clamp(base_peak_km * ref_time/target, bounds)
    base_peak_km: float = 0.0
    reference_time_s: int = 0
    peak_km_bounds: tuple[float, float] = (0.0, 0.0)
    long_run_fraction: float = 0.35     # marathon bewust >0.35 (onderhandeld)
    growth_rate: float = 0.15           # binnen consistency-cap (+15/+20%)
    tss_per_km: float = 5.5
    # Sessies
    peak_sessions: int = 4              # run-sessies in specifieke fases
    acc_sessions_max: int = 4           # cap na 4e-run-trigger in accumulatie
    taper_sessions: int = 3
    fourth_run_trigger_km: float = 40.0
    run_gating: bool = True             # fase-gedreven run-intensiteit
    # Sport-mix: fiets-ondersteuning
    bike_sessions_acc: int = 3
    bike_sessions_specific: int = 2
    bike_sessions_real: int = 0
    bike_intro_tss: tuple[float, ...] = (370, 415)  # ramp-in eerste buildweken
    bike_build_tss: float = 480.0       # plateau bij bike_sessions_acc sessies
    # Deloads: vroege meso's diep (blessure-terugkeer), later Delahaije-blokken
    deload_run_factor: float = 0.70
    deload_tss_factor_early: float = 0.45
    deload_tss_factor_late: float = 0.65
    early_deloads: int = 2
    # Volume-modulatie per bloktype (transformatie: intensiteit ↑, volume ↓)
    trans_volume_factor: float = 0.92
    trans2_volume_factor: float = 0.88
    # Realisatie (race-specifieke invulling)
    race_week_fraction: float = 0.20
    # CTL-doelpad
    ctl_target: tuple[float, float] = (0.0, 0.0)
    ctl_target_delta: float = 0.0       # FTP-blok: +5–8 punten i.p.v. absolute range


GOAL_TYPE_PROFILES: dict[str, GoalTypeProfile] = {
    "marathon": GoalTypeProfile(
        sport="run", volume_driver="km",
        base_peak_km=50.0, reference_time_s=int(3.5 * 3600),   # ref 3:30
        peak_km_bounds=(45.0, 65.0),                           # sub-3 → ~58
        long_run_fraction=0.42,        # onderhandeld: long moet écht lang zijn
        peak_sessions=5, acc_sessions_max=4,
        ctl_target=(75.0, 85.0),
    ),
    "half": GoalTypeProfile(
        sport="run", volume_driver="km",
        base_peak_km=45.0, reference_time_s=int(100 * 60),     # ref 1:40
        peak_km_bounds=(38.0, 55.0),
        long_run_fraction=0.35, peak_sessions=5,
        ctl_target=(65.0, 78.0),
    ),
    "10k": GoalTypeProfile(
        sport="run", volume_driver="km",
        base_peak_km=40.0, reference_time_s=int(45 * 60),      # ref 0:45
        peak_km_bounds=(30.0, 50.0),                           # §4.1: 10k → ~45
        long_run_fraction=0.32, peak_sessions=4,
        bike_intro_tss=(220,), bike_build_tss=300.0,
        ctl_target=(60.0, 72.0),
    ),
    "5k": GoalTypeProfile(
        sport="run", volume_driver="km",
        base_peak_km=35.0, reference_time_s=int(22 * 60),      # ref 0:22
        peak_km_bounds=(28.0, 45.0),
        long_run_fraction=0.30, peak_sessions=4,
        bike_intro_tss=(200,), bike_build_tss=270.0,
        ctl_target=(55.0, 68.0),
    ),
    "gran_fondo": GoalTypeProfile(
        sport="ride", volume_driver="tss",
        long_run_fraction=0.0, run_gating=False,
        peak_sessions=2, acc_sessions_max=2, taper_sessions=2,
        fourth_run_trigger_km=0.0,
        bike_sessions_acc=4, bike_sessions_specific=3, bike_sessions_real=2,
        deload_tss_factor_early=0.65, early_deloads=0,  # geen injury-return
        ctl_target=(70.0, 80.0),                               # §4.1: 70+
    ),
    "ftp": GoalTypeProfile(
        sport="ride", volume_driver="tss",
        long_run_fraction=0.0, run_gating=False,
        peak_sessions=2, acc_sessions_max=2, taper_sessions=2,
        fourth_run_trigger_km=0.0,
        bike_sessions_acc=4, bike_sessions_specific=3, bike_sessions_real=2,
        deload_tss_factor_early=0.65, early_deloads=0,
        ctl_target_delta=6.5,                                  # §4.1: +5–8 punten
    ),
    "triathlon": GoalTypeProfile(
        sport="multi", volume_driver="km",
        base_peak_km=40.0, reference_time_s=0, peak_km_bounds=(40.0, 40.0),
        long_run_fraction=0.35, peak_sessions=4,
        bike_sessions_acc=3, bike_sessions_specific=3, bike_sessions_real=1,
        bike_intro_tss=(300,), bike_build_tss=380.0,
        ctl_target=(70.0, 82.0),
    ),
}
GOAL_TYPE_PROFILES["custom"] = GOAL_TYPE_PROFILES["marathon"]


# ── STAP 1: BLOKVERDELING ─────────────────────────────────────────────────

_PHASE_RATIOS_LONG = [        # ≥20 wk (≈ de huidige 28-weeks verdeling)
    ("accumulatie_I", 0.25), ("accumulatie_II", 0.25),
    ("transformatie_I", 0.15), ("accumulatie_III", 0.14),
    ("transformatie_II", 0.11), ("realisatie", 0.10),
]
_PHASE_RATIOS_MID = [         # 12–19 wk
    ("accumulatie_I", 0.40), ("transformatie_I", 0.25),
    ("accumulatie_II", 0.15), ("transformatie_II", 0.12),
    ("realisatie", 0.08),
]
_PHASE_RATIOS_SHORT = [       # <12 wk → warning
    ("accumulatie_I", 0.45), ("transformatie_I", 0.35), ("realisatie", 0.20),
]


def split_phases(n_weeks: int) -> tuple[list[tuple[str, int]], list[str]]:
    """Verdeel ``n_weeks`` over fasen (largest-remainder rounding)."""
    warnings: list[str] = []
    if n_weeks >= 20:
        ratios = _PHASE_RATIOS_LONG
    elif n_weeks >= 12:
        ratios = _PHASE_RATIOS_MID
    else:
        ratios = _PHASE_RATIOS_SHORT
        warnings.append(
            f"Korte aanloop ({n_weeks} wk < 12): doel mogelijk niet haalbaar."
        )

    raw = [(name, n_weeks * frac) for name, frac in ratios]
    counts = {name: int(math.floor(val)) for name, val in raw}
    remainder = n_weeks - sum(counts.values())
    by_frac = sorted(raw, key=lambda nv: nv[1] - math.floor(nv[1]), reverse=True)
    for name, _ in by_frac[:remainder]:
        counts[name] += 1

    # Realisatie minimaal 1 week (race-week), steel van de grootste fase.
    if n_weeks >= len(ratios) and counts.get("realisatie", 0) == 0:
        biggest = max(counts, key=lambda k: counts[k])
        counts[biggest] -= 1
        counts["realisatie"] = 1

    phases = [(name, counts[name]) for name, _ in ratios if counts[name] > 0]
    return phases, warnings


def _block_type(phase: str) -> str:
    if phase.startswith("accumulatie"):
        return "acc"
    if phase.startswith("transformatie"):
        return "trans"
    return "real"


# ── STAP 3: FASE-GEDREVEN INTENSITEITS-GATING ─────────────────────────────

def _gate_for_week(profile: GoalTypeProfile, phase: str, wif: int,
                   phase_len: int, is_deload: bool, trans_seen: bool,
                   is_last_trans: bool) -> str:
    """Gate per week, gedreven door fase + positie binnen de fase."""
    block = _block_type(phase)
    if block == "real":
        return "race_specifiek"
    if not profile.run_gating:
        return "race_specifiek" if block == "trans" else "geen"

    if block == "trans":
        # Eerste trans-blok: drempelwerk; laatste trans-blok: race-specifiek.
        return "race_specifiek" if is_last_trans else "drempel"

    # Accumulatie-blokken
    frac = wif / max(1, phase_len)
    if not trans_seen and phase.endswith("_I"):
        # Blessure-terugkeer/basis: geen → strides → tempoduur
        base = "geen" if frac <= 0.60 else ("strides" if frac <= 0.86 else "tempoduur")
    elif not trans_seen:
        # Tweede acc-blok vóór transformatie: tempoduur, staart → drempel
        base = "drempel" if frac > 0.80 else "tempoduur"
    else:
        # Acc-blok ná transformatie (piekvolume): terug naar Z1-dominantie
        base = "tempoduur"

    if is_deload:
        return "geen" if base == "geen" else "strides"
    return base


# ── STAP 4: CTL-DOELPAD ───────────────────────────────────────────────────

MAX_CTL_RAMP_PER_MONTH = 5.0


def project_ctl(start_ctl: float, weekly_tss: list[float]) -> list[float]:
    """Projecteer CTL (42-daags EWMA) over de weekly-TSS-reeks."""
    ctl = start_ctl
    out = []
    for tss in weekly_tss:
        daily = tss / 7.0
        for _ in range(7):
            ctl = ctl + (daily - ctl) / 42.0
        out.append(round(ctl, 1))
    return out


def _ctl_goal_range(profile: GoalTypeProfile,
                    athlete: AthleteProfile) -> tuple[float, float]:
    if profile.ctl_target_delta:
        return (athlete.current_ctl + profile.ctl_target_delta - 1.5,
                athlete.current_ctl + profile.ctl_target_delta + 1.5)
    return profile.ctl_target


# ── HOOFDGENERATOR ────────────────────────────────────────────────────────

def compute_peak_km(profile: GoalTypeProfile, target_value: Optional[str],
                    start_km: float) -> float:
    """Piekvolume-formule: f(doeltype, streeftijd)."""
    if profile.volume_driver != "km" or profile.base_peak_km <= 0:
        return 0.0
    peak = profile.base_peak_km
    target_s = _parse_time_seconds(target_value)
    if target_s and profile.reference_time_s:
        peak = profile.base_peak_km * (profile.reference_time_s / target_s)
    lo, hi = profile.peak_km_bounds
    peak = max(lo, min(hi, peak))
    return max(peak, start_km)  # nooit onder het huidige volume


def _parse_time_seconds(value: Optional[str]) -> Optional[int]:
    """'2:59:00' → 10740; '42:30' → 2550; anders None (bv. '310W')."""
    if not value:
        return None
    parts = value.strip().split(":")
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return None
    if len(nums) == 3:
        return nums[0] * 3600 + nums[1] * 60 + nums[2]
    if len(nums) == 2:
        return nums[0] * 60 + nums[1]
    return None


def generate_plan(
    goal: Goal,
    athlete: AthleteProfile,
    plan_start: date,
    intermediate_goals: Optional[list[Goal]] = None,
) -> GenerationResult:
    """Genereer het volledige macroplan voor ``goal``.

    Args:
        goal: het A-doel (type bepaalt het GoalTypeProfile).
        athlete: startsituatie (CTL, recent volume/sessies, FTP, HRmax).
        plan_start: maandag van week 1. Wordt genormaliseerd naar maandag.
        intermediate_goals: B/C-doelen binnen de horizon (mini-tapers).

    Returns:
        GenerationResult met PlanWeek-lijst + warnings + CTL-projectie.
    """
    profile = GOAL_TYPE_PROFILES.get(goal.type, GOAL_TYPE_PROFILES["custom"])
    plan_start = plan_start - timedelta(days=plan_start.weekday())  # → maandag

    n_weeks = (goal.event_date - plan_start).days // 7 + 1
    if n_weeks < 1:
        raise ValueError(
            f"event_date {goal.event_date} ligt vóór plan_start {plan_start}."
        )

    phases, warnings = split_phases(n_weeks)

    # Fase-mapping per week + meta
    phase_of_week: list[tuple[str, int, int]] = []   # (phase, wif, phase_len)
    for name, length in phases:
        for wif in range(1, length + 1):
            phase_of_week.append((name, wif, length))

    trans_names = [n for n, _ in phases if _block_type(n) == "trans"]
    last_trans = trans_names[-1] if trans_names else None

    if profile.volume_driver == "km":
        start_km = max(5.0, athlete.recent_run_km_avg)
    else:
        start_km = round(min(athlete.recent_run_km_avg, 20.0), 1)
    peak_km = compute_peak_km(profile, goal.target_value, start_km)

    # ── Volumecurve + TSS, sequentieel met deload-ritme ──
    try:
        from agents.load_manager import enforce_consistency_rules
    except ImportError:                                    # pragma: no cover
        enforce_consistency_rules = None

    weeks: list[PlanWeek] = []
    build_streak = 0
    deload_count = 0
    last_build_km = start_km
    last_build_tss = 0.0
    if profile.volume_driver == "km":
        sessions = athlete.recent_run_sessions
    else:
        sessions = 2 if start_km > 0 else 0
    fourth_run_pending = False
    seen_trans = False
    consistency_warnings: set[str] = set()

    # TSS-gedreven profielen: CTL-doelpad bepaalt de weekly targets.
    ctl_goal = _ctl_goal_range(profile, athlete)
    n_build_weeks = max(1, sum(1 for p, _, _ in phase_of_week
                               if _block_type(p) != "real"))
    weekly_ramp = 0.0
    if profile.volume_driver == "tss":
        # Factor 2.0 compenseert CTL-verlies in deloads + taper; de cap
        # (max ~5 CTL/maand) blijft de harde grens.
        needed = max(0.0, ctl_goal[0] - athlete.current_ctl)
        weekly_ramp = min(MAX_CTL_RAMP_PER_MONTH / 4.33,
                          needed / n_build_weeks * 2.0)
    sim_ctl = athlete.current_ctl

    taper_index = 0
    n_real = sum(length for name, length in phases if _block_type(name) == "real")

    for i, (phase, wif, phase_len) in enumerate(phase_of_week):
        week_start = plan_start + timedelta(weeks=i)
        block = _block_type(phase)
        if block != "real":
            seen_trans = seen_trans or block == "trans"

        # ── Deload-ritme: accumulatie 3:1, transformatie 2:1 ──
        rhythm = 3 if block == "acc" else 2
        is_deload = block != "real" and build_streak >= rhythm
        is_race_week = (i == len(phase_of_week) - 1)

        if block == "real":
            # ── Realisatie: taper (race-specifieke invulling) ──
            k_pre = n_real - 1
            if is_race_week:
                vol_frac = profile.race_week_fraction
            else:
                step = 0.15 / max(1, k_pre - 1)
                vol_frac = 0.60 - taper_index * step
                taper_index += 1
            run_km = round(peak_km * vol_frac, 1)
            run_sessions_w = profile.taper_sessions if run_km > 0 else 0
            long_km = 0.0 if is_race_week else round(run_km * profile.long_run_fraction, 1)
            if profile.volume_driver == "tss":
                tss = last_build_tss * (0.40 if is_race_week else vol_frac)
                tss += run_km * profile.tss_per_km
            else:
                tss = run_km * profile.tss_per_km
                tss += profile.bike_sessions_real * 55
            bike_sessions = profile.bike_sessions_real
            build_streak = 0
        elif is_deload:
            # ── Deload: -30% run, TSS-diepte afhankelijk van meso-fase ──
            deload_count += 1
            depth = (profile.deload_tss_factor_early
                     if deload_count <= profile.early_deloads
                     else profile.deload_tss_factor_late)
            run_km = round(last_build_km * profile.deload_run_factor, 1)
            run_sessions_w = sessions
            long_km = round(run_km * profile.long_run_fraction, 1)
            tss = last_build_tss * depth
            bike_sessions = max(0, _bike_sessions_for(profile, sessions) - 1)
            build_streak = 0
        else:
            # ── Buildweek: groei binnen consistency-cap, tot piek ──
            build_streak += 1
            if profile.volume_driver == "km":
                phase_cap = peak_km * _phase_volume_factor(profile, phase, last_trans)
                if i == 0:
                    raw_km = min(start_km, phase_cap)
                else:
                    raw_km = min(last_build_km * (1 + profile.growth_rate), phase_cap)
                # 4e-run-trigger: week NA het kruisen van de drempel
                if fourth_run_pending and sessions < profile.acc_sessions_max:
                    if athlete.days_symptom_free >= 14:
                        sessions += 1
                    fourth_run_pending = False
                if (profile.fourth_run_trigger_km
                        and raw_km > profile.fourth_run_trigger_km
                        and sessions < profile.acc_sessions_max):
                    fourth_run_pending = True
                if seen_trans:
                    sessions = max(sessions, profile.peak_sessions)

                if enforce_consistency_rules is not None:
                    check = enforce_consistency_rules(
                        week_target_km=raw_km,
                        week_prev_km=last_build_km if i > 0 else 0,
                        long_run_km=raw_km * profile.long_run_fraction,
                        days_symptom_free=athlete.days_symptom_free,
                    )
                    raw_km = check["adjusted_km"]
                    for w in check["warnings"]:
                        # Long-run-fractie >35% is bij dit doeltype bewust
                        if profile.long_run_fraction > 0.35 and "Long run" in w:
                            continue
                        consistency_warnings.add(w)

                run_km = round(raw_km, 1)
                run_sessions_w = sessions
                long_km = round(raw_km * profile.long_run_fraction, 1)
                bike_sessions = _bike_sessions_for(profile, sessions)
                run_tss = run_km * profile.tss_per_km
                bike_tss = _bike_tss_for(profile, i, weeks, bike_sessions)
                tss = run_tss + bike_tss
                last_build_km = raw_km
            else:
                # TSS-gedreven (gran fondo / FTP-blok): CTL-doelpad
                run_km = start_km
                run_sessions_w = sessions
                long_km = round(run_km * profile.long_run_fraction, 1)
                bike_sessions = (profile.bike_sessions_specific
                                 if block == "trans" else profile.bike_sessions_acc)
                tss = sim_ctl * 7 + 42 * weekly_ramp
                last_build_km = run_km
            last_build_tss = tss

        # CTL-simulatie bijhouden (voor het TSS-gedreven pad)
        daily = tss / 7.0
        for _ in range(7):
            sim_ctl = sim_ctl + (daily - sim_ctl) / 42.0

        gate = _gate_for_week(
            profile, phase, wif, phase_len, is_deload,
            trans_seen=seen_trans and block != "trans",
            is_last_trans=(phase == last_trans),
        )

        weeks.append(PlanWeek(
            goal_id=goal.id or 0,
            week_start=week_start,
            phase=phase,
            is_deload=is_deload,
            tss_target_min=round(tss * 0.93),
            tss_target_max=round(tss * 1.07),
            run_km=round(run_km, 1),
            run_sessions=run_sessions_w,
            long_run_km=round(long_km, 1),
            bike_sessions=bike_sessions,
            intensity_gate=gate,
        ))

    # ── Stap 6: B/C-doelen → mini-taper + recovery ──
    if intermediate_goals:
        _stamp_intermediate_goals(weeks, intermediate_goals, warnings)

    # ── Stap 4: CTL-doelpad + haalbaarheid ──
    tss_series = [w.tss_target for w in weeks]
    ctl_path = project_ctl(athlete.current_ctl, tss_series)
    months = n_weeks / 4.33
    if ctl_goal != (0.0, 0.0):
        needed_ramp = (ctl_goal[0] - athlete.current_ctl) / max(0.5, months)
        if needed_ramp > MAX_CTL_RAMP_PER_MONTH:
            warnings.append(
                f"Vereiste CTL-ramp ({needed_ramp:.1f}/maand) > "
                f"{MAX_CTL_RAMP_PER_MONTH:.0f}/maand — doel-CTL "
                f"{ctl_goal[0]:.0f} waarschijnlijk niet haalbaar; "
                f"overweeg de streeftijd bij te stellen."
            )
        elif ctl_path and max(ctl_path) < ctl_goal[0] - 3:
            # Piek-CTL vóór de taper is de maat: de taper laat CTL bewust
            # zakken in ruil voor TSB (vorm) op racedag.
            warnings.append(
                f"Geprojecteerde piek-CTL ({max(ctl_path):.0f}) ligt onder "
                f"het doelbereik ({ctl_goal[0]:.0f}–{ctl_goal[1]:.0f})."
            )

    warnings.extend(sorted(consistency_warnings))
    return GenerationResult(
        weeks=weeks, warnings=warnings, ctl_projection=ctl_path, peak_km=peak_km,
    )


def _phase_volume_factor(profile: GoalTypeProfile, phase: str,
                         last_trans: Optional[str]) -> float:
    block = _block_type(phase)
    if block == "trans":
        return (profile.trans2_volume_factor if phase == last_trans
                else profile.trans_volume_factor)
    return 1.0


def _bike_sessions_for(profile: GoalTypeProfile, run_sessions: int) -> int:
    """Sport-mix: minder fiets-slots zodra de run-frequentie piekt."""
    if run_sessions >= profile.peak_sessions and profile.peak_sessions > profile.acc_sessions_max:
        return profile.bike_sessions_specific
    return profile.bike_sessions_acc


def _bike_tss_for(profile: GoalTypeProfile, week_idx: int,
                  prior_weeks: list[PlanWeek], bike_sessions: int) -> float:
    """Fiets-ondersteunings-TSS: ramp-in, daarna plateau (geschaald op slots)."""
    n_prior_builds = sum(1 for w in prior_weeks if not w.is_deload
                         and _block_type(w.phase) != "real")
    if n_prior_builds < len(profile.bike_intro_tss):
        base = profile.bike_intro_tss[n_prior_builds]
    else:
        base = profile.bike_build_tss
    if profile.bike_sessions_acc > 0:
        return base * (bike_sessions / profile.bike_sessions_acc)
    return 0.0


def _stamp_intermediate_goals(weeks: list[PlanWeek],
                              intermediate_goals: list[Goal],
                              warnings: list[str]) -> None:
    """B/C-doelen: 5–7-daagse mini-taper + 3-daagse recovery, lokaal
    gestanst zonder de blokstructuur te breken."""
    for g in intermediate_goals:
        if g.priority not in ("B", "C"):
            continue
        for idx, w in enumerate(weeks):
            if w.week_start <= g.event_date < w.week_start + timedelta(days=7):
                _scale_week(w, 0.75)
                w.long_run_km = round(min(w.long_run_km, w.run_km * 0.30), 1)
                if idx + 1 < len(weeks) and _block_type(weeks[idx + 1].phase) != "real":
                    _scale_week(weeks[idx + 1], 0.90)
                break
        else:
            warnings.append(
                f"B/C-doel {g.type} op {g.event_date} valt buiten de planhorizon."
            )


def _scale_week(w: PlanWeek, factor: float) -> None:
    w.run_km = round(w.run_km * factor, 1)
    w.long_run_km = round(w.long_run_km * factor, 1)
    w.tss_target_min = round(w.tss_target_min * factor)
    w.tss_target_max = round(w.tss_target_max * factor)


# ── PERSISTENTIE ──────────────────────────────────────────────────────────

def persist_plan_weeks(goal_id: int, weeks: list[PlanWeek],
                       from_week: Optional[date] = None) -> int:
    """Schrijf plan_weeks naar SQLite.

    ``from_week=None`` vervangt het hele plan; met een datum worden
    alleen weken >= from_week overschreven — het verleden blijft staan.
    Returns: aantal geschreven rijen.
    """
    import history_db
    history_db.ensure_migrations()

    from_iso = from_week.isoformat() if from_week else None
    now = datetime.now().isoformat()
    rows = []
    for w in weeks:
        ws = w.week_start.isoformat()
        if from_iso and ws < from_iso:
            continue
        rows.append((
            goal_id, ws, w.phase, 1 if w.is_deload else 0,
            w.tss_target_min, w.tss_target_max,
            w.run_km, w.run_sessions, w.long_run_km, w.bike_sessions,
            w.intensity_gate, w.generated_at or now,
        ))

    with history_db._connect() as conn:
        if from_iso:
            conn.execute(
                "DELETE FROM plan_weeks WHERE goal_id = ? AND week_start >= ?",
                (goal_id, from_iso),
            )
        else:
            conn.execute("DELETE FROM plan_weeks WHERE goal_id = ?", (goal_id,))
        conn.executemany(
            """
            INSERT OR REPLACE INTO plan_weeks
                (goal_id, week_start, phase, is_deload,
                 tss_target_min, tss_target_max,
                 run_km, run_sessions, long_run_km, bike_sessions,
                 intensity_gate, generated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
    return len(rows)


def load_plan_weeks(goal_id: int) -> list[PlanWeek]:
    """Lees het macroplan van een goal, gesorteerd op week_start."""
    import history_db
    history_db.ensure_migrations()
    with history_db._connect() as conn:
        rows = conn.execute(
            "SELECT * FROM plan_weeks WHERE goal_id = ? ORDER BY week_start",
            (goal_id,),
        ).fetchall()
    return [
        PlanWeek(
            goal_id=r["goal_id"],
            week_start=date.fromisoformat(r["week_start"]),
            phase=r["phase"],
            is_deload=bool(r["is_deload"]),
            tss_target_min=r["tss_target_min"],
            tss_target_max=r["tss_target_max"],
            run_km=r["run_km"],
            run_sessions=r["run_sessions"],
            long_run_km=r["long_run_km"],
            bike_sessions=r["bike_sessions"],
            intensity_gate=r["intensity_gate"],
            generated_at=r["generated_at"],
        )
        for r in rows
    ]
