from datetime import date, timedelta

import history_db
import shared
from agents import threshold_model


TODAY = date(2026, 7, 20)


def _seed_state(sec=255):
    shared.save_state({"threshold_pace_sec_per_km": sec})


def _obs(day_offset: int, activity_id: str, delta: int, hr_band: str,
         rpe: int | None = 6, completed: bool = True):
    return threshold_model.record_observation({
        "activity_id": activity_id,
        "date": (TODAY - timedelta(days=day_offset)).isoformat(),
        "pace_delta_sec": delta,
        "hr_vs_band": hr_band,
        "completed": completed,
    }, rpe=rpe)


def test_race_suggestion_formulas_muteren_niet():
    _seed_state(255)

    suggestion = threshold_model.suggest_from_race(5000, 20 * 60, today=TODAY)

    assert suggestion["old_sec"] == 255
    assert suggestion["proposed_sec"] == 256
    assert suggestion["source"] == "race"
    assert threshold_model.get_threshold_pace() == 255


def test_een_of_twee_snellere_observaties_geen_suggestie():
    _seed_state(255)
    _obs(1, "a1", -5, "onder", 6)
    _obs(2, "a2", -4, "in", 7)

    assert threshold_model.evaluate_trend(today=TODAY) is None
    assert history_db.get_pending_threshold_suggestion() is None


def test_drie_van_vier_sneller_met_lage_rpe_geeft_voorstel():
    _seed_state(255)
    _obs(1, "a1", -5, "onder", 6)
    _obs(2, "a2", -4, "in", 7)
    _obs(3, "a3", -3, "onder", 6)
    _obs(4, "a4", 1, "in", 8)

    suggestion = threshold_model.evaluate_trend(today=TODAY)

    assert suggestion is not None
    assert suggestion["old_sec"] == 255
    assert suggestion["proposed_sec"] == 252
    assert threshold_model.get_threshold_pace() == 255


def test_sneller_met_te_veel_ontbrekende_rpe_geen_suggestie():
    _seed_state(255)
    _obs(1, "a1", -5, "onder", None)
    _obs(2, "a2", -4, "in", None)
    _obs(3, "a3", -3, "onder", 6)
    _obs(4, "a4", 1, "in", 8)

    assert threshold_model.evaluate_trend(today=TODAY) is None


def test_drie_van_vier_langzamer_met_hr_boven_geeft_trager_voorstel():
    _seed_state(255)
    _obs(1, "a1", 6, "boven", 8)
    _obs(2, "a2", 5, "boven", 8)
    _obs(3, "a3", 0, "boven", 8, completed=False)
    _obs(4, "a4", -2, "in", 7)

    suggestion = threshold_model.evaluate_trend(today=TODAY)

    assert suggestion["proposed_sec"] == 258


def test_oude_observaties_tellen_niet_mee():
    _seed_state(255)
    _obs(1, "a1", -5, "onder", 6)
    _obs(2, "a2", -4, "in", 7)
    _obs(40, "old", -6, "onder", 6)

    assert threshold_model.evaluate_trend(today=TODAY) is None


def test_accept_muteert_logt_en_reset_observaties_en_cooldown():
    _seed_state(255)
    for i in range(4):
        _obs(i + 1, f"a{i}", -5, "onder", 6)
    suggestion = threshold_model.evaluate_trend(today=TODAY)

    resolved = threshold_model.resolve_suggestion(suggestion["id"], accepted=True)

    assert resolved["status"] == "accepted"
    assert threshold_model.get_threshold_pace() == 252
    assert history_db.list_threshold_pace_log()[-1]["new_sec"] == 252
    assert history_db.list_threshold_observations() == []
    _obs(1, "b1", -5, "onder", 6)
    _obs(2, "b2", -5, "onder", 6)
    _obs(3, "b3", -5, "onder", 6)
    assert threshold_model.evaluate_trend(today=TODAY + timedelta(days=1)) is None


def test_dismiss_reset_en_cooldown_zonder_mutatie():
    _seed_state(255)
    suggestion = threshold_model.suggest_from_race(10000, 42 * 60, today=TODAY)

    threshold_model.resolve_suggestion(suggestion["id"], accepted=False)

    assert threshold_model.get_threshold_pace() == 255
    assert history_db.list_threshold_observations() == []
    assert threshold_model.evaluate_trend(today=TODAY + timedelta(days=1)) is None


def test_bounds_pending_en_handmatige_set():
    _seed_state(255)

    log = threshold_model.set_threshold_pace(100, "test", "manual")
    assert log["new_sec"] == 220
    s1 = threshold_model.suggest_from_race(5000, 20 * 60, today=TODAY)
    s2 = threshold_model.suggest_from_race(5000, 19 * 60, today=TODAY)

    assert s1 is not None
    assert s2 is None


def test_rpe_roundtrip():
    row = threshold_model.record_rpe("act-1", 7, "2026-07-20")

    assert row["rpe"] == 7
    assert threshold_model.get_rpe("act-1")["date"] == "2026-07-20"
