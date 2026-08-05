from datetime import date, timedelta

import history_db
import shared
from agents import feedback_engine
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
    _obs(3, "a3", -4, "onder", 6)
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
    _obs(3, "a3", -4, "onder", 6)
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


def test_afgebroken_snelle_reps_tellen_nooit_als_vooruitgang():
    _seed_state(255)
    _obs(1, "a1", -6, "in", 6, completed=False)
    _obs(2, "a2", -5, "in", 6, completed=False)
    _obs(3, "a3", -4, "onder", 6, completed=False)

    assert threshold_model.evaluate_trend(today=TODAY) is None


def test_min_drie_seconden_is_on_target_en_niet_ook_sneller():
    observation = {
        "pace_delta_sec": -3,
        "hr_vs_band": "in",
        "rpe": 6,
        "completed": True,
    }

    assert threshold_model._on_target(observation) is True
    assert threshold_model._is_faster_signal(observation) is False


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


# ── observatie-keten: activiteit -> metrics -> observatie -> trend ─────────

def _threshold_event(name="Korte drempel - 5x1km @ 4:15/km"):
    return {"type": "Run", "name": name, "description": "Drempelpace: 4:15/km"}


def _analysis(delta: int, hr: int, wtype="run_tempo"):
    """Wat workout_analysis oplevert voor een drempelsessie."""
    return {
        "workout_type": wtype,
        "metrics": {
            "pace_delta_sec": delta,
            "interval_hr_avg": hr,
            "target_pace_sec": 255,
            "observed_pace_sec": 255 + delta,
            "hr_avg": 130,
        },
    }


def test_observe_from_workout_legt_pace_en_hr_band_vast():
    _seed_state(255)
    # Midden in de drempelband, afgeleid van de referentiewaarden — een hard
    # getal zou stilletjes "onder" gaan betekenen zodra HRmax bijgesteld wordt.
    in_band = (feedback_engine.THRESHOLD_HR_MIN
               + feedback_engine.THRESHOLD_HR_MAX) // 2

    obs = threshold_model.observe_from_workout(
        _threshold_event(), {"id": 900, "start_date_local": "2026-07-20T07:00:00"},
        _analysis(-5, in_band),
    )

    assert obs["pace_delta_sec"] == -5
    assert obs["observed_pace_sec"] == 250
    assert obs["target_pace_sec"] == 255
    # HR uit de reps, niet het activiteitsgemiddelde (130) — anders zou elke
    # intervalsessie als "onder de band" gelden.
    assert obs["hr_reps_avg"] == in_band
    assert obs["hr_vs_band"] == "in"


def test_observe_from_workout_pakt_garmin_rpe_als_de_app_er_geen_heeft():
    _seed_state(255)

    obs = threshold_model.observe_from_workout(
        _threshold_event(),
        {"id": 903, "start_date_local": "2026-07-20T07:00:00", "icu_rpe": 8},
        _analysis(6, 180),
    )

    assert obs["rpe"] == 8


def test_observe_from_workout_negeert_niet_drempelsessies():
    _seed_state(255)

    vo2 = threshold_model.observe_from_workout(
        {"type": "Run", "name": "VO2max - 10x60s @ 106%"},
        {"id": 901}, _analysis(-8, 180, wtype="run_vo2max"),
    )
    bike = threshold_model.observe_from_workout(
        {"type": "Ride", "name": "Threshold 3x10 min @ 100%"},
        {"id": 902}, _analysis(-8, 180, wtype="bike_threshold"),
    )

    assert vo2 is None
    assert bike is None
    assert history_db.list_threshold_observations() == []


def test_rpe_backfill_vult_bestaande_observatie_en_deblokkeert_trend():
    _seed_state(255)
    # Observaties komen binnen via de nachtelijke feedback-run, dus zonder RPE.
    for i in range(3):
        threshold_model.observe_from_workout(
            _threshold_event(), {"id": 910 + i,
                                 "start_date_local": f"2026-07-1{7 + i}T07:00:00"},
            _analysis(-5, 170),
        )
    assert threshold_model.evaluate_trend(today=TODAY) is None

    for i in range(3):
        threshold_model.record_rpe(str(910 + i), 6)

    observations = history_db.list_threshold_observations()
    assert all(o["rpe"] == 6 for o in observations)
    suggestion = history_db.get_pending_threshold_suggestion()
    assert suggestion is not None
    assert suggestion["proposed_sec"] == 252


def test_accept_vraagt_om_herplan_want_paces_staan_in_het_plan():
    _seed_state(255)
    suggestion = threshold_model.suggest_from_race(5000, 19 * 60, today=TODAY)

    resolved = threshold_model.resolve_suggestion(suggestion["id"], accepted=True)

    assert resolved["replan_needed"] is True


def test_dismiss_vraagt_niet_om_herplan():
    _seed_state(255)
    suggestion = threshold_model.suggest_from_race(5000, 19 * 60, today=TODAY)

    resolved = threshold_model.resolve_suggestion(suggestion["id"], accepted=False)

    assert resolved["replan_needed"] is False


# ── ONBETROUWBARE HARTSLAG (polsmeting) ────────────────────────────────────

def _obs_zonder_hr(day_offset: int, activity_id: str, delta: int,
                   rpe: int | None, completed: bool = True):
    """Observatie uit een sessie waarvan de HR-meting niet deugde."""
    return threshold_model.record_observation({
        "activity_id": activity_id,
        "date": (TODAY - timedelta(days=day_offset)).isoformat(),
        "pace_delta_sec": delta,
        "hr_reps_avg": 164,      # de meting bestáát, maar klopt niet
        "hr_reliable": False,
        "completed": completed,
    }, rpe=rpe)


def test_onbetrouwbare_hr_wordt_niet_als_band_vastgelegd():
    """Een spookmeting mag niet als feit in het dossier belanden."""
    _seed_state(255)

    obs = _obs_zonder_hr(1, "a1", -5, 6)

    assert obs["hr_vs_band"] is None


def test_zonder_hr_beslissen_pace_en_rpe_samen():
    """Drie snelle sessies op lage RPE tellen ook zonder bruikbare hartslag."""
    _seed_state(255)
    _obs_zonder_hr(1, "a1", -5, 6)
    _obs_zonder_hr(2, "a2", -4, 7)
    _obs_zonder_hr(3, "a3", -4, 6)

    suggestion = threshold_model.evaluate_trend(today=TODAY)

    assert suggestion is not None
    assert suggestion["proposed_sec"] == 252


def test_zonder_hr_en_zonder_rpe_geen_voorstel():
    """Pace alleen is te dun: sneller lopen zegt niets zonder wat het kostte."""
    _seed_state(255)
    _obs_zonder_hr(1, "a1", -5, None)
    _obs_zonder_hr(2, "a2", -4, None)
    _obs_zonder_hr(3, "a3", -3, None)

    assert threshold_model.evaluate_trend(today=TODAY) is None


def test_zonder_hr_stuurt_hoge_rpe_bij_trage_sessies_de_drempel_omhoog():
    _seed_state(255)
    _obs_zonder_hr(1, "a1", 6, 9)
    _obs_zonder_hr(2, "a2", 7, 8)
    _obs_zonder_hr(3, "a3", 5, 9)

    suggestion = threshold_model.evaluate_trend(today=TODAY)

    assert suggestion is not None
    assert suggestion["proposed_sec"] == 258


# ── HARTSLAGDRIFT: opbouw op vaste pace ────────────────────────────────────
#
# Bij opbouw op één vaste pace staat de pace-delta per definitie stil. Zonder
# drift heeft het model dan geen enkel signaal en blijft de drempel eeuwig op
# dezelfde waarde staan, hoe hard de atleet ook vooruit gaat.

IN_BAND = (feedback_engine.THRESHOLD_HR_MIN
           + feedback_engine.THRESHOLD_HR_MAX) // 2


def _obs_drift(day_offset: int, activity_id: str, drift: float,
               delta: int = 0, rpe: int | None = 6, hr: int = IN_BAND,
               completed: bool = True, work_time: int = 36):
    return threshold_model.record_observation({
        "activity_id": activity_id,
        "date": (TODAY - timedelta(days=day_offset)).isoformat(),
        "pace_delta_sec": delta,
        "hr_reps_avg": hr,
        "hr_drift_bpm": drift,
        "work_time_min": work_time,
        "completed": completed,
    }, rpe=rpe)


def test_drift_en_werktijd_landen_in_de_observatie():
    _seed_state(262)

    obs = threshold_model.observe_from_workout(
        _threshold_event("Lange drempel - 3x12 min @ 4:22/km"),
        {"id": 950, "start_date_local": "2026-07-20T07:00:00"},
        {"workout_type": "run_tempo", "metrics": {
            "pace_delta_sec": -2, "interval_hr_avg": IN_BAND,
            "target_pace_sec": 262, "observed_pace_sec": 260,
            "hr_drift_bpm": 6, "work_time_min": 36,
        }},
    )

    assert obs["hr_drift_bpm"] == 6
    assert obs["work_time_min"] == 36


def test_onbetrouwbare_hr_levert_geen_drift():
    """Drift uit een spookmeting is erger dan geen drift: het lijkt een feit."""
    _seed_state(262)

    obs = threshold_model.observe_from_workout(
        _threshold_event("Lange drempel - 3x12 min @ 4:22/km"),
        {"id": 951, "start_date_local": "2026-07-20T07:00:00"},
        {"workout_type": "run_tempo", "metrics": {
            "pace_delta_sec": 0, "interval_hr_avg": IN_BAND,
            "target_pace_sec": 262, "observed_pace_sec": 262,
            "hr_drift_bpm": 2, "work_time_min": 36, "hr_reliable": False,
        }},
    )

    assert obs["hr_drift_bpm"] is None


def test_vlakke_drift_op_target_stelt_snellere_drempel_voor():
    """Pace-delta 0 in alle drie: alleen drift kan dit signaal geven."""
    _seed_state(262)
    _obs_drift(3, "d1", 3)
    _obs_drift(2, "d2", 2)
    _obs_drift(1, "d3", 1)

    suggestion = threshold_model.evaluate_trend(today=TODAY)

    assert suggestion is not None
    assert suggestion["proposed_sec"] == 259
    assert suggestion["source"] == "drift_trend"
    assert threshold_model.get_threshold_pace() == 262  # nooit muteren


def test_doorklimmende_drift_op_target_stelt_tragere_drempel_voor():
    _seed_state(262)
    _obs_drift(3, "d1", 8)
    _obs_drift(2, "d2", 9)
    _obs_drift(1, "d3", 11)

    suggestion = threshold_model.evaluate_trend(today=TODAY)

    assert suggestion is not None
    assert suggestion["proposed_sec"] == 265
    assert suggestion["source"] == "drift_trend"


def test_grijze_drift_geeft_geen_voorstel():
    """4-7 bpm is niet te onderscheiden van een warme dag of slechte nacht."""
    _seed_state(262)
    _obs_drift(3, "d1", 4)
    _obs_drift(2, "d2", 6)
    _obs_drift(1, "d3", 7)

    assert threshold_model.evaluate_trend(today=TODAY) is None


def test_vlakke_drift_telt_niet_als_de_sessie_te_traag_liep():
    """Anders koop je een 'vooruitgang' door simpelweg rustiger te lopen."""
    _seed_state(262)
    _obs_drift(3, "d1", 1, delta=9)
    _obs_drift(2, "d2", 2, delta=8)
    _obs_drift(1, "d3", 1, delta=10)

    suggestion = threshold_model.evaluate_trend(today=TODAY)

    # Wel een trager-signaal (de bestaande regel), nooit een sneller-signaal.
    assert suggestion is None or suggestion["proposed_sec"] > 262


def test_vlakke_drift_met_hoge_rpe_versnelt_niet():
    """Hartslag zegt rustig, atleet zegt zwaar — dan wint de atleet."""
    _seed_state(262)
    _obs_drift(3, "d1", 2, rpe=8)
    _obs_drift(2, "d2", 1, rpe=9)
    _obs_drift(1, "d3", 2, rpe=8)

    assert threshold_model.evaluate_trend(today=TODAY) is None


def test_vlakke_drift_boven_de_band_versnelt_niet():
    _seed_state(262)
    boven = feedback_engine.THRESHOLD_HR_MAX + 5
    _obs_drift(3, "d1", 2, hr=boven)
    _obs_drift(2, "d2", 1, hr=boven)
    _obs_drift(1, "d3", 2, hr=boven)

    assert threshold_model.evaluate_trend(today=TODAY) is None


def test_drift_context_beschrijft_de_richting():
    _seed_state(262)
    _obs_drift(3, "d1", 6)
    _obs_drift(2, "d2", 4)
    _obs_drift(1, "d3", 3)

    context = threshold_model.threshold_context()

    assert [row["drift_bpm"] for row in context["drift_series"]] == [6, 4, 3]
    assert "zakt bij gelijk tempo" in context["drift_sentence"]


def test_drift_context_zonder_metingen_legt_uit_wat_er_nodig_is():
    _seed_state(262)

    context = threshold_model.threshold_context()

    assert context["drift_series"] == []
    assert "Nog geen bruikbare driftmeting" in context["drift_sentence"]
