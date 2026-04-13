"""
plan_week.py — Orchestrator: plan de komende week in intervals.icu.

Gebruik:
    python plan_week.py              # Dry run (print alleen, schrijft niets)
    python plan_week.py --schrijf    # Schrijft workouts naar intervals.icu
    python plan_week.py --status     # Toon huidige status zonder te plannen
    python plan_week.py --week 2026-03-23  # Plan specifieke week (maandag)
"""

import sys
import json
import argparse
from datetime import date, timedelta
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import intervals_client as api
from agents import injury_guard, load_manager, endurance_coach, bike_coach, week_planner
from agents import marathon_periodizer

STATE_PATH = Path(__file__).parent / "state.json"


def _next_monday(from_date: date = None) -> date:
    """Geeft de maandag van de komende week."""
    if from_date is None:
        from_date = date.today()
    days_ahead = 7 - from_date.weekday()
    if days_ahead == 7:
        days_ahead = 0
    return from_date + timedelta(days=days_ahead)


def _load_state() -> dict:
    with open(STATE_PATH) as f:
        return json.load(f)


def print_status():
    """Print huidige coach-status zonder iets te plannen."""
    print("\n" + "=" * 60)
    print("  AMSTERDAM MARATHON COACH — HUIDIGE STATUS")
    print("=" * 60)

    # Marathon Periodizer
    phase_info = marathon_periodizer.get_current_phase()
    vol = marathon_periodizer.calculate_weekly_run_volume(phase_info["week_nummer"])
    print(f"\n  Race:          Amsterdam Marathon — 18 oktober 2026")
    print(f"  Fase:          {phase_info['fase_label']} (week {phase_info['week_nummer']})")
    print(f"  Weken tot race:{phase_info['weeks_to_race']}")
    print(f"  Loopvolume:    {vol['run_km_totaal']:.1f} km/week ({vol['run_sessies']} sessies)")
    if vol['lange_duurloop_km'] > 0:
        print(f"  Lange duurloop:{vol['lange_duurloop_km']:.0f} km")

    # Injury Guard
    ig = injury_guard.analyze()
    print(f"\n  Injury Guard:  {ig['status'].upper()}")
    print(f"  {ig['message']}")
    print(f"  Symptoomvrij:  {ig['days_symptom_free']} dagen")
    print(f"  Strides:       {'JA' if ig['strides_allowed'] else 'NEE'}")
    print(f"  Tempolopen:    {'JA' if ig['tempo_allowed'] else 'NEE'}")

    # Load Manager
    lm = load_manager.analyze()
    print(f"\n  CTL (fitheid): {lm['ctl']}")
    print(f"  ATL (moeheid): {lm['atl']}")
    print(f"  TSB (vorm):    {lm['tsb']:+.1f}")
    print(f"  Weekdoel TSS:  {lm['recommended_weekly_tss']}")
    print(f"  Overtraining:  {lm['overtraining_risk']}")

    print("\n" + "=" * 60 + "\n")


def run(week_start: date, dry_run: bool = True, skip_run_days: list = None):
    """
    Voer de volledige planningscyclus uit.

    1. Haal data op uit intervals.icu (activiteiten, wellness, FTP)
    2. Draai Injury Guard
    3. Draai Load Manager
    4. Genereer run-sessies (Endurance Coach)
    5. Genereer bike-sessies (Bike Coach)
    6. Laat Week Planner het schema bouwen en (optioneel) schrijven
    """
    print(f"\n  Starttdatum week: {week_start} (maandag)")
    print("  Data ophalen uit intervals.icu...")

    # ── 1. DATA OPHALEN ──────────────────────────────────────────────────────
    try:
        athlete = api.get_athlete()
        athlete_name = athlete.get("name", "Onbekend")
    except Exception as e:
        print(f"  ⚠️  Kan athlete data niet ophalen: {e}.")
        athlete_name = "Onbekend"

    try:
        activities = api.get_activities(
            start=date.today() - timedelta(days=42),
            end=date.today()
        )
        print(f"  {len(activities)} activiteiten geladen (42 dagen).")
    except Exception as e:
        print(f"  ⚠️  Activiteiten niet beschikbaar: {e}")
        activities = []

    # FTP: haal icu_ftp op uit meest recente fietsactiviteit met vermogen
    ftp = 250
    for act in activities:
        if act.get("type") in ("VirtualRide", "Ride") and act.get("icu_ftp"):
            ftp = act["icu_ftp"]
            break
    print(f"  Atleet: {athlete_name} | FTP: {ftp}W (icu_ftp)")

    try:
        wellness = api.get_wellness(
            start=date.today() - timedelta(days=14),
            end=date.today()
        )
        print(f"  {len(wellness)} wellness records geladen.")
    except Exception as e:
        print(f"  ⚠️  Wellness niet beschikbaar: {e}")
        wellness = []

    # ── 1b. MARATHON PERIODIZER ─────────────────────────────────────────────
    phase_info = marathon_periodizer.get_current_phase(today=week_start)
    marathon_vol = marathon_periodizer.calculate_weekly_run_volume(phase_info["week_nummer"])
    print(f"\n  Marathon fase:  {phase_info['fase_label']} (week {phase_info['week_nummer']}, "
          f"wk {phase_info['week_in_fase']} in fase)")
    print(f"  Loopvolume:     {marathon_vol['run_km_totaal']:.1f} km "
          f"({marathon_vol['run_sessies']} sessies, "
          f"lange duurloop: {marathon_vol['lange_duurloop_km']:.0f} km)")
    print(f"  Weken tot race: {phase_info['weeks_to_race']}")

    # ── 2. INJURY GUARD ──────────────────────────────────────────────────────
    ig_result = injury_guard.analyze(
        wellness_data=wellness,
        activities=activities,
    )

    # ── 3. LOAD MANAGER ──────────────────────────────────────────────────────
    lm_result = load_manager.analyze(
        activities=activities,
        injury_guard_output=ig_result,
    )

    phase = lm_result["current_phase"]

    # Geef deload flag door via ig_result zodat endurance_coach het ziet
    if lm_result.get("is_deload_week"):
        ig_result["_is_deload_week"] = True
        print(f"  ** DELOAD WEEK ** — volume -28% op alles")

    # ── 4. ENDURANCE COACH ───────────────────────────────────────────────────
    run_sessions = endurance_coach.plan_sessions(
        phase=phase,
        injury_guard=ig_result,
        load_manager=lm_result,
        week_start=week_start,
        skip_run_days=skip_run_days or [],
        marathon_volume=marathon_vol,
    )

    # Bereken hoeveel run-TSS verloren ging door blessure-modifier
    ig_full = {"status": "groen", "run_intensity_allowed": False, "strides_allowed": False,
               "tempo_allowed": False, "bike_intensity_allowed": True,
               "strength_allowed": True, "volume_modifier": 1.0}
    run_sessions_full = endurance_coach.plan_sessions(
        phase, ig_full, lm_result, week_start, marathon_volume=marathon_vol)
    full_run_tss = sum(s.get("tss_geschat", 0) for s in run_sessions_full)
    actual_run_tss = sum(s.get("tss_geschat", 0) for s in run_sessions)
    run_tss_lost = max(0, full_run_tss - actual_run_tss)

    # ── 5. BIKE COACH ────────────────────────────────────────────────────────
    bike_sessions = bike_coach.plan_sessions(
        phase=phase,
        injury_guard=ig_result,
        load_manager=lm_result,
        week_start=week_start,
        ftp=ftp,
        run_tss_lost=run_tss_lost,
        skip_run_days=skip_run_days or [],
        marathon_volume=marathon_vol,
    )

    # ── 6. WEEK PLANNER ──────────────────────────────────────────────────────
    events = week_planner.build_week(
        week_start=week_start,
        run_sessions=run_sessions,
        bike_sessions=bike_sessions,
        injury_guard=ig_result,
        load_manager=lm_result,
        dry_run=dry_run,
    )

    # Update weeklog in state
    state = _load_state()
    workout_tss = sum(
        e.get("tss") or 0
        for e in events
        if isinstance(e, dict) and e.get("categorie") == "WORKOUT"
    )
    state["weekly_log"].append({
        "week_start": week_start.isoformat(),
        "fase": phase,
        "planned_tss": lm_result["recommended_weekly_tss"],
        "geschat_tss": workout_tss,
        "actual_tss": None,
        "injury_status": ig_result["status"],
        "notes": ig_result["message"],
    })
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=4, ensure_ascii=False)

    return events


def _this_monday(from_date: date = None) -> date:
    """Maandag van de huidige kalenderweek."""
    if from_date is None:
        from_date = date.today()
    return from_date - timedelta(days=from_date.weekday())


def _week_has_workouts(week_start: date) -> bool:
    """Check via intervals.icu of een week al workout-events heeft."""
    try:
        events = api.get_events(start=week_start, end=week_start + timedelta(days=6))
        return any(e.get("category") == "WORKOUT" for e in events)
    except Exception as e:
        print(f"  ⚠️  Kon events niet ophalen voor {week_start}: {e} — skip (safe default)")
        return True  # bij twijfel skippen, overschrijf nooit bestaand plan


def run_horizon(horizon: int, write: bool, skip_run_days: list = None):
    """
    Rolling horizon: plan N weken vooruit (vanaf de huidige maandag).
    Skip weken die al workouts hebben.
    Active week krijgt --schrijf alleen als >=48u tot maandag.
    """
    today_monday = _this_monday()
    for i in range(horizon):
        wk = today_monday + timedelta(weeks=i)

        if _week_has_workouts(wk):
            print(f"\n  [horizon] Week {wk} heeft al workouts in intervals.icu — skip.")
            continue

        # Active week: als we nu IN die week zitten (i==0)
        is_active_week = (i == 0)
        effective_write = write
        if is_active_week:
            hours_to_next_monday = ((wk + timedelta(days=7)) - date.today()).days * 24
            if hours_to_next_monday < 48:
                if write:
                    print(f"\n  [horizon] Active week {wk}: <48u tot volgende maandag — "
                          f"dry-run forceren (warn).")
                effective_write = False

        print(f"\n  [horizon] Plannen week {wk} (schrijf={effective_write})")
        run(wk, dry_run=not effective_write, skip_run_days=skip_run_days or [])


def main():
    parser = argparse.ArgumentParser(description="Sport Coach — week inplannen")
    parser.add_argument("--schrijf", action="store_true",
                        help="Schrijf workouts naar intervals.icu (zonder dit: dry run)")
    parser.add_argument("--status", action="store_true",
                        help="Toon huidige status en stop")
    parser.add_argument("--week", type=str, default=None,
                        help="Maandag van de te plannen week (YYYY-MM-DD). Standaard: komende maandag.")
    parser.add_argument("--horizon", type=int, default=None,
                        help="Rolling horizon: plan N weken vooruit vanaf deze maandag. "
                             "Skipt weken die al workouts hebben.")
    parser.add_argument("--geen-run-maandag", action="store_true",
                        help="Sla de maandag-run over (verplaatst naar woensdag)")
    args = parser.parse_args()

    if args.status:
        print_status()
        return

    skip_run_days = ["maandag"] if args.geen_run_maandag else []

    if args.horizon is not None and args.horizon > 0:
        run_horizon(args.horizon, write=args.schrijf, skip_run_days=skip_run_days)
        return

    if args.week:
        try:
            week_start = date.fromisoformat(args.week)
            if week_start.weekday() != 0:
                print(f"  ⚠️  {args.week} is geen maandag. Gebruik een maandag als startdatum.")
                sys.exit(1)
        except ValueError:
            print(f"  ⚠️  Ongeldige datum: {args.week}. Gebruik format YYYY-MM-DD.")
            sys.exit(1)
    else:
        week_start = _next_monday()

    dry_run = not args.schrijf

    run(week_start, dry_run=dry_run, skip_run_days=skip_run_days)


if __name__ == "__main__":
    main()
