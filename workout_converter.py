"""Pure function: intervals.icu workout_doc → TrainingPeaks structure.

This module has NO network, NO Streamlit, NO file I/O. It takes a
workout_doc dict (as returned by intervals.icu ``GET /events?resolve=true``)
plus a sport string, and returns a dict ready to drop into the
TrainingPeaks ``POST /fitness/v6/athletes/{userId}/workouts`` body as
the ``structure`` field (as a dict, **not** a JSON string — TP rejects
strings with "Workout structure is invalid").

Why pure: the tester review flagged silent mapping errors as the single
highest risk of the TrainingPeaks sync feature. Keeping this function
free of side effects means it can be exhaustively fixture-tested without
hitting any API, and regressions show up as failing unit tests instead
of polluted TrainingPeaks calendars.

TrainingPeaks structure shape (reverse-engineered from live calendar)
---------------------------------------------------------------------
Observed by fetching an existing workout from ``GET /fitness/v6/athletes/
{userId}/workouts/{start}/{end}`` and inspecting its ``structure`` dict.
Differs from the tp2intervals research notes in several subtle ways:

* **Every** top-level step is ``{"type": "step", ...}``. There is no
  ``"repetition"`` step type — repetition is expressed via ``length.unit``.
* Every top-level step has ``length: {value: N, unit: "repetition"}``
  where ``N`` is the number of reps. Single intervals use ``N=1``.
* Top-level steps contain a ``steps`` array with leaf objects.
* Leaf objects have only ``length`` (``{value: seconds, unit: "second"}``)
  and ``targets``. No ``type``, no ``name``.
* Target objects are ``{"minValue": X}`` for steady efforts and
  ``{"minValue": X, "maxValue": Y}`` for ranges/ramps.

MVP scope and known limitations
-------------------------------
* Duration-based steps only. Distance-based steps raise TPConversionError.
* Ramps are flattened to a min/max target band (not a real interpolated
  ramp). Acceptable trade-off per architect review for MVP.
* Only one level of nesting in repetition groups (matches observed data).
* Sports supported: Run, Ride, VirtualRide. Swim/weights/crosstrain not
  supported and must be filtered by the caller before invoking convert().
"""
from __future__ import annotations

from typing import Any, TypedDict

from trainingpeaks_errors import TPConversionError

# TrainingPeaks workout_type_value_id codes. Source: tp2intervals research
# (observation 390). Swim=1 intentionally omitted — not in MVP scope.
_TP_WORKOUT_TYPE_ID: dict[str, int] = {
    "Run": 3,
    "Ride": 2,
    "VirtualRide": 2,
}

# Maps intervals.icu target enum → (resolved key, threshold field name,
# TrainingPeaks primaryIntensityMetric string).
# The metric strings come from inspecting live TP workouts: bike uses
# "percentOfFtp", run uses "percentOfThresholdPace". "percentOfThresholdHr"
# follows the same naming pattern but is unverified against live data.
_TARGET_SPEC: dict[str, tuple[str, str, str]] = {
    "POWER": ("_power", "ftp", "percentOfFtp"),
    "PACE": ("_pace", "threshold_pace", "percentOfThresholdPace"),
    "HR": ("_hr", "lthr", "percentOfThresholdHr"),
}


class TPConversion(TypedDict):
    """Output of convert(). Keeps the converter return shape explicit."""

    tp_structure: dict[str, Any]
    workout_type_id: int
    total_seconds: int


def convert(workout_doc: dict[str, Any], sport: str) -> TPConversion:
    """Convert an intervals.icu workout_doc to TrainingPeaks format.

    Args:
        workout_doc: Full workout_doc dict from intervals.icu with
            ``resolve=true``. Must contain ``target``, ``steps``, and the
            threshold reference for its target type (ftp/lthr/threshold_pace).
        sport: intervals.icu sport string (``Run``, ``Ride``, ``VirtualRide``).

    Returns:
        TPConversion dict with the serialisable TP structure, the TP
        workout type id, and the summed step duration for sanity checks.

    Raises:
        TPConversionError: If any required field is missing, the sport is
            unsupported, the target threshold is zero or missing, or a
            step has an unresolvable target.
    """
    if not isinstance(workout_doc, dict):
        raise TPConversionError("workout_doc must be a dict")

    # --- Sport -------------------------------------------------------------
    if sport not in _TP_WORKOUT_TYPE_ID:
        raise TPConversionError(
            f"Unsupported sport '{sport}'. MVP supports: "
            f"{sorted(_TP_WORKOUT_TYPE_ID)}"
        )
    workout_type_id = _TP_WORKOUT_TYPE_ID[sport]

    # --- Target type -------------------------------------------------------
    target = workout_doc.get("target")
    if target not in _TARGET_SPEC:
        raise TPConversionError(
            f"Unknown or missing workout_doc.target: {target!r}. "
            f"Expected one of {sorted(_TARGET_SPEC)}"
        )
    resolved_key, threshold_field, primary_intensity = _TARGET_SPEC[target]

    threshold = workout_doc.get(threshold_field)
    if not threshold or threshold <= 0:
        raise TPConversionError(
            f"workout_doc.{threshold_field} is missing or zero; "
            f"cannot compute % targets for {target} workout"
        )

    # --- Steps -------------------------------------------------------------
    raw_steps = workout_doc.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise TPConversionError("workout_doc.steps is missing or empty")

    tp_steps: list[dict[str, Any]] = []
    total_seconds = 0
    for idx, step in enumerate(raw_steps):
        if not isinstance(step, dict):
            raise TPConversionError(f"step[{idx}] is not a dict")
        converted, step_seconds = _convert_step(
            step, resolved_key, threshold, path=f"step[{idx}]"
        )
        tp_steps.append(converted)
        total_seconds += step_seconds

    tp_structure = {
        "structure": tp_steps,
        "primaryLengthMetric": "duration",
        "primaryIntensityMetric": primary_intensity,
    }

    return TPConversion(
        tp_structure=tp_structure,
        workout_type_id=workout_type_id,
        total_seconds=total_seconds,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _convert_step(
    step: dict[str, Any],
    resolved_key: str,
    threshold: float,
    path: str,
) -> tuple[dict[str, Any], int]:
    """Convert one intervals.icu top-level step into a TP repetition wrapper.

    TrainingPeaks wraps every top-level step in a ``{type: step, length:
    {unit: repetition}}`` container, even single intervals (which use
    ``value: 1``). Repetition groups from intervals.icu use ``value: N``
    with the same nested leaf-step format.

    Returns the TP wrapper dict and the total seconds it consumes
    (reps × sum(child leaf durations)).
    """
    # Repetition group: has 'reps' and nested 'steps'. Multi-rep wrappers
    # use type "repetition"; single-rep wrappers (reps == 1 or single
    # intervals from a flat step) use type "step". Both carry the same
    # length.unit == "repetition" shape — only the type field differs.
    if "reps" in step and isinstance(step.get("steps"), list):
        reps = step.get("reps")
        if not isinstance(reps, int) or reps <= 0:
            raise TPConversionError(
                f"{path}: repetition group has invalid reps={reps!r}"
            )
        child_steps_raw = step.get("steps") or []
        if not child_steps_raw:
            raise TPConversionError(
                f"{path}: repetition group has no child steps"
            )
        leaves: list[dict[str, Any]] = []
        leaf_total = 0
        for i, child in enumerate(child_steps_raw):
            if not isinstance(child, dict):
                raise TPConversionError(f"{path}.steps[{i}] is not a dict")
            if "reps" in child and isinstance(child.get("steps"), list):
                raise TPConversionError(
                    f"{path}.steps[{i}]: nested repetition groups are not "
                    f"supported in MVP (TrainingPeaks structure is single-level)"
                )
            leaf, leaf_seconds = _leaf_step(
                child, resolved_key, threshold, path=f"{path}.steps[{i}]"
            )
            leaves.append(leaf)
            leaf_total += leaf_seconds
        wrapper = {
            "type": "repetition" if reps > 1 else "step",
            "length": {"value": reps, "unit": "repetition"},
            "steps": leaves,
        }
        return wrapper, reps * leaf_total

    # Single interval: wrap a single leaf in a 1-rep container.
    leaf, seconds = _leaf_step(step, resolved_key, threshold, path)
    wrapper = {
        "type": "step",
        "length": {"value": 1, "unit": "repetition"},
        "steps": [leaf],
    }
    return wrapper, seconds


def _leaf_step(
    step: dict[str, Any],
    resolved_key: str,
    threshold: float,
    path: str,
) -> tuple[dict[str, Any], int]:
    """Build a TP leaf step: ``{length: {unit: second}, targets: [...]}``.

    Leaf steps intentionally carry no ``type`` and no ``name`` — TP only
    wants duration and targets at this level.
    """
    duration = step.get("duration")
    if not isinstance(duration, (int, float)) or duration <= 0:
        raise TPConversionError(
            f"{path}: duration missing or non-positive ({duration!r}); "
            f"distance-only steps are not supported in MVP"
        )
    duration_s = int(duration)

    min_pct, max_pct = _resolve_target_range(step, resolved_key, threshold, path)

    # Steady target (min == max) is expressed as just {minValue: X} in TP.
    if min_pct == max_pct:
        primary: dict[str, Any] = {"minValue": min_pct}
    else:
        primary = {"minValue": min_pct, "maxValue": max_pct}

    targets: list[dict[str, Any]] = [primary]

    # Cadence is currently dropped for TP: the live TP calendar format we
    # inspected carries only the intensity target, and mixing units in the
    # targets array triggers "Workout structure is invalid". Keep it out
    # until we verify the right encoding.

    return {
        "length": {"value": duration_s, "unit": "second"},
        "targets": targets,
    }, duration_s


def _resolve_target_range(
    step: dict[str, Any],
    resolved_key: str,
    threshold: float,
    path: str,
) -> tuple[float, float]:
    """Extract min/max target as % of threshold from a resolved step.

    intervals.icu stores the resolved absolute values in ``_power`` /
    ``_pace`` / ``_hr`` with either a single ``value`` or a ``start``/
    ``end`` pair for ranges and ramps. We convert to percentages using
    the workout's threshold (ftp / lthr / threshold_pace).
    """
    resolved = step.get(resolved_key)
    if not isinstance(resolved, dict):
        raise TPConversionError(
            f"{path}: missing resolved {resolved_key}; call intervals.icu "
            f"with resolve=true"
        )

    # Prefer explicit start/end range if present, otherwise fall back to value.
    if "start" in resolved and "end" in resolved:
        lo_raw = resolved["start"]
        hi_raw = resolved["end"]
    elif "value" in resolved:
        lo_raw = hi_raw = resolved["value"]
    else:
        raise TPConversionError(
            f"{path}: {resolved_key} has no value/start/end fields"
        )

    if lo_raw is None or hi_raw is None:
        raise TPConversionError(
            f"{path}: {resolved_key} contains None ({lo_raw!r}, {hi_raw!r})"
        )

    lo = min(float(lo_raw), float(hi_raw))
    hi = max(float(lo_raw), float(hi_raw))

    return (
        round((lo / threshold) * 100, 1),
        round((hi / threshold) * 100, 1),
    )


