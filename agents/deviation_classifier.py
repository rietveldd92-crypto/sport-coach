"""Deviation classifier — match planned event vs actual activity, emit Deviation.

Pure function. No I/O, no side effects. Consumes already-matched
{event, activity} pairs (see shared.match_events_activities).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from .models import Deviation
from .session_classifier import is_sacred

# Tolerantie-drempels (verankerd in de design decisions in de sprint spec)
HARDER_TSS_RATIO = 1.3
EASIER_TSS_RATIO = 0.6
LONGER_DURATION_RATIO = 1.3
TSS_BAND = 0.30  # ±30% — "within tolerance"

# Severity drempels op basis van |tss_delta|
SEVERITY_MEDIUM_TSS = 30
SEVERITY_HIGH_TSS = 60


def _planned_tss(event: Optional[dict[str, Any]]) -> float:
    if not event:
        return 0.0
    return float(event.get("load_target") or event.get("icu_training_load") or 0) or 0.0


def _actual_tss(activity: Optional[dict[str, Any]]) -> float:
    if not activity:
        return 0.0
    return float(
        activity.get("icu_training_load")
        or activity.get("training_load")
        or 0
    ) or 0.0


def _duration_min(obj: Optional[dict[str, Any]]) -> float:
    if not obj:
        return 0.0
    # event uses duration (seconds) or moving_time; activity uses moving_time
    sec = obj.get("moving_time") or obj.get("duration") or 0
    try:
        return float(sec) / 60.0
    except (TypeError, ValueError):
        return 0.0


def _date_from(obj: Optional[dict[str, Any]]) -> Optional[date]:
    if not obj:
        return None
    raw = obj.get("start_date_local") or obj.get("start_date") or ""
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "")).date()
    except ValueError:
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            return None


def _severity(tss_delta: float) -> str:
    abs_d = abs(tss_delta)
    if abs_d >= SEVERITY_HIGH_TSS:
        return "high"
    if abs_d >= SEVERITY_MEDIUM_TSS:
        return "medium"
    return "low"


def classify_deviation(
    planned_event: Optional[dict[str, Any]],
    actual_activity: Optional[dict[str, Any]],
    today: Optional[date] = None,
) -> Optional[Deviation]:
    """Classificeer afwijking tussen één gepland event en één activiteit.

    Returns None als er noch planned noch actual is (niets te zeggen).
    Returns Deviation met type='none' als alles binnen tolerantie.
    """
    if not planned_event and not actual_activity:
        return None

    today = today or date.today()
    tss_planned = _planned_tss(planned_event)
    tss_actual = _actual_tss(actual_activity)
    sacred = is_sacred(planned_event) if planned_event else False
    planned_date = _date_from(planned_event)
    pdate_str = planned_date.isoformat() if planned_date else None
    event_id = str(planned_event.get("id")) if planned_event else None
    act_id = str(actual_activity.get("id")) if actual_activity else None
    tss_delta = tss_actual - tss_planned

    # Case: alleen actual (ongepland) → extra
    if not planned_event and actual_activity:
        return Deviation(
            type="extra",
            actual_activity_id=act_id,
            tss_planned=0.0,
            tss_actual=tss_actual,
            severity=_severity(tss_actual),
            note="Ongeplande activiteit",
        )

    # Case: alleen planned, geen activity
    if planned_event and not actual_activity:
        # Alleen telt als skipped als de geplande dag al voorbij is
        if planned_date is not None and planned_date < today:
            return Deviation(
                type="skipped",
                planned_event_id=event_id,
                tss_planned=tss_planned,
                tss_actual=0.0,
                severity=_severity(tss_planned),
                planned_date=pdate_str,
                sacred=sacred,
                note="Sessie gepland maar niet uitgevoerd",
            )
        # Future / today — geen deviation
        return None

    # Beide aanwezig
    if tss_planned > 0 and tss_actual > tss_planned * HARDER_TSS_RATIO:
        return Deviation(
            type="replaced_harder",
            planned_event_id=event_id,
            actual_activity_id=act_id,
            tss_planned=tss_planned,
            tss_actual=tss_actual,
            severity=_severity(tss_delta),
            planned_date=pdate_str,
            sacred=sacred,
            note=f"Uitgevoerd +{int(tss_delta)} TSS zwaarder dan gepland",
        )

    if tss_planned > 0 and tss_actual < tss_planned * EASIER_TSS_RATIO:
        return Deviation(
            type="replaced_easier",
            planned_event_id=event_id,
            actual_activity_id=act_id,
            tss_planned=tss_planned,
            tss_actual=tss_actual,
            severity=_severity(tss_delta),
            planned_date=pdate_str,
            sacred=sacred,
            note=f"Uitgevoerd {int(tss_delta)} TSS lichter dan gepland",
        )

    # Longer check: duur > 1.3x maar TSS binnen ±30%
    dp = _duration_min(planned_event)
    da = _duration_min(actual_activity)
    if dp > 0 and da > dp * LONGER_DURATION_RATIO:
        if tss_planned == 0 or abs(tss_delta) <= tss_planned * TSS_BAND:
            return Deviation(
                type="longer",
                planned_event_id=event_id,
                actual_activity_id=act_id,
                tss_planned=tss_planned,
                tss_actual=tss_actual,
                severity=_severity(tss_delta),
                planned_date=pdate_str,
                sacred=sacred,
                note=f"Duur +{int(da - dp)} min langer",
            )

    # Anders: none (geen afwijking)
    return Deviation(
        type="none",
        planned_event_id=event_id,
        actual_activity_id=act_id,
        tss_planned=tss_planned,
        tss_actual=tss_actual,
        severity="low",
        planned_date=pdate_str,
        sacred=sacred,
    )


def detect_deviations(
    events: list[dict[str, Any]],
    activities: list[dict[str, Any]],
    today: Optional[date] = None,
) -> list[Deviation]:
    """Detecteer alle deviations voor een week.

    Gebruikt dezelfde matching-logica als shared.match_events_activities,
    maar geeft een platte lijst Deviation terug (skipt type='none').
    """
    # Lokale import — shared.py staat op project-root, niet in agents/
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from shared import match_events_activities  # noqa: E402

    matched = match_events_activities(events or [], activities or [])
    out: list[Deviation] = []
    for pair in matched:
        ev = pair.get("event")
        act = pair.get("activity")
        # pseudo-events voor ongeplande activiteiten: behandel als extra
        if ev and ev.get("_unplanned"):
            ev = None
        dev = classify_deviation(ev, act, today=today)
        if dev and dev.type != "none":
            out.append(dev)
    return out
