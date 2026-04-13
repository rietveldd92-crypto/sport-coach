"""Tests voor agents.adjustments_log."""
from datetime import date

import pytest

from agents import adjustments_log as log
from agents.models import AdaptResult, Deviation, Modification


@pytest.fixture
def tmp_log(tmp_path):
    return tmp_path / "adjustments_log.json"


def test_append_creates_file(tmp_log):
    result = AdaptResult(narrative="test", invariant="inv")
    entry = log.build_entry(date(2026, 4, 13), [], result)
    log.append(entry, path=tmp_log)
    assert tmp_log.exists()
    all_entries = log.get_all(path=tmp_log)
    assert len(all_entries) == 1
    assert all_entries[0]["narrative"] == "test"


def test_get_active_returns_none_initially(tmp_log):
    assert log.get_active(path=tmp_log) is None


def test_get_active_returns_latest_non_dismissed(tmp_log):
    r1 = AdaptResult(narrative="oud", invariant="inv1")
    r2 = AdaptResult(narrative="nieuw", invariant="inv2")
    e1 = log.append(log.build_entry(date(2026, 4, 6), [], r1), path=tmp_log)
    log.append(log.build_entry(date(2026, 4, 13), [], r2), path=tmp_log)
    active = log.get_active(path=tmp_log)
    assert active["narrative"] == "nieuw"

    log.mark_dismissed(active["id"], path=tmp_log)
    active2 = log.get_active(path=tmp_log)
    assert active2["id"] == e1["id"]


def test_mark_reverted(tmp_log):
    r = AdaptResult(narrative="x", invariant="y")
    entry = log.append(log.build_entry(date(2026, 4, 13), [], r), path=tmp_log)
    assert log.mark_reverted(entry["id"], path=tmp_log)
    active = log.get_active(path=tmp_log)
    assert active is None


def test_build_entry_met_deviations_en_modifications():
    devs = [Deviation(type="skipped", planned_event_id="e1", tss_planned=120)]
    mods = [Modification(event_id="e1", action="create", reason="sacred herplanning")]
    result = AdaptResult(modifications=mods, narrative="ok", invariant="CTL oké")
    entry = log.build_entry(date(2026, 4, 13), devs, result)
    assert entry["week_start"] == "2026-04-13"
    assert len(entry["deviations"]) == 1
    assert len(entry["modifications"]) == 1
    assert entry["applied"] is True
    assert entry["dismissed"] is False
    assert entry["reverted"] is False


def test_mark_dismissed_nonexistent(tmp_log):
    assert log.mark_dismissed("not-an-id", path=tmp_log) is False
