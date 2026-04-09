"""Tests voor de nieuwe TP sync constraints (Fase 3 van redesign).

Twee delen:
1. is_syncable_date — de "alleen vandaag/morgen"-regel
2. propagate_swap_if_synced — delete+post bij swap van een gesynced event
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

import tp_sync_service
from trainingpeaks_errors import TPAPIError, TPAuthError, TPConversionError

FIXTURES = Path(__file__).parent / "fixtures" / "workout_docs"


def _load_fixture(name: str) -> dict:
    with open(FIXTURES / name, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# is_syncable_date — vandaag of morgen, niks anders
# ---------------------------------------------------------------------------

REFERENCE_DAY = date(2026, 4, 9)


class TestIsSyncableDate:
    def test_today_is_syncable(self):
        assert tp_sync_service.is_syncable_date(REFERENCE_DAY, today=REFERENCE_DAY) is True

    def test_tomorrow_is_syncable(self):
        tomorrow = REFERENCE_DAY + timedelta(days=1)
        assert tp_sync_service.is_syncable_date(tomorrow, today=REFERENCE_DAY) is True

    def test_yesterday_is_not_syncable(self):
        yesterday = REFERENCE_DAY - timedelta(days=1)
        assert tp_sync_service.is_syncable_date(yesterday, today=REFERENCE_DAY) is False

    def test_two_days_ahead_not_syncable(self):
        """Dag-na-morgen is te ver: plan kan nog schuiven, zinloos om te pushen."""
        assert (
            tp_sync_service.is_syncable_date(
                REFERENCE_DAY + timedelta(days=2), today=REFERENCE_DAY
            )
            is False
        )

    def test_one_week_ago_not_syncable(self):
        assert (
            tp_sync_service.is_syncable_date(
                REFERENCE_DAY - timedelta(days=7), today=REFERENCE_DAY
            )
            is False
        )

    def test_iso_date_string_accepted(self):
        """intervals.icu geeft start_date_local als 'YYYY-MM-DDTHH:MM:SS'."""
        assert (
            tp_sync_service.is_syncable_date("2026-04-09T00:00:00", today=REFERENCE_DAY)
            is True
        )

    def test_plain_yyyymmdd_accepted(self):
        assert (
            tp_sync_service.is_syncable_date("2026-04-10", today=REFERENCE_DAY) is True
        )

    def test_garbage_date_returns_false(self):
        """Malformed input mag niet crashen, alleen False returnen."""
        assert tp_sync_service.is_syncable_date("not-a-date", today=REFERENCE_DAY) is False
        assert tp_sync_service.is_syncable_date("", today=REFERENCE_DAY) is False

    def test_no_today_param_uses_current_date(self):
        """Sanity: zonder today-override gebruikt het date.today() stilletjes."""
        # Kan niet echt de waarde vergelijken zonder freeze,
        # maar het mag niet exploderen.
        result = tp_sync_service.is_syncable_date(date.today())
        assert result is True


# ---------------------------------------------------------------------------
# propagate_swap_if_synced — detect + delete + post bij al-gesynced workouts
# ---------------------------------------------------------------------------

# Gebruik een echte fixture: dat garandeert dat de converter niet struikelt.
# Als de fixture-shape verandert, worden de converter-tests al rood dus
# deze tests falen dan ook direct — consistent met de rest van de suite.
_FIXTURE = _load_fixture("bike_sweetspot_2x15_intervals.json")

VALID_NEW_EVENT = {
    "id": "evt-123",
    "name": "Nieuwe workout na swap",
    "type": "Ride",
    "description": "Ververste versie",
    "start_date_local": "2026-04-09T00:00:00",
    "workout_doc": _FIXTURE["workout_doc"],
    "icu_training_load": 50,
}

OLD_EVENT = {
    "id": "evt-123",
    "name": "Oude workout (origineel)",
    "type": "Ride",
    "start_date_local": "2026-04-09T00:00:00",
}


class TestPropagateSwapIfSynced:
    def test_no_propagation_when_not_synced(self, tmp_path: Path):
        """Als het event nooit naar TP is gepusht, doen we niks."""
        state_file = tmp_path / "state.json"

        result = tp_sync_service.propagate_swap_if_synced(
            OLD_EVENT,
            new_event_fetch_fn=lambda: VALID_NEW_EVENT,
            cookie="cookie",
            state_file=state_file,
        )
        assert result is None

    def test_propagation_triggers_delete_then_post(self, tmp_path: Path):
        """Gesynced + lokaal geswapt = delete oude TP workout + post nieuwe."""
        state_file = tmp_path / "state.json"

        # Arrange: markeer het event als gesynced (oude versie).
        tp_sync_service.mark_synced(
            event_id="evt-123",
            tp_workout_id=999_888,
            title="Oude workout (origineel)",
            workout_day="2026-04-09",
            state_file=state_file,
        )

        # Mock alle TP network calls.
        with patch("tp_sync_service.tpc") as mock_tpc:
            mock_tpc.exchange_cookie_for_token.return_value = "bearer-token"
            mock_tpc.get_user_id.return_value = 42
            mock_tpc.create_workout.return_value = {"workoutId": 111_222}

            result = tp_sync_service.propagate_swap_if_synced(
                OLD_EVENT,
                new_event_fetch_fn=lambda: VALID_NEW_EVENT,
                cookie="cookie",
                state_file=state_file,
            )

        # Assert: delete werd aangeroepen met de oude TP id
        mock_tpc.delete_workout.assert_called_once()
        delete_kwargs = mock_tpc.delete_workout.call_args.kwargs
        assert delete_kwargs["workout_id"] == 999_888
        assert delete_kwargs["user_id"] == 42

        # Create werd aangeroepen met de nieuwe titel
        mock_tpc.create_workout.assert_called_once()
        create_kwargs = mock_tpc.create_workout.call_args.kwargs
        assert create_kwargs["title"] == "Nieuwe workout na swap"

        # Result geeft terug dat er replaced is
        assert result is not None
        assert result["replaced"] is True
        assert result["tp_workout_id"] == 111_222

        # Sync-log is geüpdatet met de nieuwe TP id
        new_entry = tp_sync_service.is_synced("evt-123", state_file)
        assert new_entry["tp_workout_id"] == 111_222
        assert new_entry["title"] == "Nieuwe workout na swap"

    def test_propagation_fails_if_fresh_event_unavailable(self, tmp_path: Path):
        """Als we het verse event niet kunnen ophalen, falen we expliciet."""
        state_file = tmp_path / "state.json"

        tp_sync_service.mark_synced(
            event_id="evt-123",
            tp_workout_id=1,
            title="Oud",
            workout_day="2026-04-09",
            state_file=state_file,
        )

        with pytest.raises(TPConversionError, match="verse event"):
            tp_sync_service.propagate_swap_if_synced(
                OLD_EVENT,
                new_event_fetch_fn=lambda: None,
                cookie="cookie",
                state_file=state_file,
            )

    def test_propagation_raises_if_delete_fails(self, tmp_path: Path):
        """Als delete crashed, wissen we state niet — anders rare lege plek."""
        state_file = tmp_path / "state.json"

        tp_sync_service.mark_synced(
            event_id="evt-123",
            tp_workout_id=999_888,
            title="Oud",
            workout_day="2026-04-09",
            state_file=state_file,
        )

        with patch("tp_sync_service.tpc") as mock_tpc:
            mock_tpc.exchange_cookie_for_token.return_value = "token"
            mock_tpc.get_user_id.return_value = 42
            mock_tpc.delete_workout.side_effect = TPAPIError(
                "500 server error", status_code=500
            )

            with pytest.raises(TPAPIError):
                tp_sync_service.propagate_swap_if_synced(
                    OLD_EVENT,
                    new_event_fetch_fn=lambda: VALID_NEW_EVENT,
                    cookie="cookie",
                    state_file=state_file,
                )

            # Create is niet aangeroepen — we gaan niet naast de oude een
            # nieuwe creëren, dat geeft alleen maar dubbele workouts.
            mock_tpc.create_workout.assert_not_called()

        # Sync-log is ONVERANDERD — de oude workout staat nog in TP
        # en onze state weet dat nog.
        entry = tp_sync_service.is_synced("evt-123", state_file)
        assert entry is not None
        assert entry["tp_workout_id"] == 999_888

    def test_sync_event_without_allow_replace_still_raises(self, tmp_path: Path):
        """Handmatige sync van een al-gesynced event blijft een fout.

        Alleen de swap-propagatie pad mag allow_replace=True meegeven.
        """
        state_file = tmp_path / "state.json"

        tp_sync_service.mark_synced(
            event_id="evt-123",
            tp_workout_id=1,
            title="Oud",
            workout_day="2026-04-09",
            state_file=state_file,
        )

        with pytest.raises(TPConversionError, match="al gesynced"):
            tp_sync_service.sync_event(
                VALID_NEW_EVENT,
                cookie="cookie",
                state_file=state_file,
                # allow_replace ontbreekt → default False
            )
