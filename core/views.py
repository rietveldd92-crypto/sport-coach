"""Read-model assemblage voor de FastAPI-laag (Fase 3, UPGRADE_PLAN §7).

Routers blijven dun: zij doen alleen Pydantic-validatie en roepen deze
functies aan. Alle intervals.icu-I/O en samenstellen van today/week/
season/trends-views gebeurt hier, met dezelfde bouwstenen als app.py
(shared.match_events_activities, history_db, availability_v2, ...).

intervals.icu-fouten worden vertaald naar :class:`IntervalsUnavailable`;
api/main.py mapt die exception naar een nette HTTP 502.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Iterator, Optional

import history_db
import shared


class IntervalsUnavailable(Exception):
    """intervals.icu is niet bereikbaar (of gaf een fout)."""


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


# ── WEEK-DATA ─────────────────────────────────────────────────────────────

def fetch_week_bundle(week_start: date) -> tuple[list, list, list]:
    """(events, activities, matched) voor één week.

    Events-fout → IntervalsUnavailable; activities-fout → lege lijst
    (zelfde tolerantie als app.py's fetch_week).
    """
    import intervals_client as api

    week_end = week_start + timedelta(days=6)
    try:
        try:
            events = api.get_events(week_start, week_end, resolve=True)
        except TypeError:  # oude signature zonder resolve
            events = api.get_events(week_start, week_end)
    except Exception as exc:
        raise IntervalsUnavailable(f"events ophalen faalde: {exc}") from exc
    try:
        activities = api.get_activities(start=week_start, end=week_end)
    except Exception:
        activities = []
    matched = shared.match_events_activities(events, activities)
    return events, activities, matched


def pick_today_item(matched: list, today: date) -> Optional[dict]:
    """Workout van vandaag: eerst niet-voltooid, anders de voltooide.

    (Zelfde selectie als de Today-hero in app.py.)
    """
    today_str = today.isoformat()
    for want_done in (False, True):
        for item in matched:
            if item.get("is_note"):
                continue
            e_date = item["event"].get("start_date_local", "")[:10]
            if e_date == today_str and item["done"] == want_done:
                return item
    return None


def _event_summary(item: dict) -> dict:
    """Compacte JSON-weergave van één matched-item."""
    event = item["event"]
    activity = item.get("activity")
    eid = str(event.get("id", ""))
    placement = history_db.get_placement(eid) if eid else None
    return {
        "event": event,
        "activity": activity,
        "done": bool(item.get("done")),
        "is_note": bool(item.get("is_note")),
        "unplanned": bool(item.get("_unplanned")),
        "placement": placement,
    }


def today_view(today: Optional[date] = None) -> dict:
    """GET /api/today — workout vandaag + checkin-status + morgen-preview."""
    from agents.workout_feel import get_feel_note

    today = today or date.today()
    tomorrow = today + timedelta(days=1)
    monday = _monday(today)
    # Week + morgen (morgen kan in de volgende week vallen — zondag).
    _, _, matched = fetch_week_bundle(monday)
    if tomorrow > monday + timedelta(days=6):
        _, _, matched_next = fetch_week_bundle(monday + timedelta(days=7))
        matched = matched + matched_next

    item = pick_today_item(matched, today)
    workout = None
    if item is not None:
        workout = _event_summary(item)
        workout["coach_note"] = get_feel_note(item["event"])

    tomorrow_str = tomorrow.isoformat()
    tomorrow_preview = [
        _event_summary(i) for i in matched
        if not i.get("is_note")
        and i["event"].get("start_date_local", "")[:10] == tomorrow_str
    ]

    checkin = history_db.get_wellness(today)
    score = history_db.morning_checkin_score(today)
    state = shared.load_state() or {}
    tsb = float(state.get("load", {}).get("tsb_estimate", 0) or 0)
    recovery = history_db.compute_recovery_score(checkin, tsb)

    # Injury-guard-status voor de header-badge (Fase 4 Today-scherm).
    # analyze() zonder signalen = status-refresh (buffer-decay, geen
    # nieuwe history-entries); fouten zijn hier geen showstopper.
    injury = None
    try:
        from agents import injury_guard

        guard = injury_guard.analyze()
        injury = {
            "status": guard.get("status"),
            "message": guard.get("message"),
            "active_signals": guard.get("active_signals") or [],
            "days_symptom_free": guard.get("days_symptom_free"),
        }
    except Exception:
        pass

    return {
        "date": today.isoformat(),
        "workout": workout,
        "checkin": {
            "done": checkin is not None,
            "score": score,
            "record": checkin,
            "recovery": recovery,
        },
        "injury_guard": injury,
        "tomorrow": tomorrow_preview,
    }


def week_view(week_start: date) -> dict:
    """GET /api/week/{week_start} — matched events + placements + slots."""
    from core import availability_v2 as av2

    week_start = _monday(week_start)
    week_end = week_start + timedelta(days=6)
    _, _, matched = fetch_week_bundle(week_start)

    placements = history_db.get_placements(week_start.isoformat(),
                                           week_end.isoformat())
    slots = av2.get_slots_for_week(week_start)
    availability = {
        d.isoformat(): [
            {"start": s.start, "end": s.end, "context": s.context}
            for s in day_slots
        ]
        for d, day_slots in slots.items()
    }

    return {
        "week_start": week_start.isoformat(),
        "items": [_event_summary(i) for i in matched],
        "placements": placements,
        "availability": availability,
    }


def plan_week(week_start: date) -> dict:
    """POST /api/week/{week_start}/plan — bestaande plan-flow + solver."""
    import plan_week as planner

    week_start = _monday(week_start)
    events = planner.run(week_start, dry_run=False)
    # week_planner returnt bij schrijven de intervals.icu-responses
    # ("category"); bij dry-run de interne dicts ("categorie").
    workouts = [
        e for e in (events or [])
        if isinstance(e, dict)
        and (e.get("category") or e.get("categorie")) == "WORKOUT"
    ]
    warnings = []
    try:
        from shared import load_state

        last = (load_state() or {}).get("last_plan_warnings") or {}
        if last.get("week_start") == week_start.isoformat():
            warnings = last.get("warnings") or []
    except Exception:
        warnings = []
    return {
        "week_start": week_start.isoformat(),
        "planned_sessions": len(workouts),
        "events": events,
        "warnings": warnings,
    }


# ── EVENT LOOKUP ──────────────────────────────────────────────────────────

def find_event(event_id: str, *, resolve: bool = False,
               days_back: int = 7, days_ahead: int = 14) -> Optional[dict]:
    """Zoek één event op id in het venster [vandaag-back, vandaag+ahead]."""
    import intervals_client as api

    today = date.today()
    try:
        try:
            events = api.get_events(today - timedelta(days=days_back),
                                    today + timedelta(days=days_ahead),
                                    resolve=resolve)
        except TypeError:
            events = api.get_events(today - timedelta(days=days_back),
                                    today + timedelta(days=days_ahead))
    except Exception as exc:
        raise IntervalsUnavailable(f"events ophalen faalde: {exc}") from exc
    return next(
        (e for e in events if str(e.get("id")) == str(event_id)), None)


def swap_event(event_id: str, category: str) -> dict:
    """POST /api/placements/{event_id}/swap — gedeelde swap-flow."""
    from core import swap_service

    event = find_event(event_id)
    if event is None:
        raise LookupError(f"Event {event_id} niet gevonden in het zoekvenster")

    e_date_str = (event.get("start_date_local") or "")[:10]
    week_start = _monday(date.fromisoformat(e_date_str)) if e_date_str \
        else _monday(date.today())
    _, _, matched = fetch_week_bundle(week_start)

    state = shared.load_state() or {}
    weekly_target = state.get("load", {}).get("weekly_tss_target", 400)
    ideal_tss = swap_service.compute_ideal_tss(matched, event_id, weekly_target)
    phase_range = swap_service.resolve_phase_tss_range()

    return swap_service.perform_swap(
        event, category,
        ideal_tss=ideal_tss, matched=matched, phase_tss_range=phase_range,
    )


def move_placement(event_id: str, target_date: date, *,
                   apply: bool = False) -> dict:
    """POST /api/placements/{event_id}/move — solver-diff (+ optioneel apply)."""
    import intervals_client as api
    from core import replan

    week_start = _monday(target_date)
    week_end = week_start + timedelta(days=6)
    try:
        events = api.get_events(week_start, week_end)
    except Exception as exc:
        raise IntervalsUnavailable(f"events ophalen faalde: {exc}") from exc

    return replan.move_event(event_id, target_date, apply=apply, events=events)


# ── GOALS ─────────────────────────────────────────────────────────────────

def _recent_activities(days: int = 42) -> Optional[list]:
    """Activities van de laatste N dagen; None bij intervals-fout."""
    try:
        import intervals_client as api

        return api.get_activities(
            start=date.today() - timedelta(days=days), end=date.today())
    except Exception:
        return None


def create_goal_with_plan(data: dict) -> dict:
    """POST /api/goals — goal aanmaken + macroplan genereren/persisteren.

    Raises ValueError bij een tweede actief A-doel of een event_date
    in het verleden (router → 409).
    """
    from core import goal_engine
    from core.goal_engine import Goal
    from core.periodization_generator import (
        build_athlete_profile, generate_plan, persist_plan_weeks,
    )

    goal = goal_engine.create_goal(Goal(**data))

    generation = None
    if goal.priority == "A" and goal.status == "active":
        profile = build_athlete_profile(activities=_recent_activities())
        try:
            result = generate_plan(
                goal, profile, plan_start=_monday(date.today()),
                intermediate_goals=goal_engine.get_intermediate_goals(goal),
            )
        except ValueError:
            # Plan niet genereerbaar → goal niet half achterlaten.
            goal_engine.delete_goal(goal.id)
            raise
        persist_plan_weeks(goal.id, result.weeks)
        generation = {
            "plan_weeks": len(result.weeks),
            "warnings": result.warnings,
            "peak_km": result.peak_km,
        }

    return {"goal": goal.model_dump(mode="json"), "generation": generation}


def delete_goal(goal_id: int) -> None:
    """DELETE /api/goals/{id} — LookupError als het doel niet bestaat."""
    from core import goal_engine

    if goal_engine.get_goal(goal_id) is None:
        raise LookupError(f"Goal {goal_id} bestaat niet")
    goal_engine.delete_goal(goal_id)


def regenerate_goal(goal_id: int, force: bool = False) -> dict:
    """POST /api/goals/{id}/regenerate — rolling re-periodisatie (§4.2).

    ``force=True`` negeert de ±10%-uitvoeringsband — nodig om een net
    toegevoegd B/C-tussendoel (mini-taper) meteen in het macroplan te
    stansen zonder te wachten tot de uitvoering toevallig afwijkt.
    """
    from core import goal_engine
    from core.replan_goal import weekly_recalibration

    goal = goal_engine.get_goal(goal_id)
    if goal is None:
        raise LookupError(f"Goal {goal_id} bestaat niet")
    return weekly_recalibration(goal=goal, activities=_recent_activities(), force=force)


# ── SEASON / TRENDS ───────────────────────────────────────────────────────

def season_view(today: Optional[date] = None) -> dict:
    """GET /api/season — macroplan + CTL-paden + haalbaarheidsadvies."""
    import fitness_trend
    from core import goal_engine, plan_provider, replan_goal
    from core.periodization_generator import build_athlete_profile, project_ctl

    today = today or date.today()
    goal, weeks = plan_provider.get_active_plan()

    state = shared.load_state() or {}
    current_ctl = float(state.get("load", {}).get("ctl_estimate", 45.0) or 45.0)

    # Werkelijk CTL-pad — intervals.icu-fout is hier geen showstopper.
    ctl_actual: list[dict] = []
    try:
        import intervals_client as api

        activities = api.get_activities(
            start=today - timedelta(days=120), end=today)
        trend = fitness_trend.calculate_daily_trend(
            activities, seed_ctl=20, seed_atl=20)
        ctl_actual = [{"date": t["date"], "ctl": t["ctl"], "tsb": t["tsb"]}
                      for t in trend]
        if trend:
            current_ctl = trend[-1]["ctl"]
    except Exception:
        pass  # fallback: alleen state-CTL, geen curve

    this_monday = _monday(today)
    future = [w for w in weeks if w.week_start >= this_monday]
    ctl_path = project_ctl(current_ctl, [w.tss_target for w in future])
    ctl_target_path = [
        {"week_start": w.week_start.isoformat(), "ctl": round(c, 1)}
        for w, c in zip(future, ctl_path)
    ]

    profile = build_athlete_profile(state=state)
    profile.current_ctl = current_ctl
    advice = None
    try:
        advice = replan_goal._feasibility_advice(goal, profile, future)
    except Exception:
        pass
    advice = advice or "Op schema — doelpad haalbaar."

    return {
        "goal": goal.model_dump(mode="json"),
        "weeks_to_goal": goal_engine.weeks_to_goal(goal, today=today),
        "current_ctl": round(current_ctl, 1),
        "plan_weeks": [w.model_dump(mode="json") for w in weeks],
        "ctl_actual": ctl_actual,
        "ctl_target_path": ctl_target_path,
        "advice": advice,
    }


def trends_view(today: Optional[date] = None) -> dict:
    """GET /api/trends — ctl/atl/tsb-series, weekvolume, hrv."""
    import fitness_trend

    today = today or date.today()
    state = shared.load_state() or {}

    activities: list = []
    source = "state"
    try:
        import intervals_client as api

        activities = api.get_activities(
            start=today - timedelta(days=120), end=today)
        source = "intervals"
    except Exception:
        pass

    trend = fitness_trend.calculate_daily_trend(
        activities, seed_ctl=20, seed_atl=20) if activities else []

    # Weekvolume: km (run) + TSS + uren per weekstart.
    volume: dict[str, dict] = {}
    for act in activities:
        d_str = (act.get("start_date_local") or "")[:10]
        try:
            monday = _monday(date.fromisoformat(d_str)).isoformat()
        except ValueError:
            continue
        wk = volume.setdefault(
            monday, {"week_start": monday, "tss": 0.0, "run_km": 0.0,
                     "hours": 0.0})
        wk["tss"] += act.get("icu_training_load") or 0
        wk["hours"] += (act.get("moving_time") or 0) / 3600.0
        if act.get("type") == "Run":
            wk["run_km"] += (act.get("distance") or 0) / 1000.0
    weekly_volume = [
        {**wk, "tss": round(wk["tss"], 0), "run_km": round(wk["run_km"], 1),
         "hours": round(wk["hours"], 1)}
        for wk in sorted(volume.values(), key=lambda w: w["week_start"])
    ]

    hrv: list[dict] = []
    try:
        import intervals_client as api

        wellness = api.get_wellness(
            start=today - timedelta(days=42), end=today)
        hrv = [
            {"date": w.get("id"), "hrv": w.get("hrv"),
             "resting_hr": w.get("restingHR")}
            for w in (wellness or []) if w.get("hrv") is not None
        ]
    except Exception:
        pass

    # Athlete-snapshot (FTP/HRmax) + TP-koppeling voor het Jij-scherm.
    import config
    from core.periodization_generator import build_athlete_profile

    profile = build_athlete_profile(
        activities=activities or None, state=state)

    return {
        "source": source,
        "load": state.get("load", {}),
        "ctl_series": trend,
        "weekly_volume": weekly_volume,
        "hrv": hrv,
        "athlete": {"ftp": profile.ftp, "hrmax": profile.hrmax},
        "tp_sync_enabled": config.get_bool("TP_SYNC_ENABLED", default=False),
    }


# ── CHECKIN ───────────────────────────────────────────────────────────────

def process_checkin(
    *,
    sleep_score: Optional[int] = None,
    energy: Optional[int] = None,
    soreness: Optional[int] = None,
    motivation: Optional[int] = None,
    injury_signals: Optional[list[str]] = None,
    notes: Optional[str] = None,
    today: Optional[date] = None,
) -> dict:
    """POST /api/checkin — wellness naar history_db + injury_guard-flow.

    Vervangt het adjust.py-CLI-pad voor blessuresignalen: signalen gaan
    door exact dezelfde injury_guard.analyze()-buffer (direct vs buffered).
    """
    from agents import injury_guard

    today = today or date.today()
    history_db.record_wellness(
        today,
        sleep_score=sleep_score,
        energy=energy,
        soreness=soreness,
        motivation=motivation,
        notes=notes,
    )

    guard = injury_guard.analyze(feedback_signals=injury_signals or None)

    wellness = history_db.get_wellness(today)
    state = shared.load_state() or {}
    tsb = float(state.get("load", {}).get("tsb_estimate", 0) or 0)

    return {
        "date": today.isoformat(),
        "checkin_score": history_db.morning_checkin_score(today),
        "recovery": history_db.compute_recovery_score(wellness, tsb),
        "injury_guard": guard,
    }


def checkin_history(days: int = 14, today: Optional[date] = None) -> dict:
    """GET /api/checkin/history — wellness-records + blessuresignalen.

    Maakt de injury_guard-buffer transparant (UPGRADE_PLAN §6, Jij-scherm):
    per dag het checkin-record, plus de gemelde signalen uit de
    injury-history van de athlete-state.
    """
    today = today or date.today()
    cutoff = (today - timedelta(days=days)).isoformat()

    records = history_db.get_recent_wellness(days=days)
    for rec in records:
        vals = [rec.get(k) for k in
                ("sleep_score", "energy", "soreness", "motivation")]
        vals = [v for v in vals if v is not None]
        rec["checkin_score"] = (
            round(sum(vals) / len(vals), 2) if vals else None)

    state = shared.load_state() or {}
    signals = [
        h for h in (state.get("injury", {}) or {}).get("history", [])
        if str(h.get("date", "")) >= cutoff
    ]

    # Status-refresh via hetzelfde read-pad als today_view (analyze()
    # zonder signalen = buffer-decay, geen nieuwe history-entries).
    guard = None
    try:
        from agents import injury_guard

        result = injury_guard.analyze()
        guard = {
            "status": result.get("status"),
            "message": result.get("message"),
            "active_signals": result.get("active_signals") or [],
            "days_symptom_free": result.get("days_symptom_free"),
        }
    except Exception:
        pass

    return {
        "days": days,
        "records": records,
        "signals": signals,
        "injury_guard": guard,
    }


# ── COACH FEEDBACK (SSE) ──────────────────────────────────────────────────

def prepare_coach_feedback(event_id: str) -> dict:
    """Verzamel data + prompt voor de feedback-stream.

    Returns {"stream": True, prompt, model, analysis} als Gemini kan
    streamen, anders {"stream": False, text, fallback} (rule-based of
    'nog geen activiteit').

    Raises LookupError als het event niet bestaat in het zoekvenster.
    """
    import intervals_client as api
    from agents import feedback_engine

    today = date.today()
    start, end = today - timedelta(days=7), today + timedelta(days=7)
    try:
        events = api.get_events(start, end)
        activities = api.get_activities(start=start, end=today)
    except Exception as exc:
        raise IntervalsUnavailable(f"data ophalen faalde: {exc}") from exc

    matched = shared.match_events_activities(events, activities)
    item = next(
        (i for i in matched
         if str(i["event"].get("id")) == str(event_id)), None)
    if item is None:
        raise LookupError(f"Event {event_id} niet gevonden in het zoekvenster")

    event, activity = item["event"], item.get("activity")
    if not activity:
        return {"stream": False, "fallback": True,
                "text": "Nog geen voltooide activiteit voor dit event — "
                        "feedback volgt na de workout."}

    state = shared.load_state() or {}
    try:
        wellness = api.get_wellness(start=today - timedelta(days=14), end=today)
    except Exception:
        wellness = []
    try:
        recent_28d = api.get_activities(
            start=today - timedelta(days=28), end=today)
    except Exception:
        recent_28d = []

    prompt, model_name, analysis = feedback_engine.build_prompt(
        event, activity,
        state=state, wellness_records=wellness,
        week_events=matched, recent_28d=recent_28d,
    )

    if feedback_engine.gemini_available():
        return {"stream": True, "prompt": prompt, "model": model_name,
                "analysis": analysis}
    # Geen API-key → rule-based fallback, non-streaming (UPGRADE_PLAN §7).
    return {"stream": False, "fallback": True,
            "text": feedback_engine.rule_feedback(analysis),
            "analysis": analysis}


def coach_feedback_sse(data: dict) -> Iterator[str]:
    """SSE-generator over een prepare_coach_feedback()-resultaat."""
    from agents import feedback_engine

    if data.get("stream"):
        try:
            for chunk in feedback_engine.gemini_stream(
                    data["model"], data["prompt"]):
                yield f"data: {json.dumps({'text': chunk})}\n\n"
        except Exception as exc:
            fb = feedback_engine.rule_feedback(data.get("analysis") or {})
            yield ("data: " + json.dumps(
                {"text": fb, "fallback": True, "error": str(exc)}) + "\n\n")
    else:
        yield ("data: " + json.dumps(
            {"text": data.get("text", ""),
             "fallback": bool(data.get("fallback"))}) + "\n\n")
    yield "data: [DONE]\n\n"
