"""Rolling re-periodisatie — wekelijkse herijking van het macroplan
(UPGRADE_PLAN §4.2, Fase 2).

Elke zondagavond (of on-demand):
  1. Werkelijke CTL + uitgevoerd run-volume ophalen.
  2. Afwijking t.o.v. plan_weeks bepalen. Binnen ±10%: niets doen.
     Daarbuiten: generator opnieuw draaien VANAF VOLGENDE WEEK met de
     huidige werkelijkheid als startpunt; het verleden blijft staan.
  3. Haalbaarheidscheck: CTL-projectie op racedag → advies-string i.p.v.
     stiekem forceren.

Injury-guard-status drukt het pad (sluit aan op de bestaande gating):
  - YELLOW: intensiteitssessies eruit → gates gecapt op strides (Z1/Z2),
    TSS-band -20% op intensiteitsbudget (≈ -10% totaal).
  - RED: alleen Z1 → gate "geen", TSS-band -30%.

CLI:  python -m core.replan_goal [--dry-run]
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
from typing import Optional

from core import goal_engine
from core.goal_engine import Goal
from core.periodization_generator import (
    AthleteProfile,
    PlanWeek,
    build_athlete_profile,
    generate_plan,
    load_plan_weeks,
    persist_plan_weeks,
    project_ctl,
    GOAL_TYPE_PROFILES,
    _ctl_goal_range,
    MAX_CTL_RAMP_PER_MONTH,
)

DEVIATION_BAND = 0.10

# Injury-gating: cap op de gate + TSS-reductie per status
_INJURY_PRESSURE = {
    "geel": {"gate_cap": "strides", "tss_factor": 0.90},
    "rood": {"gate_cap": "geen", "tss_factor": 0.70},
}
_GATE_ORDER = ["geen", "strides", "tempoduur", "drempel", "race_specifiek"]


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _actual_run_km_from_activities(activities: list, week_start: date) -> float:
    """Som van run-km in de week die op ``week_start`` begint."""
    total = 0.0
    week_end = week_start + timedelta(days=7)
    for act in activities or []:
        if act.get("type") != "Run":
            continue
        try:
            d = date.fromisoformat((act.get("start_date_local") or "")[:10])
        except ValueError:
            continue
        if week_start <= d < week_end:
            total += (act.get("distance") or 0) / 1000.0
    return round(total, 1)


def _actual_tss_from_activities(activities: list, week_start: date) -> float:
    """Som van TSS (icu_training_load) in de week die op ``week_start`` begint."""
    total = 0.0
    week_end = week_start + timedelta(days=7)
    for act in activities or []:
        try:
            d = date.fromisoformat((act.get("start_date_local") or "")[:10])
        except ValueError:
            continue
        if week_start <= d < week_end:
            total += act.get("icu_training_load") or act.get("training_load") or 0
    return round(total, 1)


def _apply_injury_pressure(weeks: list[PlanWeek], status: str) -> list[str]:
    """Cap gates + reduceer TSS-banden voor de gegeven injury-status."""
    pressure = _INJURY_PRESSURE.get(status)
    if not pressure:
        return []
    cap_idx = _GATE_ORDER.index(pressure["gate_cap"])
    notes = []
    for w in weeks:
        if _GATE_ORDER.index(w.intensity_gate) > cap_idx:
            notes.append(
                f"{w.week_start}: gate {w.intensity_gate} → "
                f"{pressure['gate_cap']} (injury {status})"
            )
            w.intensity_gate = pressure["gate_cap"]
        w.tss_target_min = round(w.tss_target_min * pressure["tss_factor"])
        w.tss_target_max = round(w.tss_target_max * pressure["tss_factor"])
    return notes


def _feasibility_advice(goal: Goal, profile: AthleteProfile,
                        future_weeks: list[PlanWeek]) -> Optional[str]:
    """Projecteer CTL over het resterende pad; advies als doel-CTL wankelt."""
    gt = GOAL_TYPE_PROFILES.get(goal.type)
    if gt is None:
        return None
    ctl_goal = _ctl_goal_range(gt, profile)
    if ctl_goal == (0.0, 0.0):
        return None
    path = project_ctl(profile.current_ctl,
                       [w.tss_target for w in future_weeks])
    peak = max(path) if path else profile.current_ctl
    months_left = max(0.5, len(future_weeks) / 4.33)
    needed_ramp = (ctl_goal[0] - profile.current_ctl) / months_left
    if needed_ramp > MAX_CTL_RAMP_PER_MONTH:
        return (
            f"Doel-CTL {ctl_goal[0]:.0f} vereist {needed_ramp:.1f} CTL/maand "
            f"(max ~{MAX_CTL_RAMP_PER_MONTH:.0f}) — niet realistisch meer. "
            f"Overweeg de streeftijd bij te stellen of het doel te verzetten."
        )
    if peak < ctl_goal[0] - 3:
        return (
            f"Geprojecteerde piek-CTL ({peak:.0f}) blijft onder het "
            f"doelbereik ({ctl_goal[0]:.0f}–{ctl_goal[1]:.0f}). "
            f"Een iets conservatievere streeftijd is realistischer."
        )
    return None


def weekly_recalibration(
    today: Optional[date] = None,
    *,
    goal: Optional[Goal] = None,
    actual_ctl: Optional[float] = None,
    actual_run_km: Optional[float] = None,
    recent_run_sessions: Optional[int] = None,
    injury_status: Optional[str] = None,
    activities: Optional[list] = None,
    persist: bool = True,
) -> dict:
    """Herijk het macroplan van het actieve A-doel op de werkelijkheid.

    Alle werkelijkheids-inputs zijn injecteerbaar (tests/scheduler); zonder
    expliciete waarden worden ze uit de athlete-state en ``activities``
    afgeleid.

    Returns dict met o.a.::

        status:   no_goal | within_band | replanned | injury_adjusted
        deviation_pct, advice, notes, regenerated_from, warnings
    """
    if today is None:
        today = date.today()
    if goal is None:
        goal = goal_engine.get_active_goal()
    if goal is None or goal.id is None:
        return {"status": "no_goal", "advice": "Geen actief A-doel.",
                "notes": [], "warnings": []}

    plan = load_plan_weeks(goal.id)
    if not plan:
        return {"status": "no_goal",
                "advice": "Actief doel heeft nog geen macroplan — draai "
                          "scripts/seed_goal.py of de goal wizard.",
                "notes": [], "warnings": []}

    this_monday = _monday(today)
    next_monday = this_monday + timedelta(days=7)
    current = next((w for w in plan if w.week_start == this_monday), None)

    # ── 1. Werkelijkheid ophalen (injecteerbaar) ──
    state: dict = {}
    if actual_ctl is None:
        try:
            from shared import load_state
            state = load_state() or {}
            actual_ctl = float(state.get("load", {}).get("ctl_estimate", 45.0))
        except Exception:
            actual_ctl = 45.0
    if injury_status is None:
        injury_status = (state.get("injury", {}) or {}).get("status", "groen")
    if actual_run_km is None and activities is not None:
        actual_run_km = _actual_run_km_from_activities(activities, this_monday)
    actual_tss = _actual_tss_from_activities(activities, this_monday) \
        if activities is not None else None

    # ── 2. Afwijking t.o.v. plan_weeks bepalen (±10% band) ──
    # Band op het uitgevoerde werk (km + TSS) vs de geplande week; de
    # werkelijke CTL stuurt het profiel + de haalbaarheidscheck.
    deviations: dict[str, float] = {}
    if current is not None and current.run_km > 0 and actual_run_km is not None:
        deviations["run_km"] = (actual_run_km - current.run_km) / current.run_km
    if current is not None and current.tss_target > 0 and actual_tss is not None:
        deviations["tss"] = (actual_tss - current.tss_target) / current.tss_target

    max_dev = max((abs(v) for v in deviations.values()), default=0.0)
    within_band = max_dev <= DEVIATION_BAND

    future = [w for w in plan if w.week_start >= next_monday]
    notes: list[str] = []
    warnings: list[str] = []
    advice: Optional[str] = None

    if within_band:
        status = "within_band"
        # Injury-status drukt het pad ook als het volume op schema ligt.
        if injury_status in _INJURY_PRESSURE and future:
            notes = _apply_injury_pressure(future, injury_status)
            if persist:
                persist_plan_weeks(goal.id, future, from_week=next_monday)
            status = "injury_adjusted"
        profile = AthleteProfile(
            current_ctl=actual_ctl,
            recent_run_km_avg=actual_run_km if actual_run_km is not None
            else (current.run_km if current else 21.0),
            recent_run_sessions=recent_run_sessions
            or (current.run_sessions if current else 3),
        )
        advice = _feasibility_advice(goal, profile, future) or \
            "Op schema — plan ongewijzigd."
        return {
            "status": status, "deviation_pct": round(max_dev * 100, 1),
            "deviations": {k: round(v * 100, 1) for k, v in deviations.items()},
            "advice": advice, "notes": notes, "warnings": warnings,
            "regenerated_from": None,
        }

    # ── Buiten de band: generator herdraaien vanaf volgende week ──
    profile = build_athlete_profile(activities=activities)
    profile.current_ctl = actual_ctl
    if actual_run_km is not None:
        profile.recent_run_km_avg = actual_run_km
    if recent_run_sessions is not None:
        profile.recent_run_sessions = recent_run_sessions
    elif current is not None:
        profile.recent_run_sessions = current.run_sessions

    result = generate_plan(
        goal.model_copy(update={"id": goal.id}),
        profile,
        plan_start=next_monday,
        intermediate_goals=goal_engine.get_intermediate_goals(goal),
    )
    warnings = result.warnings
    notes = _apply_injury_pressure(result.weeks, injury_status)

    if persist:
        persist_plan_weeks(goal.id, result.weeks, from_week=next_monday)

    # ── 3. Haalbaarheidscheck ──
    advice = _feasibility_advice(goal, profile, result.weeks) or (
        f"Plan herijkt vanaf {next_monday} op werkelijke situatie "
        f"(CTL {actual_ctl:.0f}, {profile.recent_run_km_avg:.0f} km/wk)."
    )

    return {
        "status": "replanned",
        "deviation_pct": round(max_dev * 100, 1),
        "deviations": {k: round(v * 100, 1) for k, v in deviations.items()},
        "advice": advice,
        "notes": notes,
        "warnings": warnings,
        "regenerated_from": next_monday.isoformat(),
        "new_weeks": len(result.weeks),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Wekelijkse herijking van het macroplan (§4.2)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Toon de herijking zonder te persisteren")
    args = parser.parse_args()

    activities = None
    try:
        import intervals_client as api
        activities = api.get_activities(
            start=date.today() - timedelta(days=42), end=date.today())
    except Exception as e:
        print(f"  intervals.icu niet beschikbaar ({e}) — herijking op state.")

    report = weekly_recalibration(activities=activities,
                                  persist=not args.dry_run)
    print("\n=== Rolling re-periodisatie ===")
    for key in ("status", "deviation_pct", "deviations",
                "regenerated_from", "advice"):
        if key in report:
            print(f"  {key}: {report[key]}")
    for n in report.get("notes", []):
        print(f"  injury: {n}")
    for w in report.get("warnings", []):
        print(f"  warning: {w}")


if __name__ == "__main__":
    main()
