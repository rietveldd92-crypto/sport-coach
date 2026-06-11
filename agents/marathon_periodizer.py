"""Marathon Periodizer — DEPRECATED dunne re-export van core.plan_provider.

Sinds Fase 2 (UPGRADE_PLAN §4) komt het macroplan uit de parametrische
generator (core/periodization_generator.py) en leeft het in de
``plan_weeks``-tabel van het actieve A-doel (core/goal_engine.py).

De hardcoded tabellen (RUN_PROGRESSION_TABLE, WEEKLY_TSS_TABLE, PHASES)
zijn verwijderd nadat tests/test_periodization_snapshot.py bewees dat de
generator het onderhandelde plan ±10% reproduceert; de oude tabellen leven
daar voort als regressie-fixture.

Nieuwe code hoort core.plan_provider (of de generator) direct te
importeren; deze module bestaat alleen zodat bestaande imports
(load_manager, endurance_coach, bike_coach, plan_week, evaluate_week,
app.py) ongewijzigd blijven werken.
"""
from __future__ import annotations

from core.plan_provider import (  # noqa: F401
    PLAN_START,
    RACE_DATE,
    WeeklyPlanProxy,
    WeeklyTssTableProxy,
    calculate_weekly_run_volume,
    get_current_phase,
    get_run_intensiteit_gating,
    get_week_number,
    get_weekly_plan,
    get_weekly_tss_table,
    print_full_plan,
)

# Module-level "tabellen" zijn nu lazy views op het actieve macroplan —
# load_manager indexeert/membership-checkt deze alsof het de oude
# list/dict zijn, maar krijgt altijd de verse DB-stand.
WEEKLY_PLAN = WeeklyPlanProxy()
WEEKLY_TSS_TABLE = WeeklyTssTableProxy()


if __name__ == "__main__":
    print_full_plan()

    print("\n=== Huidige fase ===")
    phase = get_current_phase()
    for k, v in phase.items():
        print(f"  {k}: {v}")

    print("\n=== Volume deze week ===")
    vol = calculate_weekly_run_volume(phase["week_nummer"])
    for k, v in vol.items():
        print(f"  {k}: {v}")
