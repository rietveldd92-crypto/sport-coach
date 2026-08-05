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

# Drift = HR van de laatste rep min die van de eerste, bij vaste pace. Onder de
# drempel stabiliseert de hartslag en blijft dat verschil klein; erboven blijft
# hij klimmen omdat de inspanning nooit in steady-state komt. Alleen de uiteinden
# spreken: 4-7 bpm is grijs en levert bewust geen signaal, want daar is één
# sessie niet te onderscheiden van een warme dag of een slechte nacht.
DRIFT_FLAT_BPM = 3
DRIFT_HIGH_BPM = 8
# Drift telt alleen mee als de sessie ook op het voorgeschreven tempo liep.
# Vlakke hartslag op een pace die 10 s/km te traag was, zegt niets over de
# drempel die het plan probeerde te raken.
DRIFT_ON_TARGET_SEC = 3
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
    # Een drift-getal uit een onbruikbare hartslag is erger dan geen getal:
    # het voedt de trend met sensorruis. Zelfde afweging als bij hr_vs_band.
    drift = analysis.get("hr_drift_bpm", metrics.get("hr_drift_bpm"))
    if not hr_reliable:
        drift = None
    work_time = analysis.get("work_time_min", metrics.get("work_time_min"))

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
        hr_drift_bpm=float(drift) if drift is not None else None,
        work_time_min=int(work_time) if work_time is not None else None,
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
        rpe = (rpe_row or {}).get("rpe")
        if rpe is None:
            # Garmin schrijft zijn session-RPE mee als icu_rpe. Zonder deze
            # fallback blijft de observatie RPE-loos tot de atleet hem in de app
            # invult — en juist als de HR onbruikbaar is (polsmeting) eist de
            # sneller-trend een RPE, dus dan telt de observatie nooit mee.
            rpe = activity.get("icu_rpe")
        observation = record_observation(
            {
                "activity_id": activity_id,
                "date": (activity.get("start_date_local") or "")[:10],
                "pace_delta_sec": metrics.get("pace_delta_sec"),
                "hr_reps_avg": metrics.get("interval_hr_avg") or metrics.get("hr_avg"),
                "target_pace_sec": metrics.get("target_pace_sec"),
                "observed_pace_sec": metrics.get("observed_pace_sec"),
                "hr_drift_bpm": metrics.get("hr_drift_bpm"),
                "work_time_min": metrics.get("work_time_min"),
                "hr_reliable": metrics.get("hr_reliable", True),
                "completed": True,
            },
            rpe=rpe,
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

    # Opbouw op vaste pace laat de pace-delta per definitie stilstaan, dus de
    # regels hierboven kunnen nooit vuren. Drift is daar het enige bewegende
    # signaal: vlakke hartslag op target betekent dat de sessie binnen de
    # drempel is komen te liggen.
    flat = [o for o in observations if _is_flat_drift_signal(o)]
    if len(flat) >= TREND_MIN_OBSERVATIONS:
        old = get_threshold_pace()
        proposed = _clamp(old - 3)
        reason = _drift_reason(
            flat,
            f"{len(flat)} van laatste {len(observations)} drempelsessies op "
            f"target met vlakke hartslag (drift <= {DRIFT_FLAT_BPM} bpm)",
        )
        return history_db.insert_threshold_suggestion(
            date=today.isoformat(),
            old_sec=old,
            proposed_sec=proposed,
            reason=reason,
            source="drift_trend",
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

    # De spiegel: op target gelopen, maar de hartslag blijft elke sessie
    # doorklimmen. Dan lag de pace boven de drempel en is de sessie een
    # VO2max-prikkel met een drempel-etiket.
    climbing = [o for o in observations if _is_high_drift_signal(o)]
    if len(climbing) >= TREND_MIN_OBSERVATIONS:
        old = get_threshold_pace()
        proposed = _clamp(old + 3)
        reason = _drift_reason(
            climbing,
            f"{len(climbing)} van laatste {len(observations)} drempelsessies op "
            f"target met doorklimmende hartslag (drift >= {DRIFT_HIGH_BPM} bpm)",
        )
        return history_db.insert_threshold_suggestion(
            date=today.isoformat(),
            old_sec=old,
            proposed_sec=proposed,
            reason=reason,
            source="drift_trend",
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

    drift_series = [
        {"date": o.get("date"),
         "drift_bpm": o.get("hr_drift_bpm"),
         "work_time_min": o.get("work_time_min")}
        for o in reversed(observations)
        if o.get("hr_drift_bpm") is not None and _on_target(o)
    ]
    drift_sentence = _drift_sentence(drift_series)

    return {
        "sentence": sentence,
        "recent_observations": list(reversed(observations)),
        "faster_count": len(faster),
        "slower_count": len(slower),
        "flat_drift_count": len([o for o in observations
                                 if _is_flat_drift_signal(o)]),
        "high_drift_count": len([o for o in observations
                                 if _is_high_drift_signal(o)]),
        "drift_series": drift_series,
        "drift_sentence": drift_sentence,
        "drift_flat_bpm": DRIFT_FLAT_BPM,
        "drift_high_bpm": DRIFT_HIGH_BPM,
        "required_count": TREND_MIN_OBSERVATIONS,
        "window_size": TREND_WINDOW_SIZE,
        "window_days": TREND_WINDOW_DAYS,
    }


def _drift_sentence(series: list[dict]) -> str:
    """Beschrijf de hartslagdrift op target-pace, oudste eerst."""
    if not series:
        return ("Nog geen bruikbare driftmeting: die vraagt een drempelsessie "
                "op target met vlakke reps en een betrouwbare hartslag.")

    values = [round(float(row["drift_bpm"])) for row in series]
    listed = ", ".join(f"{v:+d}" for v in values)
    head = f"Drift op target-pace (oudste eerst): {listed} bpm."

    if len(values) < 2:
        return (f"{head} Eén meting zegt nog niets over een richting — "
                f"{TREND_MIN_OBSERVATIONS} nodig voor een voorstel.")

    change = values[-1] - values[0]
    if change <= -2:
        return (f"{head} De hartslag zakt bij gelijk tempo: de duurcapaciteit "
                "op drempel groeit.")
    if change >= 2:
        return (f"{head} De hartslag klimt bij gelijk tempo: de sessies kosten "
                "meer in plaats van minder.")
    return f"{head} Vlakke trend; nog geen richting."


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
    if not bool(obs.get("completed", 1)):
        return False
    # -3 s/km valt nog binnen de expliciete on-target-band (Â±3). Houd de
    # assen disjunct: pas strikt sneller dan die band is een pace-signaal.
    if obs.get("pace_delta_sec") is None or float(obs["pace_delta_sec"]) >= -3:
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


def _on_target(obs: dict) -> bool:
    """Liep deze sessie op het voorgeschreven tempo?

    Drift is alleen vergelijkbaar tussen sessies die hetzelfde probeerden.
    """
    delta = obs.get("pace_delta_sec")
    if delta is None:
        return False
    return abs(float(delta)) <= DRIFT_ON_TARGET_SEC


def _is_flat_drift_signal(obs: dict) -> bool:
    """Op target gelopen met een hartslag die zich vastzette."""
    drift = obs.get("hr_drift_bpm")
    if drift is None or not _on_target(obs):
        return False
    if not bool(obs.get("completed", 1)):
        return False
    if obs.get("hr_vs_band") not in {"onder", "in"}:
        # Vlak maar boven de band betekent niet dat er ruimte is; dan klopt de
        # band niet of ligt de pace nog steeds te hoog. Niet versnellen.
        return False
    rpe = obs.get("rpe")
    if rpe is not None and int(rpe) >= 8:
        # De hartslag zegt rustig, de atleet zegt zwaar. Bij die tegenspraak
        # wint de atleet — een drempel opschuiven die zwaar aanvoelt is precies
        # hoe je een blessure of een overtraind blok inkoopt.
        return False
    return float(drift) <= DRIFT_FLAT_BPM


def _is_high_drift_signal(obs: dict) -> bool:
    """Op target gelopen, maar de hartslag bleef klimmen."""
    drift = obs.get("hr_drift_bpm")
    if drift is None or not _on_target(obs):
        return False
    return float(drift) >= DRIFT_HIGH_BPM


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


def _drift_reason(observations: list[dict], prefix: str) -> str:
    drifts = [round(float(o["hr_drift_bpm"])) for o in observations
              if o.get("hr_drift_bpm") is not None]
    minutes = [o.get("work_time_min") for o in observations
               if o.get("work_time_min") is not None]
    tail = f", werktijd {minutes} min" if minutes else ""
    return (
        f"{prefix}: drift {drifts} bpm{tail} "
        "-> drempelpace aanpassen als voorstel."
    )


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
