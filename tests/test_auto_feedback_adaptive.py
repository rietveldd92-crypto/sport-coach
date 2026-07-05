"""Tests voor auto_feedback.run_adaptive_cycle — vooral de create/delete-
guard die de duplicaat-cascade-bug voorkomt (zie agents/adapt_week.py):
een sacred sessie die herplant wordt, mag alleen het origineel verliezen als
de vervangende 'create' ook echt gelukt is.
"""
from __future__ import annotations

import auto_feedback
import intervals_client
from agents.models import AdaptResult, Deviation, Modification

STATE = {"load": {"ctl_estimate": 49.0}}


def _reschedule_result() -> AdaptResult:
    create_mod = Modification(
        event_id="orig1",
        action="create",
        after={
            "name": "Drempel", "type": "Run", "load_target": 70,
            "start_date_local": "2026-07-08T09:00:00",
        },
        tss_delta=70,
    )
    delete_mod = Modification(
        event_id="orig1",
        action="delete",
        before={"id": "orig1", "name": "Drempel"},
        reason="Origineel event verwijderd na herplanning (voorkomt duplicaat-cascade)",
    )
    return AdaptResult(
        new_events=[create_mod.after],
        modifications=[create_mod, delete_mod],
        narrative="test", invariant="test",
    )


def _patch_common(monkeypatch, deviation):
    monkeypatch.setattr(auto_feedback, "detect_deviations",
                         lambda events, activities: [deviation])
    monkeypatch.setattr(auto_feedback, "adapt_week",
                         lambda *a, **k: _reschedule_result())
    monkeypatch.setattr(auto_feedback, "_load_state", lambda: STATE)
    monkeypatch.setattr(auto_feedback.adjustments_log, "build_entry",
                         lambda *a, **k: {"id": "x"})
    monkeypatch.setattr(auto_feedback.adjustments_log, "append", lambda entry: None)

    from agents import volume_compensation
    monkeypatch.setattr(volume_compensation, "apply_to_events", lambda **k: [])


def _sacred_skipped_dev() -> Deviation:
    return Deviation(
        type="skipped", planned_event_id="orig1", sacred=True,
        tss_planned=70, tss_actual=0, planned_date="2026-07-06",
    )


def test_delete_skipped_when_create_fails(monkeypatch):
    """Als het aanmaken van de vervangende sessie faalt, mag het origineel
    niet alsnog verwijderd worden — anders raakt de sacred sessie kwijt
    zonder vervanging (erger dan de oorspronkelijke duplicaat-bug)."""
    _patch_common(monkeypatch, _sacred_skipped_dev())

    def _boom(**kwargs):
        raise RuntimeError("intervals.icu 500")

    monkeypatch.setattr(intervals_client, "create_event", _boom)
    deleted = []
    monkeypatch.setattr(intervals_client, "delete_event", lambda eid: deleted.append(eid))

    result = auto_feedback.run_adaptive_cycle([], [], dry_run=False)

    assert deleted == []
    assert result["applied"] is False


def test_delete_happens_after_create_succeeds(monkeypatch):
    """Als de vervangende sessie wél gelukt is, moet het origineel worden
    opgeruimd — anders cascadeert de duplicatie de volgende dag opnieuw."""
    _patch_common(monkeypatch, _sacred_skipped_dev())

    created = []

    def _create(**kwargs):
        created.append(kwargs)
        return {"id": "new1"}

    monkeypatch.setattr(intervals_client, "create_event", _create)
    deleted = []
    monkeypatch.setattr(intervals_client, "delete_event", lambda eid: deleted.append(eid))

    result = auto_feedback.run_adaptive_cycle([], [], dry_run=False)

    assert deleted == ["orig1"]
    assert result["applied"] is True
    # sport_type + start_time moeten meegegeven zijn — anders defaultet
    # create_event naar Ride/00:00 (de originele bug).
    assert created[0]["sport_type"] == "Run"
    assert created[0]["start_time"] == "09:00:00"
    assert created[0]["load_target"] == 70
