"""Planner V3 week skeleton.

This module decides which sessions belong in a week. It does not choose
days, write to intervals.icu, or inspect availability.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agents import workout_library as lib
from agents.bike_coach import _tss_bike, fatmax_medium_session, long_slow_session
from agents.endurance_coach import DOUBLE_DREMPEL_START_WEEK


RUN_KM_CEILING_DEFAULT = 65.0
MIN_RUN_MIN = 45
EASY_RUN_KM = 8.0


@dataclass(frozen=True)
class SkeletonSlot:
    sessie: dict
    rol: str
    prioriteit: int
    vaste_dag: str | None = None


def build_skeleton(
    week_number: int,
    marathon_volume: dict,
    injury_guard: dict,
    load_manager: dict,
    prefs: dict | None,
    fixed_sessions: list[dict] | None,
) -> list[SkeletonSlot]:
    slots, _ = build_skeleton_with_warnings(
        week_number,
        marathon_volume,
        injury_guard,
        load_manager,
        prefs,
        fixed_sessions,
    )
    return slots


def build_skeleton_with_warnings(
    week_number: int,
    marathon_volume: dict,
    injury_guard: dict,
    load_manager: dict,
    prefs: dict | None,
    fixed_sessions: list[dict] | None,
) -> tuple[list[SkeletonSlot], list[dict]]:
    prefs = prefs or {}
    progression = prefs.get("progression") or {}
    warnings: list[dict] = []
    slots: list[SkeletonSlot] = []

    run_km_ceiling = float(prefs.get("run_km_ceiling", RUN_KM_CEILING_DEFAULT))
    fourth_run_gate_open = bool(prefs.get("fourth_run_gate_open", False))
    is_deload = bool(load_manager.get("is_deload_week") or injury_guard.get("_is_deload_week"))

    quality_step = int(progression.get("run_quality_step", _run_quality_step_for_week(week_number)))
    if is_deload:
        quality_step = max(1, quality_step - 1)
    quality_idx = int(progression.get("run_quality_variety_index", 0))
    long_idx = int(progression.get("long_run_variety_index", 0))
    z2_idx = int(progression.get("z2_run_variety_index", 0))

    run_intensity_ok = bool(injury_guard.get("run_intensity_allowed", False))
    tempo_ok = bool(injury_guard.get("tempo_allowed", False))
    intensity_open = run_intensity_ok and tempo_ok

    planned_run_km = 0.0
    interval_count = 1 if is_deload else 2
    if week_number < DOUBLE_DREMPEL_START_WEEK:
        interval_count = min(interval_count, 1)

    interval_a = _quality_or_easy(
        category="threshold_short",
        step=quality_step,
        variety_index=quality_idx + week_number,
        intensity_open=intensity_open,
        fallback_duration=_short_run_minutes(marathon_volume),
        z2_index=z2_idx,
    )
    slots.append(SkeletonSlot(interval_a, "interval_a", 1))
    planned_run_km += _estimate_run_km(interval_a, marathon_volume)

    if interval_count >= 2:
        interval_b = _quality_or_easy(
            category="threshold_long",
            step=quality_step,
            variety_index=quality_idx + week_number + 1,
            intensity_open=intensity_open,
            fallback_duration=_short_run_minutes(marathon_volume),
            z2_index=z2_idx + 1,
        )
        slots.append(SkeletonSlot(interval_b, "interval_b", 1))
        planned_run_km += _estimate_run_km(interval_b, marathon_volume)

    long_km = float(marathon_volume.get("lange_duurloop_km") or 0)
    if long_km > 0:
        remaining_for_long = max(0.0, run_km_ceiling - planned_run_km)
        if long_km > remaining_for_long:
            warnings.append({
                "code": "run_km_ceiling_long_capped",
                "message": (
                    f"Lange duurloop ingekort naar {remaining_for_long:.1f} km "
                    f"om onder {run_km_ceiling:.0f} km/week te blijven."
                ),
            })
            long_km = remaining_for_long
        if long_km > 0:
            long_run = lib.pick_long_run(long_km, long_idx)
            slots.append(SkeletonSlot(long_run, "long_run", 1))
            planned_run_km += long_km

    if fourth_run_gate_open:
        remaining = run_km_ceiling - planned_run_km
        if remaining >= EASY_RUN_KM:
            easy = lib.pick_z2_run(max(MIN_RUN_MIN, _km_to_minutes(EASY_RUN_KM)), z2_idx + 2)
            slots.append(SkeletonSlot(easy, "easy_run", 3))
            planned_run_km += EASY_RUN_KM
        else:
            warnings.append({
                "code": "easy_run_dropped_ceiling",
                "message": (
                    "Extra rustige loop vervalt: geen km-ruimte onder "
                    f"{run_km_ceiling:.0f} km/week."
                ),
            })

    slots.extend(_commute_slots(fixed_sessions or []))

    two_run_intervals = sum(1 for slot in slots if slot.rol.startswith("interval")) >= 2
    slots.extend(_bike_fill_slots(two_run_intervals=two_run_intervals))

    _mark_run_km(slots, planned_run_km, run_km_ceiling)
    return slots, warnings


def _quality_or_easy(
    *,
    category: str,
    step: int,
    variety_index: int,
    intensity_open: bool,
    fallback_duration: int,
    z2_index: int,
) -> dict:
    if intensity_open:
        return lib.pick_run_quality(step=step, variety_index=variety_index, category=category)
    return lib.pick_z2_run(max(MIN_RUN_MIN, fallback_duration), z2_index)


def _commute_slots(fixed_sessions: list[dict]) -> list[SkeletonSlot]:
    slots: list[SkeletonSlot] = []
    for item in fixed_sessions:
        if not item.get("enabled", True):
            continue
        weekday = item.get("weekday")
        vaste_dag = item.get("dag") or item.get("day")
        if vaste_dag is None and weekday is not None:
            vaste_dag = _day_name(int(weekday))
        duration = int(item.get("duration_min") or 100)
        if_estimate = float(item.get("if_estimate") or 0.65)
        sessie = {
            "type": "commute",
            "naam": item.get("name") or "Forenzen-rit",
            "beschrijving": "Vaste Z2 forenzen-rit. Telt mee voor het weekdoel.",
            "duur_min": duration,
            "tss_geschat": _tss_bike(duration, if_estimate),
            "sport": item.get("sport") or "VirtualRide",
            "zone": "Z2",
            "intensiteit_factor": if_estimate,
        }
        slots.append(SkeletonSlot(sessie, "commute", 2, vaste_dag=vaste_dag))
    return slots


def _bike_fill_slots(*, two_run_intervals: bool) -> list[SkeletonSlot]:
    builders = [long_slow_session, fatmax_medium_session, lib.endurance_ride]
    sessions = [
        builders[0](),
        builders[1](),
        builders[2](75),
    ]
    if two_run_intervals:
        sessions = [
            s for s in sessions
            if s.get("type") not in {"threshold", "sweetspot", "over_unders"}
        ]
    return [SkeletonSlot(s, "bike_fill", 3) for s in sessions]


def _short_run_minutes(marathon_volume: dict) -> int:
    return max(MIN_RUN_MIN, _km_to_minutes(float(marathon_volume.get("km_per_korte_sessie") or 8.0)))


def _km_to_minutes(km: float, pace_min_per_km: float = 5.8) -> int:
    return round(km * pace_min_per_km)


def _estimate_run_km(sessie: dict, marathon_volume: dict) -> float:
    if sessie.get("type") == "long_run" or sessie.get("type") == "long_run_ns":
        return float(marathon_volume.get("lange_duurloop_km") or 0)
    # Conservative skeleton-level estimate. Detailed workout parsing stays in
    # workout_annotations; the skeleton only needs ceiling protection.
    return max(0.0, round((sessie.get("duur_min") or 0) / 5.8, 1))


def _mark_run_km(slots: list[SkeletonSlot], planned_run_km: float, ceiling: float) -> None:
    for slot in slots:
        if (slot.sessie.get("sport") or "").lower() == "run":
            slot.sessie.setdefault("_skeleton", {})
            slot.sessie["_skeleton"].update({
                "planned_run_km": round(planned_run_km, 1),
                "run_km_ceiling": ceiling,
            })


def _run_quality_step_for_week(week_number: int) -> int:
    return max(1, min(week_number - 12, 6))


def _day_name(weekday: int) -> str:
    return [
        "maandag",
        "dinsdag",
        "woensdag",
        "donderdag",
        "vrijdag",
        "zaterdag",
        "zondag",
    ][weekday]
