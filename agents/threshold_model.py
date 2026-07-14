"""Threshold pace model.

Observations and suggestions never mutate threshold pace. Only manual set
and accepting a suggestion write the athlete-state value and audit log.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import history_db
from agents.feedback_engine import (
    ATHLETE_THRESHOLD_PACE_DEFAULT_SEC,
    THRESHOLD_HR_MAX,
    THRESHOLD_HR_MIN,
    get_athlete_threshold_pace_sec,
)


MIN_THRESHOLD_SEC = 220
MAX_THRESHOLD_SEC = 320
WORKOUT_COOLDOWN_DAYS = 14
TREND_WINDOW_DAYS = 28
TREND_WINDOW_SIZE = 4
TREND_MIN_OBSERVATIONS = 3
RACE_ANCHOR_FACTORS = {
    5000: 1.065,
    10000: 1.03,
    21097: 0.985,
    21100: 0.985,
}


def get_threshold_pace() -> int:
    return _clamp(get_athlete_threshold_pace_sec())


def set_threshold_pace(sec: int, reason: str, source: str = "manual") -> dict:
    old = get_threshold_pace()
    new = _clamp(sec)
    from shared import load_state, save_state

    state = load_state() or {}
    state["threshold_pace_sec_per_km"] = new
    save_state(state)
    return history_db.insert_threshold_pace_log(
        date=date.today().isoformat(),
        old_sec=old,
        new_sec=new,
        reason=reason,
        source=source,
    )


def record_observation(analysis: dict[str, Any], rpe: int | None = None) -> dict:
    """Persist one threshold observation. Idempotent on activity_id."""
    activity_id = analysis.get("activity_id") or analysis.get("id")
    if not activity_id:
        activity = analysis.get("activity") or {}
        activity_id = activity.get("id")
    if not activity_id:
        raise ValueError("activity_id ontbreekt")

    obs_date = (
        analysis.get("date")
        or (analysis.get("activity") or {}).get("start_date_local", "")[:10]
        or date.today().isoformat()
    )
    metrics = analysis.get("metrics") or {}
    pace_delta = analysis.get("pace_delta_sec", metrics.get("pace_delta_sec"))
    hr = analysis.get("hr_reps_avg", metrics.get("hr_reps_avg"))
    # Een onbetrouwbare meting is erger dan geen meting: hij ziet eruit als een
    # feit. Band op None => de trend leunt op pace en RPE (zie _is_*_signal).
    hr_reliable = analysis.get("hr_reliable", metrics.get("hr_reliable", True))
    hr_vs_band = analysis.get("hr_vs_band") or _hr_vs_band(hr)
    if not hr_reliable:
        hr_vs_band = None
    completed = bool(analysis.get("completed", True))
    clean_rpe = _clean_rpe(rpe if rpe is not None else analysis.get("rpe"))
    target = analysis.get("target_pace_sec", metrics.get("target_pace_sec"))
    observed = analysis.get("observed_pace_sec", metrics.get("observed_pace_sec"))

    return history_db.insert_threshold_observation(
        date=obs_date,
        activity_id=str(activity_id),
        pace_delta_sec=pace_delta,
        hr_reps_avg=hr,
        hr_vs_band=hr_vs_band,
        rpe=clean_rpe,
        completed=completed,
        target_pace_sec=int(target) if target is not None else None,
        observed_pace_sec=int(observed) if observed is not None else None,
    )


def is_threshold_workout(event: dict, analysis: dict) -> bool:
    """Alleen echte drempelsessies voeden het dossier — geen VO2max of MP."""
    if event.get("type") != "Run":
        return False
    name = (event.get("name") or "").lower()
    return analysis.get("workout_type") == "run_tempo" or "drempel" in name


def observe_from_workout(event: dict, activity: dict, analysis: dict) -> dict | None:
    """Gedeelde ingang voor élk feedback-pad (API én nachtelijke auto_feedback).

    Legt de observatie vast en toetst daarna de trend. Faalt stil: feedback
    geven mag nooit stuklopen op het drempeldossier.
    """
    try:
        if not is_threshold_workout(event, analysis):
            return None
        activity_id = str(activity.get("id") or "")
        if not activity_id:
            return None

        metrics = analysis.get("metrics") or {}
        rpe_row = get_rpe(activity_id)
        observation = record_observation(
            {
                "activity_id": activity_id,
                "date": (activity.get("start_date_local") or "")[:10],
                "pace_delta_sec": metrics.get("pace_delta_sec"),
                "hr_reps_avg": metrics.get("interval_hr_avg") or metrics.get("hr_avg"),
                "target_pace_sec": metrics.get("target_pace_sec"),
                "observed_pace_sec": metrics.get("observed_pace_sec"),
                "hr_reliable": metrics.get("hr_reliable", True),
                "completed": True,
            },
            rpe=(rpe_row or {}).get("rpe"),
        )
        evaluate_trend()
        return observation
    except Exception:
        return None


def evaluate_trend(today: date | None = None) -> dict | None:
    today = today or date.today()
    if history_db.get_pending_threshold_suggestion():
        return None
    if _in_workout_cooldown(today):
        return None

    since = (today - timedelta(days=TREND_WINDOW_DAYS)).isoformat()
    observations = history_db.list_threshold_observations(
        since=since,
        limit=TREND_WINDOW_SIZE,
    )
    if len(observations) < TREND_MIN_OBSERVATIONS:
        return None

    faster = [o for o in observations if _is_faster_signal(o)]
    faster_missing_rpe = sum(1 for o in faster if o.get("rpe") is None)
    if len(faster) >= TREND_MIN_OBSERVATIONS and faster_missing_rpe <= 1:
        old = get_threshold_pace()
        proposed = _clamp(old - 3)
        reason = _trend_reason(
            faster,
            f"{len(faster)} van laatste {len(observations)} drempelsessies "
            "sneller dan target bij HR onder/in band en lage RPE",
        )
        return history_db.insert_threshold_suggestion(
            date=today.isoformat(),
            old_sec=old,
            proposed_sec=proposed,
            reason=reason,
            source="workout_trend",
        )

    slower = [o for o in observations if _is_slower_signal(o)]
    if len(slower) >= TREND_MIN_OBSERVATIONS:
        old = get_threshold_pace()
        proposed = _clamp(old + 3)
        reason = _trend_reason(
            slower,
            f"{len(slower)} van laatste {len(observations)} drempelsessies "
            "trager/afgebroken met HR boven de drempelband",
        )
        return history_db.insert_threshold_suggestion(
            date=today.isoformat(),
            old_sec=old,
            proposed_sec=proposed,
            reason=reason,
            source="workout_trend",
        )

    return None


def suggest_from_race(distance_m: int, time_sec: int, today: date | None = None) -> dict | None:
    if history_db.get_pending_threshold_suggestion():
        return None
    today = today or date.today()
    factor = _race_factor(distance_m)
    race_pace = time_sec / (distance_m / 1000)
    proposed = _clamp(round(race_pace * factor))
    old = get_threshold_pace()
    reason = (
        f"Race-anker {distance_m/1000:g} km in {_time_label(time_sec)}: "
        f"racepace {_pace_label(round(race_pace))}/km x {factor:g} "
        f"-> voorstel drempel {_pace_label(proposed)}/km."
    )
    return history_db.insert_threshold_suggestion(
        date=today.isoformat(),
        old_sec=old,
        proposed_sec=proposed,
        reason=reason,
        source="race",
    )


def resolve_suggestion(suggestion_id: int, accepted: bool) -> dict:
    suggestion = history_db.get_threshold_suggestion(suggestion_id)
    if not suggestion:
        raise ValueError(f"suggestie {suggestion_id} bestaat niet")
    if suggestion.get("status") != "pending":
        return suggestion

    status = "accepted" if accepted else "dismissed"
    changed = accepted and int(suggestion["proposed_sec"]) != get_threshold_pace()
    if accepted:
        set_threshold_pace(
            int(suggestion["proposed_sec"]),
            suggestion.get("reason") or "suggestie geaccepteerd",
            suggestion.get("source") or "suggestion",
        )
    history_db.resolve_threshold_suggestion(suggestion_id, status)
    history_db.clear_threshold_observations()
    resolved = history_db.get_threshold_suggestion(suggestion_id) or suggestion
    # Workouts dragen absolute paces die op plan-moment zijn berekend, dus na
    # een geaccepteerde wijziging staat het huidige plan op de oude drempel.
    resolved["replan_needed"] = bool(changed)
    return resolved


def pending_suggestion() -> dict | None:
    return history_db.get_pending_threshold_suggestion()


def threshold_summary() -> dict:
    return {
        "threshold_pace_sec_per_km": get_threshold_pace(),
        "default_sec_per_km": ATHLETE_THRESHOLD_PACE_DEFAULT_SEC,
        "log": history_db.list_threshold_pace_log(),
        "suggestion": pending_suggestion(),
    }


def threshold_dossier(limit: int = 24) -> dict:
    observations = list(reversed(history_db.list_threshold_observations(limit=limit)))
    logs = history_db.list_threshold_pace_log()
    return {
        **threshold_summary(),
        "log": logs,
        "observations": observations,
        "context": threshold_context(),
    }


def threshold_context() -> dict:
    observations = history_db.list_threshold_observations(limit=TREND_WINDOW_SIZE)
    faster = [o for o in observations if _is_faster_signal(o)]
    slower = [o for o in observations if _is_slower_signal(o)]
    suggestion = pending_suggestion()
    pace = _pace_label(get_threshold_pace())

    if suggestion:
        sentence = (
            f"Open drempelvoorstel: {_pace_label(suggestion['old_sec'])}/km "
            f"naar {_pace_label(suggestion['proposed_sec'])}/km. "
            f"Reden: {suggestion['reason']}"
        )
    elif len(observations) < TREND_MIN_OBSERVATIONS:
        sentence = (
            f"Drempelpace staat op {pace}/km. "
            f"{len(observations)} recente observatie(s); minimaal "
            f"{TREND_MIN_OBSERVATIONS} nodig voor een voorstel."
        )
    elif len(faster) >= TREND_MIN_OBSERVATIONS:
        sentence = (
            f"{len(faster)} van laatste {len(observations)} drempelsessies "
            "zijn sneller-signalen, maar er is nu geen open voorstel "
            "(cooldown of eerdere beslissing kan gelden)."
        )
    elif len(slower) >= TREND_MIN_OBSERVATIONS:
        sentence = (
            f"{len(slower)} van laatste {len(observations)} drempelsessies "
            "zijn trager/HR-boven signalen, maar er is nu geen open voorstel "
            "(cooldown of eerdere beslissing kan gelden)."
        )
    else:
        sentence = (
            f"Drempelpace staat op {pace}/km. Laatste "
            f"{len(observations)} observaties zijn gemengd; geen voorstel."
        )

    return {
        "sentence": sentence,
        "recent_observations": list(reversed(observations)),
        "faster_count": len(faster),
        "slower_count": len(slower),
        "required_count": TREND_MIN_OBSERVATIONS,
        "window_size": TREND_WINDOW_SIZE,
        "window_days": TREND_WINDOW_DAYS,
    }


def record_rpe(activity_id: str, rpe: int, obs_date: str | None = None) -> dict:
    """Sla de RPE op en vul een reeds bestaande observatie aan.

    De observatie wordt bij de feedback-run vastgelegd, meestal vóórdat de
    atleet zijn RPE invult. Zonder deze backfill blijft die rij RPE-loos en
    kan de sneller-trend (die RPE <= 7 eist) nooit vuren.
    """
    clean = _clean_rpe(rpe)
    if clean is None:
        raise ValueError("rpe moet 1..10 zijn")
    row = history_db.upsert_workout_rpe(
        str(activity_id),
        clean,
        obs_date or date.today().isoformat(),
    )
    if history_db.set_observation_rpe(str(activity_id), clean):
        evaluate_trend()
    return row


def get_rpe(activity_id: str) -> dict | None:
    return history_db.get_workout_rpe(str(activity_id))


def _race_factor(distance_m: int) -> float:
    if distance_m in RACE_ANCHOR_FACTORS:
        return RACE_ANCHOR_FACTORS[distance_m]
    nearest = min(RACE_ANCHOR_FACTORS, key=lambda d: abs(d - distance_m))
    return RACE_ANCHOR_FACTORS[nearest]


def _in_workout_cooldown(today: date) -> bool:
    latest = history_db.latest_threshold_resolution()
    if not latest:
        return False
    resolved_at = (latest.get("resolved_at") or latest.get("date") or "")[:10]
    try:
        resolved_date = date.fromisoformat(resolved_at)
    except ValueError:
        return False
    return today < resolved_date + timedelta(days=WORKOUT_COOLDOWN_DAYS)


def _is_faster_signal(obs: dict) -> bool:
    rpe = obs.get("rpe")
    if obs.get("pace_delta_sec") is None or float(obs["pace_delta_sec"]) > -3:
        return False
    if obs.get("hr_vs_band") is None:
        # Onbruikbare HR (polsmeting): pace alleen is te dun, want sneller
        # lopen zegt niets zolang je niet weet wat het kostte. RPE neemt de
        # rol van de hartslag over en is dan verplicht.
        return rpe is not None and int(rpe) <= 7
    return (
        obs.get("hr_vs_band") in {"onder", "in"}
        and (rpe is None or int(rpe) <= 7)
    )


def _is_slower_signal(obs: dict) -> bool:
    rpe = obs.get("rpe")
    failed = not bool(obs.get("completed", 1))
    slow = obs.get("pace_delta_sec") is not None and float(obs["pace_delta_sec"]) >= 5
    if not (slow or failed):
        return False
    if obs.get("hr_vs_band") is None:
        return rpe is not None and int(rpe) >= 8
    return obs.get("hr_vs_band") == "boven"


def _hr_vs_band(hr: Any) -> str | None:
    if hr is None:
        return None
    hr = float(hr)
    if hr < THRESHOLD_HR_MIN:
        return "onder"
    if hr > THRESHOLD_HR_MAX:
        return "boven"
    return "in"


def _clean_rpe(raw: Any) -> int | None:
    if raw is None:
        return None
    value = int(raw)
    if not 1 <= value <= 10:
        return None
    return value


def _trend_reason(observations: list[dict], prefix: str) -> str:
    deltas = [round(float(o["pace_delta_sec"])) for o in observations
              if o.get("pace_delta_sec") is not None]
    rpes = [o.get("rpe") for o in observations if o.get("rpe") is not None]
    return (
        f"{prefix}: pace-delta's {deltas}s/km, "
        f"RPE {rpes or 'onbekend'} -> drempelpace aanpassen als voorstel."
    )


def _clamp(sec: int) -> int:
    return max(MIN_THRESHOLD_SEC, min(MAX_THRESHOLD_SEC, int(sec)))


def _pace_label(sec: int) -> str:
    minutes, seconds = divmod(int(round(sec)), 60)
    return f"{minutes}:{seconds:02d}"


def _time_label(sec: int) -> str:
    hours, rem = divmod(int(sec), 3600)
    minutes, seconds = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"
