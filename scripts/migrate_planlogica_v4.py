"""PLANLOGICA-V4 W1: doelen en blokvoorkeuren omzetten naar het 10k-seizoen.

Idempotent. Draai lokaal én tegen de prod-DB (Railway), anders lopen ze
uiteen (bekende valkuil: prod-DB != lokale DB).

    python scripts/migrate_planlogica_v4.py            # dry run: toont wat er gebeurt
    python scripts/migrate_planlogica_v4.py --schrijf  # voert het uit

Wat het doet:
1. Amsterdam (marathon 18-10-2026) en de Big 10 (5-9-2026) -> completed.
2. Nieuwe doelen: A = 10k Leiden (placeholder 30-05-2027, band 38:00-38:45),
   B = Bruggenloop 15 km 13-12-2026 (1:02:00), Schoorl 10k 14-2-2027,
   CPC 5k 14-3-2027, Rotterdam 10k 11-4-2027; C = parkrun 14-11-2026.
3. Voorkeuren: run_pattern 4-3 vanaf 2-11-2026, block_start 2-11-2026.
4. Macroplan voor het nieuwe A-doel genereren en persisteren.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import goal_engine  # noqa: E402
from core.goal_engine import Goal  # noqa: E402

BLOCK_START = date(2026, 11, 2)

AFSLUITEN = [("marathon", date(2026, 10, 18)), ("10k", date(2026, 9, 5))]

NIEUWE_DOELEN = [
    Goal(type="10k", sport="run", event_date=date(2027, 5, 30), target_value="38:00-38:45", priority="A"),
    Goal(type="15k", sport="run", event_date=date(2026, 12, 13), target_value="1:02:00", priority="B"),
    Goal(type="10k", sport="run", event_date=date(2027, 2, 14), target_value=None, priority="B"),
    Goal(type="5k", sport="run", event_date=date(2027, 3, 14), target_value=None, priority="B"),
    Goal(type="10k", sport="run", event_date=date(2027, 4, 11), target_value=None, priority="B"),
    Goal(type="5k", sport="run", event_date=date(2026, 11, 14), target_value="19:45", priority="C"),
]

PREFERENCES = {
    "run_pattern": {"counts": [4, 3], "start": BLOCK_START.isoformat()},
    "block_start": BLOCK_START.isoformat(),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--schrijf", action="store_true")
    args = parser.parse_args()
    write = args.schrijf
    tag = "" if write else "[dry run] "

    goals = goal_engine.list_goals()
    for gtype, day in AFSLUITEN:
        for g in goals:
            if g.type == gtype and g.event_date == day and g.status == "active":
                print(f"{tag}Afsluiten: {g.type} {g.event_date} (id={g.id})")
                if write:
                    goal_engine.update_goal(g.id, status="completed")

    goals = goal_engine.list_goals()
    for new in NIEUWE_DOELEN:
        if any(g.type == new.type and g.event_date == new.event_date and g.status == "active" for g in goals):
            print(f"Bestaat al: {new.priority} {new.type} {new.event_date}")
            continue
        print(f"{tag}Aanmaken: {new.priority} {new.type} {new.event_date} ({new.target_value})")
        if write:
            goal_engine.create_goal(new)

    import history_db
    state = history_db.get_athlete_state()
    prefs = dict(state.get("preferences") or {})
    prefs.update(PREFERENCES)
    print(f"{tag}Voorkeuren: {PREFERENCES}")
    if write:
        # Eén key upserten — nooit save_state() met een gedeeltelijk dict
        # (replace_athlete_state wist dan alle andere keys).
        history_db.set_athlete_state_value("preferences", prefs)

    if not write:
        return
    a_goal = goal_engine.get_active_goal()
    from core.periodization_generator import build_athlete_profile, generate_plan, persist_plan_weeks
    try:
        import intervals_client as api
        activities = api.get_activities(start=date.today() - timedelta(days=42), end=date.today())
        profile = build_athlete_profile(activities=activities)
    except Exception as exc:
        print(f"intervals.icu niet bereikbaar ({exc}) — standaardprofiel.")
        profile = build_athlete_profile(activities=[])
    result = generate_plan(a_goal, profile, BLOCK_START,
                           intermediate_goals=goal_engine.get_intermediate_goals(a_goal))
    n = persist_plan_weeks(a_goal.id, result.weeks)
    print(f"Macroplan: {n} weken voor {a_goal.type} {a_goal.event_date}.")
    for w in result.warnings:
        print(f"  warning: {w}")


if __name__ == "__main__":
    main()
