"""TrainingPeaks HTTP client for the sync feature.

Uses the **undocumented** internal API at ``tpapi.trainingpeaks.com`` that
tp2intervals reverse-engineered. This means:

* Authentication is cookie-based. The user must manually extract the
  ``Production_tpAuth`` cookie from browser DevTools (see
  ``.streamlit/secrets.toml.example``).
* The cookie is exchanged for a short-lived Bearer token via
  ``GET /users/v3/token``.
* All other calls use ``Authorization: Bearer <token>``.
* Endpoints can change without notice; the ``TP_SYNC_ENABLED`` feature
  flag exists precisely so this can be killed without a code revert.

This module is intentionally thin: no caching, no retries, no logging.
Streamlit-side caching (``@st.cache_resource``) and retry policy belong
to the caller. Keeping the client dumb keeps the mocked tests simple.
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any

import requests

from trainingpeaks_errors import TPAPIError, TPAuthError

BASE_URL = "https://tpapi.trainingpeaks.com"
TOKEN_PATH = "/users/v3/token"
USER_PATH = "/users/v3/user"
CREATE_WORKOUT_PATH = "/fitness/v6/athletes/{user_id}/workouts"

DEFAULT_TIMEOUT = 15  # seconds — TP's undocumented API can be slow


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalise_cookie(raw: str) -> str:
    """Accept either 'Production_tpAuth=xxx' or just 'xxx'.

    Returns a complete Cookie-header value.
    """
    raw = (raw or "").strip()
    if not raw:
        raise TPAuthError("TP_AUTH_COOKIE is empty")
    if "=" in raw:
        return raw
    return f"Production_tpAuth={raw}"


def _raise_for_status(response: requests.Response, action: str) -> None:
    """Map TP API responses to our custom exceptions.

    401/403  → TPAuthError (cookie expired or invalid)
    Any other non-2xx → TPAPIError carrying the status code.
    """
    if 200 <= response.status_code < 300:
        return
    # Don't reflect response.text back to the user — it can contain cookies
    # or other headers echoed by a misbehaving proxy.
    if response.status_code in (401, 403):
        raise TPAuthError(
            f"TrainingPeaks {action} failed with {response.status_code}. "
            f"Your TP_AUTH_COOKIE is likely expired. Refresh it from "
            f"DevTools on trainingpeaks.com."
        )
    raise TPAPIError(
        f"TrainingPeaks {action} failed with HTTP {response.status_code}.",
        status_code=response.status_code,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def exchange_cookie_for_token(
    cookie: str, timeout: int = DEFAULT_TIMEOUT
) -> str:
    """Exchange a Production_tpAuth cookie for a short-lived Bearer token.

    Raises TPAuthError on 401/403 or on a malformed response body.
    """
    headers = {
        "Cookie": _normalise_cookie(cookie),
        "Accept": "application/json",
    }
    try:
        response = requests.get(
            f"{BASE_URL}{TOKEN_PATH}", headers=headers, timeout=timeout
        )
    except requests.Timeout as exc:
        raise TPAPIError(f"Token exchange timed out after {timeout}s") from exc
    except requests.RequestException as exc:
        raise TPAPIError(f"Token exchange network error: {exc}") from exc

    _raise_for_status(response, "token exchange")

    try:
        body = response.json()
    except ValueError as exc:
        raise TPAuthError("Token response was not valid JSON") from exc

    token_obj = body.get("token") if isinstance(body, dict) else None
    access_token = None
    if isinstance(token_obj, dict):
        access_token = token_obj.get("access_token")

    if not access_token:
        raise TPAuthError(
            "Token response did not contain token.access_token; "
            "the TrainingPeaks API shape may have changed."
        )
    return str(access_token)


def get_user_id(token: str, timeout: int = DEFAULT_TIMEOUT) -> int:
    """Fetch the authenticated user's numeric athleteId.

    The TP API returns it as ``userId`` (int). We return an int for
    direct URL interpolation in create_workout().
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    try:
        response = requests.get(
            f"{BASE_URL}{USER_PATH}", headers=headers, timeout=timeout
        )
    except requests.Timeout as exc:
        raise TPAPIError(f"User fetch timed out after {timeout}s") from exc
    except requests.RequestException as exc:
        raise TPAPIError(f"User fetch network error: {exc}") from exc

    _raise_for_status(response, "user fetch")

    body = response.json()
    user_id = body.get("userId") if isinstance(body, dict) else None
    if user_id is None:
        raise TPAPIError("User response missing userId field")
    return int(user_id)


def create_workout(
    token: str,
    user_id: int,
    workout_day: date,
    workout_type_id: int,
    title: str,
    description: str,
    total_seconds: int,
    tp_structure: dict[str, Any],
    tss_planned: float | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Create a planned workout on the user's TrainingPeaks calendar.

    Args:
        token: Bearer token from exchange_cookie_for_token().
        user_id: athleteId from get_user_id().
        workout_day: target calendar date.
        workout_type_id: TP sport code (2=Bike, 3=Run).
        title: short workout name.
        description: longer description / notes.
        total_seconds: total planned duration, used for totalTimePlanned.
        tp_structure: the TPWorkoutStructureDTO dict from
            workout_converter.convert()["tp_structure"]. Will be
            JSON-serialised into the request body's ``structure`` field.
        tss_planned: optional TSS estimate; server computes if omitted.

    Returns:
        Parsed JSON response body on 2xx (typically the created workout).

    Raises:
        TPAuthError on 401/403.
        TPAPIError on any other non-2xx or network failure.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "athleteId": user_id,
        "workoutDay": workout_day.isoformat(),
        "workoutTypeValueId": workout_type_id,
        "title": title,
        "description": description,
        "totalTimePlanned": round(total_seconds / 3600, 4),
        "structure": json.dumps(tp_structure),
    }
    if tss_planned is not None:
        payload["tssPlanned"] = tss_planned

    url = f"{BASE_URL}{CREATE_WORKOUT_PATH.format(user_id=user_id)}"
    try:
        response = requests.post(
            url, headers=headers, json=payload, timeout=timeout
        )
    except requests.Timeout as exc:
        raise TPAPIError(f"Create workout timed out after {timeout}s") from exc
    except requests.RequestException as exc:
        raise TPAPIError(f"Create workout network error: {exc}") from exc

    _raise_for_status(response, "create workout")

    try:
        return response.json()
    except ValueError:
        # Some TP endpoints return empty body on 201; treat that as OK.
        return {"status_code": response.status_code}
