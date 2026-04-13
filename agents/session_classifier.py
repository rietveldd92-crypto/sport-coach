"""Session classifier — sacred vs soft.

Sacred workouts MUST be rescheduled when skipped. Soft workouts may be absorbed silently.

Pure function `is_sacred(workout) -> bool`. No I/O, no side effects.
"""
from __future__ import annotations

from typing import Any

# Keywords die in een workout-naam of -type voorkomen en het sacred maken.
_SACRED_KEYWORDS_BIKE = {
    "threshold",
    "sweetspot",
    "sweet_spot",
    "cp",
    "critical_power",
    "vo2",
}
_SACRED_KEYWORDS_RUN = {
    "long",
    "lange",
    "duurloop",
    "drempel",
    "marathon_tempo",
    "tempo_duurloop",
    "tempo duurloop",
    "threshold",
}

# Keywords die het expliciet SOFT maken (override).
_SOFT_KEYWORDS = {
    "recovery",
    "herstel",
    "easy_spin",
    "easy spin",
    "fatmax",
    "strides",
    "long_slow",
    "z1",
    "z2",
}


def _lower(s: Any) -> str:
    return (str(s) if s is not None else "").lower()


def is_sacred(workout: dict[str, Any]) -> bool:
    """Return True als een geplande sessie als sacred aangemerkt moet worden.

    Input is een event-dict of een normalized workout-dict. Herkent velden:
    - type (intervals.icu sport type: Run, Ride, VirtualRide, ...)
    - name
    - description
    - load_target (TSS)
    - workout_type / wtype (interne tag, bv. run_long, bike_threshold)
    - duration_min / moving_time
    """
    if not workout:
        return False

    sport = _lower(workout.get("type"))
    name = _lower(workout.get("name"))
    desc = _lower(workout.get("description"))
    wtype = _lower(workout.get("workout_type") or workout.get("wtype"))
    blob = f"{name} {desc} {wtype}"

    # Soft wint — expliciet easy markeren kan niet sacred zijn
    if any(k in blob for k in _SOFT_KEYWORDS):
        return False

    # Bike sacred
    if sport in ("ride", "virtualride"):
        if any(k in blob for k in _SACRED_KEYWORDS_BIKE):
            return True
        return False

    # Run sacred
    if sport == "run":
        if any(k in blob for k in _SACRED_KEYWORDS_RUN):
            return True
        # duur-regel: run > 80 min telt als long run
        dur_min = workout.get("duration_min")
        if dur_min is None:
            moving = workout.get("moving_time") or 0
            dur_min = moving / 60 if moving else 0
        try:
            if float(dur_min) > 80:
                return True
        except (TypeError, ValueError):
            pass
        return False

    return False
