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
from datetime import date, datetime, timedelta
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


def is_syncable_date(event_date: date | str, today: date | None = None) -> bool:
    """Is deze event-datum geldig om NU handmatig te syncen naar TP?

    Regels (zie DECISIONS.md):
    - De atleet gebruikt TP primair als Zwift-target en drukt op de dag
      zelf op sync. 's Avonds de dag ervoor klaarzetten mag ook.
    - Gister is te laat (workout is al over).
    - Over 2+ dagen is te vroeg (plan kan nog schuiven).

    Returns True als event_date in {vandaag, morgen} in lokale tijd.
    """
    if today is None:
        today = date.today()
    if isinstance(event_date, str):
        try:
            event_date = date.fromisoformat(event_date[:10])
        except (ValueError, TypeError):
            return False
    tomorrow = today + timedelta(days=1)
    return event_date in (today, tomorrow)


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
    *,
    allow_replace: bool = False,
) -> dict[str, Any]:
    """Convert + push one intervals.icu event and record it in the sync log.

    ``event`` must already carry ``workout_doc`` (call intervals_client.
    get_events with ``resolve=True``). The sport must be in
    :data:`SUPPORTED_SPORTS`.

    Args:
        event: intervals.icu event met workout_doc.
        cookie: TP auth cookie.
        state_file: pad naar state.json (override voor tests).
        allow_replace: als True en het event is al gesynced, wordt de
            oude TP workout EERST verwijderd en daarna de nieuwe gepost
            (swap-propagatie). Default False → TPConversionError bij
            dubbele sync.

    Returns a dict met ``{tp_workout_id, title, workout_day, replaced}``.
    ``replaced`` is True als er een delete+post cyclus is gedaan.

    Raises TPConversionError, TPAuthError, or TPAPIError on failure.
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
    if existing and not allow_replace:
        raise TPConversionError(
            f"Workout is al gesynced naar TP "
            f"(workoutId={existing.get('tp_workout_id')})"
        )

    # --- Conversion (pure, no network) ---
    conversion = convert(workout_doc, sport)

    # --- Network: cookie → token → user ---
    token = tpc.exchange_cookie_for_token(cookie)
    user_id = tpc.get_user_id(token)

    start_date_local = event.get("start_date_local", "")[:10]
    if not start_date_local:
        raise TPConversionError("Event missing start_date_local")
    workout_day = datetime.strptime(start_date_local, "%Y-%m-%d").date()

    title = event.get("name") or "(untitled)"
    description = event.get("description") or ""

    # --- Swap-propagatie: als er een oude versie in TP stond, eerst weg ---
    replaced = False
    if existing and allow_replace:
        old_tp_id = existing.get("tp_workout_id")
        if old_tp_id:
            try:
                tpc.delete_workout(
                    token=token,
                    user_id=user_id,
                    workout_id=int(old_tp_id),
                )
                replaced = True
            except TPAPIError:
                # Als delete faalt, wissen we de sync-state niet.
                # Raise door zodat de UI dit als "sync mislukt, oude staat
                # er nog" kan tonen — geen lege plek in de kalender.
                raise

    # --- Post nieuwe workout ---
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
        "replaced": replaced,
    }


def propagate_swap_if_synced(
    old_event: dict[str, Any],
    new_event_fetch_fn,
    cookie: str,
    state_file: Path = STATE_PATH,
) -> dict[str, Any] | None:
    """Trigger delete+post in TP als het event al gesynced was.

    Use case: user heeft eerder vandaag op sync-knop gedrukt. Daarna
    swapt hij lokaal. We willen dat de nieuwe versie in TP/Zwift staat.

    Args:
        old_event: het event zoals het was VOOR de lokale swap
            (met de oude naam). Gebruikt om te detecteren of dit event
            al gesynced was.
        new_event_fetch_fn: callable() -> dict[str, Any]. Wordt pas
            aangeroepen als we weten dat er gesynced was. Moet het
            verse event met workout_doc returnen.
        cookie: TP auth cookie.
        state_file: pad naar state.json.

    Returns:
        - None als er niet gesynced was (niets te doen).
        - Dict met {tp_workout_id, replaced: True, ...} bij geslaagde
          propagatie.

    Raises:
        TPAuthError/TPAPIError/TPConversionError als de propagatie
        faalt. Caller beslist hoe te tonen.
    """
    event_id = str(old_event.get("id") or "")
    if not event_id:
        return None

    existing = is_synced(event_id, state_file)
    if not existing:
        return None  # was niet gesynced, swap heeft geen TP-consequenties

    new_event = new_event_fetch_fn()
    if not new_event:
        raise TPConversionError(
            "Kan verse event niet ophalen voor swap-propagatie"
        )

    return sync_event(new_event, cookie, state_file, allow_replace=True)
