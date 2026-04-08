"""Service layer tussen de Streamlit-UI en de TrainingPeaks-client.

Centraliseert drie dingen die de UI anders zelf zou moeten weten:

* **Sync-log** — welke intervals.icu events zijn al naar TP gepusht? Bewaard
  in ``state.json`` zodat dubbele pushes over sessies heen voorkomen
  worden (business analyst review obs 417: MVP-must item).
* **Connection test** — één call richting TP die ``(ok, human_message)``
  teruggeeft, gebruikt door de sidebar-status-indicator zonder dat de
  UI-code zelf TP-exception-types hoeft te kennen.
* **Sync event** — de volledige happy-path flow voor één event: workout_doc
  valideren, converteren, pushen, marken. Exceptions bubbelen naar de UI
  zodat die ze in ``st.error`` kan laten zien; geen stille failures.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import trainingpeaks_client as tpc
from trainingpeaks_errors import TPAPIError, TPAuthError, TPConversionError
from workout_converter import convert

STATE_PATH = Path(__file__).parent / "state.json"
SYNC_LOG_KEY = "tp_sync_log"

# Sporten die we aankunnen. De UI moet de sync-knop voor andere sporten
# verbergen — dit is een vangnet voor als er toch iets doorlekt.
SUPPORTED_SPORTS = {"Run", "Ride", "VirtualRide"}


# ---------------------------------------------------------------------------
# Sync log persistence (state.json)
# ---------------------------------------------------------------------------


def _load_state(state_file: Path = STATE_PATH) -> dict[str, Any]:
    try:
        with open(state_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_state(state: dict[str, Any], state_file: Path = STATE_PATH) -> None:
    # Simple read-modify-write. Single-user local use — no locking.
    state_file.parent.mkdir(parents=True, exist_ok=True)
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def load_sync_log(state_file: Path = STATE_PATH) -> dict[str, Any]:
    """Return ``{event_id: {tp_workout_id, synced_at, title, workout_day}}``."""
    return _load_state(state_file).get(SYNC_LOG_KEY, {})


def is_synced(event_id: str, state_file: Path = STATE_PATH) -> dict | None:
    """Return the sync-log entry for ``event_id`` or None if never synced."""
    log = load_sync_log(state_file)
    return log.get(str(event_id))


def mark_synced(
    event_id: str,
    tp_workout_id: int,
    title: str,
    workout_day: str,
    state_file: Path = STATE_PATH,
) -> None:
    """Append/update a sync entry for ``event_id`` in state.json."""
    state = _load_state(state_file)
    log = state.get(SYNC_LOG_KEY) or {}
    log[str(event_id)] = {
        "tp_workout_id": tp_workout_id,
        "synced_at": datetime.now().isoformat(timespec="seconds"),
        "title": title,
        "workout_day": workout_day,
    }
    state[SYNC_LOG_KEY] = log
    _save_state(state, state_file)


# ---------------------------------------------------------------------------
# Connection check
# ---------------------------------------------------------------------------


def check_connection(cookie: str) -> tuple[bool, str]:
    """Try to exchange the cookie for a token. Returns ``(ok, message)``.

    Never raises — callers can render the message directly.
    """
    if not cookie:
        return False, "TP_AUTH_COOKIE ontbreekt"
    try:
        tpc.exchange_cookie_for_token(cookie)
    except TPAuthError as exc:
        return False, f"Cookie verlopen — {exc}"
    except TPAPIError as exc:
        return False, f"TP onbereikbaar — {exc}"
    return True, "Verbonden"


# ---------------------------------------------------------------------------
# Full sync flow for one event
# ---------------------------------------------------------------------------


def sync_event(
    event: dict[str, Any],
    cookie: str,
    state_file: Path = STATE_PATH,
) -> dict[str, Any]:
    """Convert + push one intervals.icu event and record it in the sync log.

    ``event`` must already carry ``workout_doc`` (call intervals_client.
    get_events with ``resolve=True``). The sport must be in
    :data:`SUPPORTED_SPORTS`.

    Returns a dict with ``{tp_workout_id, title, workout_day}`` on success.
    Raises TPConversionError, TPAuthError, or TPAPIError on failure —
    the UI should catch those and render them in ``st.error``.
    """
    event_id = str(event.get("id") or "")
    if not event_id:
        raise TPConversionError("Event has no id; cannot track sync state")

    sport = event.get("type", "")
    if sport not in SUPPORTED_SPORTS:
        raise TPConversionError(
            f"Sport '{sport}' wordt (nog) niet ondersteund voor TP-sync"
        )

    workout_doc = event.get("workout_doc")
    if not workout_doc:
        raise TPConversionError(
            "Event heeft geen workout_doc — haal events op met resolve=True"
        )

    existing = is_synced(event_id, state_file)
    if existing:
        raise TPConversionError(
            f"Workout is al gesynced naar TP "
            f"(workoutId={existing.get('tp_workout_id')})"
        )

    # --- Conversion (pure, no network) ---
    conversion = convert(workout_doc, sport)

    # --- Network: cookie → token → user → create workout ---
    token = tpc.exchange_cookie_for_token(cookie)
    user_id = tpc.get_user_id(token)

    start_date_local = event.get("start_date_local", "")[:10]
    if not start_date_local:
        raise TPConversionError("Event missing start_date_local")
    workout_day = datetime.strptime(start_date_local, "%Y-%m-%d").date()

    title = event.get("name") or "(untitled)"
    description = event.get("description") or ""

    response = tpc.create_workout(
        token=token,
        user_id=user_id,
        workout_day=workout_day,
        workout_type_id=conversion["workout_type_id"],
        title=title,
        description=description,
        total_seconds=conversion["total_seconds"],
        tp_structure=conversion["tp_structure"],
        tss_planned=event.get("icu_training_load"),
    )

    tp_workout_id = response.get("workoutId") or response.get("status_code", 0)
    mark_synced(
        event_id=event_id,
        tp_workout_id=int(tp_workout_id) if tp_workout_id else 0,
        title=title,
        workout_day=workout_day.isoformat(),
        state_file=state_file,
    )

    return {
        "tp_workout_id": tp_workout_id,
        "title": title,
        "workout_day": workout_day.isoformat(),
    }
