"""Dry-run van de blokplanner naast wat er nu in intervals.icu staat.

Schrijft niets. Weken worden in volgorde gepland; of er op de zondag vóór
een week gelopen wordt, komt voor latere weken uit de planner-uitvoer van
de week ervoor (niet uit de kalender), zodat de keten klopt.

    python scripts/compare_block_plan.py 2026-11-09 2026-12-07
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import intervals_client as api  # noqa: E402
import plan_week  # noqa: E402
from agents import block_library, block_planner  # noqa: E402
from core import goal_engine, plan_provider  # noqa: E402

DAYS = ["ma", "di", "wo", "do", "vr", "za", "zo"]


def _calendar(week_start: date) -> dict[int, list[str]]:
    out: dict[int, list[str]] = {}
    for e in api.get_events(week_start, week_start + timedelta(days=6)) or []:
        if e.get("category") not in ("WORKOUT", "RACE_A", "RACE_B", "RACE_C"):
            continue
        idx = (date.fromisoformat(e["start_date_local"][:10]) - week_start).days
        tss = e.get("icu_training_load")
        out.setdefault(idx, []).append(f"{e.get('name')}" + (f" ({tss})" if tss else ""))
    return out


def main() -> None:
    first = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date(2026, 11, 9)
    last = date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else date(2026, 12, 7)
    goal = goal_engine.get_active_goal()
    goals = [goal, *goal_engine.get_intermediate_goals(goal)]
    state = plan_week._load_state() or {}
    anchors = block_library.load_anchors(state)
    print(f"Doel: {goal.type} {goal.event_date} ({goal.target_value}); ankers: drempel "
          f"{block_library.pace(anchors.threshold_sec)}, vVO2 {block_library.pace(anchors.vvo2_sec)}, "
          f"AeT {block_library.pace(anchors.aet_sec)} {anchors.bronnen}")

    _, plan_weeks = plan_provider.get_active_plan()
    gate_by_week = {w.week_start: w.intensity_gate for w in plan_weeks}

    prev_sunday_run = None
    week = first
    while week <= last:
        ctx = plan_week.block_context(
            week, goal, ftp=290, macro_gate=gate_by_week.get(week, "drempel"),
            prev_week_sunday_run=prev_sunday_run,
        )
        availability = ctx.availability
        sessions, warnings = block_planner.plan_block_week(ctx, anchors)
        cal = _calendar(week)
        tss_new = sum(s.get("tss_geschat") or 0 for s in sessions)
        print(f"\n=== Week {week} — patroon {ctx.run_count} runs, gate {block_planner.block_gate(ctx)}, "
              f"macro-gate {ctx.macro_gate}{', HERSTELWEEK' if ctx.recovery_week else ''}, races {[r.naam for r in ctx.races]} ===")
        print(f"    beschikbaarheid: {availability}")
        for i in range(7):
            mine = [f"{s['naam']} ({s['tss_geschat']})" for s in sessions if s["dag"] == block_planner.DAYS_NL[i]]
            print(f"  {DAYS[i]}  PLANNER: {' + '.join(mine) or '-'}")
            print(f"      HANDMATIG: {' + '.join(cal.get(i, [])) or '-'}")
        print(f"  TSS planner {tss_new}")
        for w in warnings:
            print(f"  ! {w['message']}")
        prev_sunday_run = any(s["dag"] == "zondag" and s["sport"] == "Run" for s in sessions) or any(
            r.datum == week + timedelta(days=6) for r in ctx.races)
        week += timedelta(days=7)


if __name__ == "__main__":
    main()
