"""Seed het echte A-doel: Amsterdam Marathon, 18 oktober 2026, sub-3:00.

Maakt (idempotent) het goal aan in de ``goals``-tabel en genereert +
persisteert het volledige macroplan in ``plan_weeks``.

Gebruik:
    python scripts/seed_goal.py            # seed + print plan
    python scripts/seed_goal.py --replan   # her-genereer plan_weeks
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import goal_engine, plan_provider  # noqa: E402
from core.goal_engine import Goal  # noqa: E402
from core.periodization_generator import (  # noqa: E402
    AthleteProfile,
    build_athlete_profile,
    generate_plan,
    persist_plan_weeks,
)

RACE_DATE = date(2026, 10, 18)
PLAN_START = date(2026, 4, 6)   # maandag van week 1 (na deload-week)

# Startsituatie bij plan_start (fysio-baseline, zie oude marathon_periodizer):
# 3 runs/week, ~21 km, CTL ~45. Het plan is vanaf deze week gegenereerd;
# rolling re-periodisatie (core/replan_goal.py) herijkt op de werkelijkheid.
SEED_PROFILE = AthleteProfile(
    current_ctl=45.0, recent_run_km_avg=21.0, recent_run_sessions=3,
    ftp=290, hrmax=192, days_symptom_free=99,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Amsterdam-marathondoel")
    parser.add_argument("--replan", action="store_true",
                        help="Her-genereer plan_weeks voor het bestaande doel")
    parser.add_argument("--profile-from-intervals", action="store_true",
                        help="Atleetprofiel uit intervals.icu activities i.p.v. "
                             "de vaste plan_start-baseline")
    args = parser.parse_args()

    # ── Goal (idempotent) ──
    goal = goal_engine.get_active_goal()
    if goal is None:
        goal = goal_engine.create_goal(Goal(
            type="marathon", sport="run", event_date=RACE_DATE,
            target_value="2:59:00", priority="A", status="active",
        ))
        print(f"  Goal aangemaakt: id={goal.id} marathon {RACE_DATE} sub-3:00")
    else:
        print(f"  Actief A-doel bestaat al: id={goal.id} {goal.type} "
              f"{goal.event_date} ({goal.target_value})")

    # ── Plan genereren + persisteren ──
    from core.periodization_generator import load_plan_weeks
    existing = load_plan_weeks(goal.id)
    if existing and not args.replan:
        print(f"  plan_weeks bestaat al ({len(existing)} weken) — "
              f"gebruik --replan om te hergenereren.")
    else:
        profile = SEED_PROFILE
        if args.profile_from_intervals:
            try:
                import intervals_client as api
                activities = api.get_activities(
                    start=date.today() - timedelta(days=42), end=date.today())
                profile = build_athlete_profile(activities=activities)
                print(f"  Profiel uit intervals.icu: CTL {profile.current_ctl}, "
                      f"{profile.recent_run_km_avg} km/wk, "
                      f"{profile.recent_run_sessions} sessies")
            except Exception as e:
                print(f"  intervals.icu niet beschikbaar ({e}) — seed-profiel.")

        result = generate_plan(goal, profile, PLAN_START)
        n = persist_plan_weeks(goal.id, result.weeks)
        print(f"  {n} plan_weeks gepersisteerd "
              f"(piek {result.peak_km:.0f} km, "
              f"piek-CTL-projectie {max(result.ctl_projection):.0f}).")
        for w in result.warnings:
            print(f"  warning: {w}")

    plan_provider.print_full_plan()


if __name__ == "__main__":
    main()
