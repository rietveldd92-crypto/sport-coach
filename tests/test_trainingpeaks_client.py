"""Mocked integration tests for trainingpeaks_client.

No real network. We patch ``requests.get`` and ``requests.post`` at the
``trainingpeaks_client`` module level and feed stubbed Response objects
back. Covers the 6 scenarios from the tester review (obs 418): token
200/401, create workout 201/401/500/timeout.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
import requests

import trainingpeaks_client as tpc
from trainingpeaks_errors import TPAPIError, TPAuthError


def _mock_response(status: int, body: dict | None = None) -> MagicMock:
    """Build a MagicMock that mimics requests.Response for our purposes."""
    response = MagicMock(spec=requests.Response)
    response.status_code = status
    response.json.return_value = body or {}
    response.text = "" if body is None else str(body)
    return response


# ---------------------------------------------------------------------------
# exchange_cookie_for_token
# ---------------------------------------------------------------------------


def test_token_exchange_returns_access_token_on_200():
    fake = _mock_response(200, {"token": {"access_token": "tok-abc"}})
    with patch.object(tpc.requests, "get", return_value=fake) as mock_get:
        token = tpc.exchange_cookie_for_token("Production_tpAuth=raw")

    assert token == "tok-abc"
    # Check the cookie header was set correctly
    _, kwargs = mock_get.call_args
    assert "Production_tpAuth=raw" in kwargs["headers"]["Cookie"]


def test_token_exchange_accepts_raw_cookie_value_without_prefix():
    fake = _mock_response(200, {"token": {"access_token": "tok-xyz"}})
    with patch.object(tpc.requests, "get", return_value=fake) as mock_get:
        tpc.exchange_cookie_for_token("justthevalue")

    _, kwargs = mock_get.call_args
    assert kwargs["headers"]["Cookie"] == "Production_tpAuth=justthevalue"


def test_token_exchange_401_raises_tp_auth_error():
    fake = _mock_response(401, {"error": "Unauthorized"})
    with patch.object(tpc.requests, "get", return_value=fake):
        with pytest.raises(TPAuthError, match="expired"):
            tpc.exchange_cookie_for_token("Production_tpAuth=dead")


def test_token_exchange_timeout_raises_tp_api_error():
    with patch.object(
        tpc.requests, "get", side_effect=requests.Timeout("slow")
    ):
        with pytest.raises(TPAPIError, match="timed out"):
            tpc.exchange_cookie_for_token("Production_tpAuth=whatever")


def test_token_exchange_malformed_body_raises_tp_auth_error():
    fake = _mock_response(200, {"wrong": "shape"})
    with patch.object(tpc.requests, "get", return_value=fake):
        with pytest.raises(TPAuthError, match="access_token"):
            tpc.exchange_cookie_for_token("Production_tpAuth=x")


def test_empty_cookie_raises_tp_auth_error_without_network():
    with patch.object(tpc.requests, "get") as mock_get:
        with pytest.raises(TPAuthError, match="empty"):
            tpc.exchange_cookie_for_token("   ")
    mock_get.assert_not_called()


# ---------------------------------------------------------------------------
# create_workout
# ---------------------------------------------------------------------------

SAMPLE_STRUCTURE = {
    "structure": [
        {
            "type": "step",
            "length": {"value": 1800, "unit": "second"},
            "name": "Z2",
            "targets": [{"minValue": 60.0, "maxValue": 75.0}],
        }
    ],
    "primaryLengthMetric": "duration",
    "primaryIntensityMetric": "power",
    "visualizationDistanceUnit": None,
}


def _call_create_workout(**overrides):
    kwargs = dict(
        token="tok",
        user_id=12345,
        workout_day=date(2030, 1, 1),
        workout_type_id=2,
        title="Test",
        description="desc",
        total_seconds=1800,
        tp_structure=SAMPLE_STRUCTURE,
    )
    kwargs.update(overrides)
    return tpc.create_workout(**kwargs)


def test_create_workout_201_returns_parsed_body():
    fake = _mock_response(201, {"id": "wk-1", "title": "Test"})
    with patch.object(tpc.requests, "post", return_value=fake) as mock_post:
        result = _call_create_workout()

    assert result == {"id": "wk-1", "title": "Test"}

    # Validate request shape: URL has user_id, Bearer header set, structure
    # is sent as a nested DICT (not string — TP rejects strings with
    # "Workout structure is invalid"), workoutDay carries a midnight suffix.
    args, kwargs = mock_post.call_args
    assert "/fitness/v6/athletes/12345/workouts" in args[0]
    assert kwargs["headers"]["Authorization"] == "Bearer tok"
    payload = kwargs["json"]
    assert payload["athleteId"] == 12345
    assert payload["workoutDay"] == "2030-01-01T00:00:00"
    assert payload["workoutTypeValueId"] == 2
    assert isinstance(payload["structure"], dict), (
        "structure must be a nested dict — TP rejects stringified payloads"
    )
    assert payload["structure"] is SAMPLE_STRUCTURE
    assert payload["totalTimePlanned"] == pytest.approx(0.5, abs=0.01)  # 30 min


def test_create_workout_401_raises_tp_auth_error():
    fake = _mock_response(401, {"error": "unauth"})
    with patch.object(tpc.requests, "post", return_value=fake):
        with pytest.raises(TPAuthError, match="expired"):
            _call_create_workout()


def test_create_workout_500_raises_tp_api_error_with_status():
    fake = _mock_response(500)
    with patch.object(tpc.requests, "post", return_value=fake):
        with pytest.raises(TPAPIError) as exc_info:
            _call_create_workout()
    assert exc_info.value.status_code == 500


def test_create_workout_timeout_raises_tp_api_error():
    with patch.object(
        tpc.requests, "post", side_effect=requests.Timeout("slow")
    ):
        with pytest.raises(TPAPIError, match="timed out"):
            _call_create_workout()


def test_create_workout_handles_empty_response_body():
    """Some TP endpoints return 201 with no JSON body; don't crash on that."""
    empty = MagicMock(spec=requests.Response)
    empty.status_code = 201
    empty.json.side_effect = ValueError("no body")
    with patch.object(tpc.requests, "post", return_value=empty):
        result = _call_create_workout()
    assert result == {"status_code": 201}


# ---------------------------------------------------------------------------
# get_user_id
# ---------------------------------------------------------------------------


def test_get_user_id_happy_path_nested_user_object():
    """Real TP shape: userId nested inside top-level 'user' object."""
    fake = _mock_response(
        200,
        {"user": {"userId": 3398462, "settings": {}}, "accountStatus": {}},
    )
    with patch.object(tpc.requests, "get", return_value=fake):
        assert tpc.get_user_id("tok") == 3398462


def test_get_user_id_falls_back_to_top_level_userid():
    """Tolerate a flat shape in case TP changes its response structure."""
    fake = _mock_response(200, {"userId": 12345})
    with patch.object(tpc.requests, "get", return_value=fake):
        assert tpc.get_user_id("tok") == 12345


def test_get_user_id_401_raises_tp_auth_error():
    fake = _mock_response(401)
    with patch.object(tpc.requests, "get", return_value=fake):
        with pytest.raises(TPAuthError):
            tpc.get_user_id("expired-tok")


def test_get_user_id_missing_field_raises_tp_api_error():
    fake = _mock_response(200, {"wrong": "shape"})
    with patch.object(tpc.requests, "get", return_value=fake):
        with pytest.raises(TPAPIError, match="userId"):
            tpc.get_user_id("tok")
