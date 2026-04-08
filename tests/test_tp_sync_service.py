"""Tests for tp_sync_service — sync-log persistence, connection check,
and the end-to-end sync_event happy path (with TP calls mocked)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import tp_sync_service
from trainingpeaks_errors import TPAPIError, TPAuthError, TPConversionError


# ---------------------------------------------------------------------------
# Sync-log persistence
# ---------------------------------------------------------------------------


def test_mark_and_lookup_sync_entry(tmp_path: Path):
    state_file = tmp_path / "state.json"

    assert tp_sync_service.is_synced("abc", state_file) is None

    tp_sync_service.mark_synced(
        event_id="abc",
        tp_workout_id=3672391939,
        title="Bosrun Z2",
        workout_day="2026-04-09",
        state_file=state_file,
    )

    entry = tp_sync_service.is_synced("abc", state_file)
    assert entry is not None
    assert entry["tp_workout_id"] == 3672391939
    assert entry["title"] == "Bosrun Z2"
    assert entry["workout_day"] == "2026-04-09"
    assert "synced_at" in entry


def test_mark_synced_preserves_existing_state_keys(tmp_path: Path):
    """state.json has other fields (load, phase, etc.) — don't nuke them."""
    state_file = tmp_path / "state.json"
    state_file.write_text(
        json.dumps(
            {
                "current_phase": "build",
                "load": {"ctl_estimate": 55},
            }
        ),
        encoding="utf-8",
    )

    tp_sync_service.mark_synced(
        event_id="evt-1",
        tp_workout_id=1,
        title="T",
        workout_day="2026-04-09",
        state_file=state_file,
    )

    saved = json.loads(state_file.read_text(encoding="utf-8"))
    assert saved["current_phase"] == "build"
    assert saved["load"]["ctl_estimate"] == 55
    assert "evt-1" in saved["tp_sync_log"]


# ---------------------------------------------------------------------------
# Connection check
# ---------------------------------------------------------------------------


def test_check_connection_empty_cookie_returns_false_without_network():
    with patch.object(tp_sync_service.tpc, "exchange_cookie_for_token") as exch:
        ok, msg = tp_sync_service.check_connection("")
    assert ok is False
    assert "ontbreekt" in msg.lower()
    exch.assert_not_called()


def test_check_connection_auth_error_maps_to_friendly_message():
    with patch.object(
        tp_sync_service.tpc,
        "exchange_cookie_for_token",
        side_effect=TPAuthError("expired"),
    ):
        ok, msg = tp_sync_service.check_connection("Production_tpAuth=old")
    assert ok is False
    assert "cookie verlopen" in msg.lower()


def test_check_connection_api_error_maps_to_friendly_message():
    with patch.object(
        tp_sync_service.tpc,
        "exchange_cookie_for_token",
        side_effect=TPAPIError("500 gateway"),
    ):
        ok, msg = tp_sync_service.check_connection("Production_tpAuth=x")
    assert ok is False
    assert "onbereikbaar" in msg.lower()


def test_check_connection_happy_path_returns_true():
    with patch.object(
        tp_sync_service.tpc,
        "exchange_cookie_for_token",
        return_value="tok",
    ):
        ok, msg = tp_sync_service.check_connection("Production_tpAuth=good")
    assert ok is True
    assert msg == "Verbonden"


# ---------------------------------------------------------------------------
# sync_event (full flow with mocked TP network)
# ---------------------------------------------------------------------------


def _load_fixture(name: str) -> tuple[dict, str]:
    """Load one of the workout_doc fixtures and return (workout_doc, sport)."""
    path = (
        Path(__file__).parent / "fixtures" / "workout_docs" / name
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["workout_doc"], data["sport"]


def test_sync_event_happy_path_calls_tp_and_records_in_log(tmp_path: Path):
    state_file = tmp_path / "state.json"
    workout_doc, sport = _load_fixture("bike_threshold_3x8_intervals.json")
    event = {
        "id": "evt-123",
        "type": sport,
        "name": "Threshold 3x8",
        "description": "main set",
        "start_date_local": "2026-04-08T00:00:00",
        "workout_doc": workout_doc,
        "icu_training_load": 85,
    }

    with patch.object(
        tp_sync_service.tpc, "exchange_cookie_for_token", return_value="tok"
    ), patch.object(
        tp_sync_service.tpc, "get_user_id", return_value=3398462
    ) as mock_user, patch.object(
        tp_sync_service.tpc,
        "create_workout",
        return_value={"workoutId": 99999, "title": "Threshold 3x8"},
    ) as mock_create:
        result = tp_sync_service.sync_event(
            event, cookie="Production_tpAuth=x", state_file=state_file
        )

    assert result["tp_workout_id"] == 99999
    assert result["workout_day"] == "2026-04-08"
    mock_user.assert_called_once_with("tok")
    mock_create.assert_called_once()
    _, kwargs = mock_create.call_args
    assert kwargs["workout_type_id"] == 2  # Bike
    assert kwargs["tss_planned"] == 85

    # Sync log updated
    entry = tp_sync_service.is_synced("evt-123", state_file)
    assert entry is not None
    assert entry["tp_workout_id"] == 99999


def test_sync_event_rejects_unsupported_sport(tmp_path: Path):
    event = {
        "id": "swim-1",
        "type": "Swim",
        "workout_doc": {"target": "POWER", "ftp": 290, "steps": []},
        "start_date_local": "2026-04-08T00:00:00",
    }
    with pytest.raises(TPConversionError, match="niet ondersteund"):
        tp_sync_service.sync_event(
            event, cookie="x", state_file=tmp_path / "s.json"
        )


def test_sync_event_rejects_already_synced_event(tmp_path: Path):
    state_file = tmp_path / "state.json"
    workout_doc, sport = _load_fixture("run_z2_pace_steady.json")
    event = {
        "id": "evt-dupe",
        "type": sport,
        "name": "Run",
        "start_date_local": "2026-04-08T00:00:00",
        "workout_doc": workout_doc,
    }
    tp_sync_service.mark_synced(
        "evt-dupe", 11111, "Run", "2026-04-08", state_file=state_file
    )

    with pytest.raises(TPConversionError, match="al gesynced"):
        tp_sync_service.sync_event(event, cookie="x", state_file=state_file)


def test_sync_event_without_workout_doc_raises_clearly(tmp_path: Path):
    event = {
        "id": "no-doc",
        "type": "Run",
        "start_date_local": "2026-04-08T00:00:00",
    }
    with pytest.raises(TPConversionError, match="workout_doc"):
        tp_sync_service.sync_event(
            event, cookie="x", state_file=tmp_path / "s.json"
        )
