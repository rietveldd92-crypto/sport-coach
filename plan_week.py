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
DAYS_NL = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"]


def _next_monday(from_date: date = None) -> date:
    """Geeft de maandag van de komende week."""
    if from_date is None:
        from_date = date.today()
    days_ahead = 7 - from_date.weekday()
    if days_ahead == 7:
        days_ahead = 0
    return from_date + timedelta(days=days_ahead)


def _load_state() -> dict:
    from shared import load_state
    return load_state()


def _planner_v3_inputs(week_start: date) -> tuple[dict, list[dict], dict[str, int]]:
    """Load prefs, fixed sessions and availability for the V3 pure planner."""
    from core import availability_v2 as av2
    import history_db

    state = _load_state() or {}
    prefs = dict(state.get("preferences") or {})
    prefs.setdefault("progression", state.get("progression") or {})
    fixed_sessions = history_db.list_fixed_sessions()
    slots = av2.get_slots_for_week(week_start)
    availability = {
        DAYS_NL[i]: sum(
            slot.duration_min
            for slot in slots.get(week_start + timedelta(days=i), [])
        )
        for i in range(7)
    }
    # Een racedag is bezet: de race is de sessie. Zonder dit zet de assigner
    # er gewoon een geplande run of rit bovenop, want hij ziet alleen
    # beschikbaarheid — niet de kalender.
    from agents import availability as _av
    for dag in _av.get_race_day_names(week_start):
        availability[dag] = 0
    return prefs, fixed_sessions, availability


def _active_block_goal():
    """Het actieve A-doel als het een blokdoel (10k/5k/half) is, anders None."""
    try:
        from agents.block_planner import BLOCK_GOAL_TYPES
        from core import goal_engine

        goal = goal_engine.get_active_goal()
    except Exception:
        return None
    if goal is not None and goal.type in BLOCK_GOAL_TYPES:
        return goal
    return None


_RACE_PRIORITY = {"RACE_A": "A", "RACE_B": "B", "RACE_C": "C"}


def _race_distance_km(event: dict, goal=None) -> float:
    import re
    from agents.block_planner import GOAL_DISTANCE_KM

    if goal is not None and goal.type in GOAL_DISTANCE_KM:
        return GOAL_DISTANCE_KM[goal.type]
    meters = event.get("distance") or 0
    if meters:
        return round(float(meters) / 1000, 1)
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:km|k\b)", (event.get("name") or "").lower())
    return float(m.group(1).replace(",", ".")) if m else 10.0


def _goal_on(goals: list, day: date):
    return next((g for g in goals if g.event_date == day), None)


def _races_in_week(week_start: date, goals: list) -> list:
    """RACE_A/B/C-events uit intervals.icu, verrijkt met doel-prioriteit en racepace."""
    from agents.block_planner import Race, race_pace_for

    try:
        events = api.get_events(week_start, week_start + timedelta(days=6))
    except Exception:
        return []
    races = []
    for e in events or []:
        prio = _RACE_PRIORITY.get(str(e.get("category") or ""))
        if not prio:
            continue
        day = date.fromisoformat(str(e.get("start_date_local"))[:10])
        if any(r.datum == day for r in races):
            continue
        goal = _goal_on(goals, day)
        km = _race_distance_km(e, goal)
        races.append(Race(
            datum=day,
            naam=e.get("name") or "race",
            distance_km=km,
            priority=goal.priority if goal else prio,
            race_pace_sec=race_pace_for(goal.type, goal.target_value, km) if goal else None,
        ))
    return races


def _next_ab_race(week_start: date, goals: list):
    from agents.block_planner import GOAL_DISTANCE_KM, Race, race_pace_for

    upcoming = sorted(
        (g for g in goals if g.priority in ("A", "B") and g.event_date >= week_start),
        key=lambda g: g.event_date,
    )
    if not upcoming:
        return None
    g = upcoming[0]
    km = GOAL_DISTANCE_KM.get(g.type, 10.0)
    return Race(datum=g.event_date, naam=f"{g.type} {g.event_date:%d-%m}", distance_km=km,
                priority=g.priority, race_pace_sec=race_pace_for(g.type, g.target_value, km))


def _ran_on(day: date) -> bool:
    """Staat er op ``day`` een (geplande of gelopen) run?"""
    try:
        for e in api.get_events(day, day) or []:
            if (e.get("type") or "").lower() == "run" and e.get("category") != "NOTE":
                return True
        for a in api.get_activities(day, day) or []:
            if (a.get("type") or "").lower() == "run":
                return True
    except Exception:
        pass
    return False


def block_context(week_start: date, goal, *, ftp: int, macro_gate: str,
                  is_deload: bool = False, intensity_open: bool = True,
                  prev_week_sunday_run: bool | None = None):
    """Bouw de BlockWeekContext voor ``week_start`` (ook gebruikt door de
    dry-run-vergelijking in scripts/compare_block_plan.py)."""
    from agents import block_planner
    from core import goal_engine

    prefs, _fixed, availability = _planner_v3_inputs(week_start)
    pattern = prefs.get("run_pattern") or {}
    goals = [goal, *goal_engine.get_intermediate_goals(goal)]
    # Ook afgesloten A/B-doelen tellen: de race van vorige week maakt deze
    # week een herstelweek, ook als iemand het doel al op completed zette.
    ab_dates = sorted(
        g.event_date for g in goal_engine.list_goals()
        if g.priority in ("A", "B") and g.status != "abandoned"
    )
    last_ab = max((d for d in ab_dates if d < week_start), default=None)
    start = block_planner.effective_block_start(prefs.get("block_start"), last_ab)
    if prev_week_sunday_run is None:
        prev_week_sunday_run = _ran_on(week_start - timedelta(days=1))
    return block_planner.BlockWeekContext(
        week_start=week_start,
        goal_type=goal.type,
        run_count=block_planner.run_count_for_week(week_start, pattern),
        availability=availability,
        ftp=ftp,
        macro_gate=macro_gate,
        steps=block_planner.block_steps(week_start, prefs.get("block_start"), is_deload, last_ab),
        variety=max(0, (week_start - start).days // 7) if start else 0,
        races=_races_in_week(week_start, goals),
        next_race=_next_ab_race(week_start, goals),
        is_deload=is_deload,
        intensity_open=intensity_open,
        prev_week_sunday_run=prev_week_sunday_run,
        next_week_run_count=block_planner.run_count_for_week(week_start + timedelta(days=7), pattern),
        runs_back_to_back_ok=bool(prefs.get("runs_back_to_back_ok", False)),
        recovery_week=last_ab is not None and (week_start - last_ab).days <= 7,
    )


def _plan_block_week(week_start: date, goal, ig_result: dict, lm_result: dict,
                     ftp: int, macro_gate: str):
    """PLANLOGICA-V4: weekplan voor een 10k/5k/half-blok."""
    from agents import block_library, block_planner

    state = _load_state() or {}
    ctx = block_context(
        week_start, goal, ftp=ftp, macro_gate=macro_gate,
        is_deload=bool(lm_result.get("is_deload_week")),
        intensity_open=bool(ig_result.get("run_intensity_allowed")) and bool(ig_result.get("tempo_allowed")),
    )
    anchors = block_library.load_anchors(state)
    sessions, warnings = block_planner.plan_block_week(ctx, anchors)
    print(f"  Blokplanner ({goal.type}): {ctx.run_count} runs-patroon, gate "
          f"{block_planner.block_gate(ctx)}, {len(ctx.races)} race(s) deze week"
          f"{', HERSTELWEEK na race' if ctx.recovery_week else ''}.")
    print(f"  Ankers: drempel {block_library.pace(anchors.threshold_sec)}, "
          f"vVO2 {block_library.pace(anchors.vvo2_sec)} ({anchors.bronnen['vvo2']}), "
          f"AeT {block_library.pace(anchors.aet_sec)} ({anchors.bronnen['aet']}).")
    return sessions, warnings


def _planner_v3_warning(warning: dict) -> dict:
    return {
        "tier": warning.get("tier", 2),
        "code": warning.get("code", "planner_v3_warning"),
        "dag": warning.get("dag"),
        "sessie": warning.get("sessie"),
        "message": warning.get("message", ""),
    }


def _record_week_log(
    events: list[dict],
    week_start: date,
    phase: str,
    lm_result: dict,
    ig_result: dict,
) -> list[dict]:
    if not events:
        return events

    state = _load_state()
    workout_tss = sum(
        e.get("tss") or 0
        for e in events
        if isinstance(e, dict) and e.get("categorie") == "WORKOUT"
    )
    new_entry = {
        "week_start": week_start.isoformat(),
        "fase": phase,
        "planned_tss": lm_result["recommended_weekly_tss"],
        "geschat_tss": workout_tss,
        "actual_tss": None,
        "injury_status": ig_result["status"],
        "notes": ig_result["message"],
    }
    log = state.setdefault("weekly_log", [])
    for i, existing in enumerate(log):
        if existing.get("week_start") == new_entry["week_start"]:
            if existing.get("actual_tss") is not None:
                new_entry["actual_tss"] = existing["actual_tss"]
            log[i] = new_entry
            break
    else:
        log.append(new_entry)
    from shared import save_state
    save_state(state)
    return events


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
    # Beschikbaarheid: dagen met 0 min ingesteld = rustdagen.
    # Expliciete skip_run_days in de call hebben voorrang; lege lijst/None
    # betekent "laat availability beslissen".
    if not skip_run_days:
        try:
            from agents import availability as _av
            _rest = _av.get_rest_day_names(week_start)
            if _rest:
                skip_run_days = _rest
                print(f"  Beschikbaarheid: {len(_rest)} rustdag(en) — {', '.join(_rest)}")
        except Exception as _e:
            print(f"  Beschikbaarheid niet geladen: {_e}")

    # Racedagen komen er altijd bij, ook als de caller expliciet
    # skip_run_days meegaf: op een racedag plan je niets bovenop.
    try:
        from agents import availability as _av
        _races = _av.get_race_day_names(week_start)
        if _races:
            skip_run_days = list(dict.fromkeys((skip_run_days or []) + _races))
            print(f"  Race deze week: {', '.join(_races)} — dag geblokkeerd.")
    except Exception as _e:
        print(f"  Racedagen niet geladen: {_e}")

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
        week_start=week_start,
    )

    phase = lm_result["current_phase"]

    # Geef deload flag door via ig_result zodat endurance_coach het ziet
    if lm_result.get("is_deload_week"):
        ig_result["_is_deload_week"] = True
        print(f"  ** DELOAD WEEK ** — volume -28% op alles")

    # ── 4. ENDURANCE COACH ───────────────────────────────────────────────────
    from core import planner_v3_enabled

    block_goal = _active_block_goal() if planner_v3_enabled() else None
    if block_goal is not None:
        placed_sessions, block_warnings = _plan_block_week(
            week_start, block_goal, ig_result, lm_result, ftp,
            marathon_vol.get("intensity_gate") or "drempel",
        )
        events = week_planner.build_week(
            week_start=week_start,
            run_sessions=[s for s in placed_sessions if (s.get("sport") or "").lower() == "run"],
            bike_sessions=[s for s in placed_sessions if (s.get("sport") or "").lower() != "run"],
            injury_guard=ig_result,
            load_manager=lm_result,
            dry_run=dry_run,
            preplanned=True,
            planner_warnings=[_planner_v3_warning(w) for w in block_warnings],
        )
        return _record_week_log(events, week_start, phase, lm_result, ig_result)

    if planner_v3_enabled():
        from agents.day_assigner import assign_days
        from agents.week_skeleton import build_skeleton_with_warnings

        prefs, fixed_sessions, availability = _planner_v3_inputs(week_start)
        skeleton, skeleton_warnings = build_skeleton_with_warnings(
            phase_info["week_nummer"],
            marathon_vol,
            ig_result,
            lm_result,
            prefs,
            fixed_sessions,
        )
        placed_sessions, assigner_warnings = assign_days(
            skeleton,
            availability,
            runs_back_to_back_ok=bool(prefs.get("runs_back_to_back_ok", False)),
            week_start=week_start,
        )
        planner_warnings = [
            _planner_v3_warning(w)
            for w in [*skeleton_warnings, *assigner_warnings]
        ]
        print(
            f"  Planner V3: {len(placed_sessions)} sessies uit geraamte geplaatst "
            f"({len(planner_warnings)} waarschuwing(en))."
        )
        run_sessions = [
            s for s in placed_sessions
            if (s.get("sport") or "").lower() == "run"
        ]
        bike_sessions = [
            s for s in placed_sessions
            if (s.get("sport") or "").lower() != "run"
        ]
        events = week_planner.build_week(
            week_start=week_start,
            run_sessions=run_sessions,
            bike_sessions=bike_sessions,
            injury_guard=ig_result,
            load_manager=lm_result,
            dry_run=dry_run,
            preplanned=True,
            planner_warnings=planner_warnings,
        )
        return _record_week_log(events, week_start, phase, lm_result, ig_result)

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

    # ── 4b. VOLUME-COMPENSATIE ───────────────────────────────────────────────
    # Als je vandaag meer hebt gelopen dan gepland, cap resterende runs deze
    # week zodat je niet in het totaal-volume overshoot.
    try:
        from agents import volume_compensation as _vc
        _activities_wk = api.get_activities(
            start=week_start, end=week_start + timedelta(days=6),
        )
        run_sessions, _vc_info = _vc.apply(
            week_start=week_start,
            sessions=run_sessions,
            activities=_activities_wk,
        )
        if _vc_info.get("capped"):
            print(f"  Volume-compensatie: overshoot {_vc_info['overshoot_km']}km → "
                  f"{len(_vc_info['capped'])} run(s) ingekort")
            for c in _vc_info["capped"]:
                print(f"    {c['datum']} '{c['naam']}': {c['van_km']}km → {c['naar_km']}km")
    except Exception as _vc_exc:
        print(f"  Volume-compensatie overgeslagen: {_vc_exc}")

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

    # Update weeklog in state — vervang bestaande entry voor deze week-start
    # i.p.v. appenden, anders verzamelt elke replan-run een dubbele log-regel.
    if not events:
        return events

    state = _load_state()
    workout_tss = sum(
        e.get("tss") or 0
        for e in events
        if isinstance(e, dict) and e.get("categorie") == "WORKOUT"
    )
    new_entry = {
        "week_start": week_start.isoformat(),
        "fase": phase,
        "planned_tss": lm_result["recommended_weekly_tss"],
        "geschat_tss": workout_tss,
        "actual_tss": None,
        "injury_status": ig_result["status"],
        "notes": ig_result["message"],
    }
    log = state.setdefault("weekly_log", [])
    for i, existing in enumerate(log):
        if existing.get("week_start") == new_entry["week_start"]:
            # Behoud actual_tss als die al is ingevuld door evaluate_week.
            if existing.get("actual_tss") is not None:
                new_entry["actual_tss"] = existing["actual_tss"]
            log[i] = new_entry
            break
    else:
        log.append(new_entry)
    from shared import save_state
    save_state(state)

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
    parser.add_argument("--vastzetten", action="store_true",
                        help="Zet de week vast: de planner (en de zondag-scheduler) "
                             "laten hem met rust tot je hem ontgrendelt.")
    parser.add_argument("--ontgrendel", action="store_true",
                        help="Haal de week-lock weg zodat er weer gepland mag worden.")
    parser.add_argument("--reden", type=str, default="",
                        help="Toelichting bij --vastzetten (komt in de kalendernotitie).")
    args = parser.parse_args()

    if args.status:
        print_status()
        return

    skip_run_days = ["maandag"] if args.geen_run_maandag else []

    # Lock-vlaggen en planvlaggen sluiten elkaar uit. Zonder deze check slikte
    # --horizon de --vastzetten stil op (horizon returnt eerder), en dan start
    # de planner terwijl je juist vroeg om níet te plannen — met --schrijf erbij
    # is dat precies de overschrijving die de lock moet voorkomen.
    if args.vastzetten and args.ontgrendel:
        print("  ⚠️  --vastzetten en --ontgrendel gaan niet samen.")
        sys.exit(1)
    if args.vastzetten or args.ontgrendel:
        conflicterend = [
            naam for naam, actief in (
                ("--horizon", args.horizon is not None and args.horizon > 0),
                ("--schrijf", args.schrijf),
                ("--geen-run-maandag", args.geen_run_maandag),
            ) if actief
        ]
        if conflicterend:
            print(f"  ⚠️  {', '.join(conflicterend)} kan niet samen met "
                  "--vastzetten/--ontgrendel: dat zijn planacties en de "
                  "lock-vlaggen zijn er juist om planning te blokkeren.")
            sys.exit(1)

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

    if args.vastzetten or args.ontgrendel:
        from agents import week_lock

        if args.ontgrendel:
            if week_lock.unlock_week(week_start):
                print(f"  Week {week_start} ontgrendeld — de planner mag hem weer vullen.")
            else:
                print(f"  Week {week_start} was niet vastgezet.")
        else:
            week_lock.lock_week(week_start, args.reden)
            print(f"  🔒 Week {week_start} vastgezet.")
            if args.reden:
                print(f"     Reden: {args.reden}")
        return

    dry_run = not args.schrijf

    run(week_start, dry_run=dry_run, skip_run_days=skip_run_days)


if __name__ == "__main__":
    main()
