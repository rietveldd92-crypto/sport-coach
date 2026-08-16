"""Volume-compensatie knipt in easy km, nooit in de sleutelsessie."""

from datetime import date

from agents import volume_compensation as vc


DREMPEL = {
    "sport": "Run", "type": "run_threshold_long",
    "naam": "Lange drempel - 3x15 min @ 4:25/km",
    "datum": "2026-07-31", "duur_min": 72, "km": 15.5, "tss_geschat": 137,
    "beschrijving": "Main Set\n3x\n- 15m 4:25/km Pace\n- 3m 64% Pace",
}
EASY = {
    "sport": "Run", "type": "run_z2_steady", "naam": "Z2 steady - 12km",
    "datum": "2026-08-01", "duur_min": 62, "km": 12.0, "tss_geschat": 55,
    "beschrijving": "- 62m 68% Pace",
}
LANG = {
    "sport": "Run", "type": "run_long", "naam": "Lange duurloop - 22km",
    "datum": "2026-08-02", "duur_min": 115, "km": 22.0, "tss_geschat": 130,
    "beschrijving": "- 115m 70% Pace",
}


def test_drempelsessie_telt_als_sleutelsessie():
    assert vc.is_key_session(DREMPEL)
    assert vc.is_key_session({"naam": "VO2max - 6x3m @ 112%"})
    assert vc.is_key_session({"type": "run_vo2max", "naam": "x"})


def test_easy_en_lange_duurloop_zijn_wel_inkortbaar():
    assert not vc.is_key_session(EASY)
    assert not vc.is_key_session(LANG)


def _overshoot_activities():
    """Een run van 25km waar 19km gepland stond — 6km overshoot."""
    return [{
        "type": "Run", "start_date_local": "2026-07-30T08:00:00",
        "distance": 25000, "moving_time": 7200, "icu_training_load": 158,
    }]


def test_overshoot_gaat_naar_easy_niet_naar_drempel():
    sessions = [DREMPEL, EASY, LANG]
    new, info = vc.apply(
        week_start=date(2026, 7, 27),
        sessions=sessions,
        activities=_overshoot_activities(),
        today=date(2026, 7, 30),
    )
    by_name = {s["naam"]: s for s in new}

    drempel = by_name["Lange drempel - 3x15 min @ 4:25/km"]
    assert drempel["duur_min"] == 72, "sleutelsessie mag niet ingekort worden"
    assert not drempel["naam"].startswith("[-")
    assert DREMPEL["naam"] in (info.get("beschermd") or [])

    ingekort = [c["naam"] for c in info["capped"]]
    assert all("drempel" not in n.lower() for n in ingekort)


def test_alleen_kwaliteit_over_dan_niet_compenseren():
    """Liever een paar km overshoot dan een halve sleutelsessie."""
    new, info = vc.apply(
        week_start=date(2026, 7, 27),
        sessions=[DREMPEL],
        activities=_overshoot_activities(),
        today=date(2026, 7, 30),
    )
    assert info["capped"] == []
    assert new[0]["duur_min"] == 72
    assert info.get("niet_gecompenseerd_km", 0) > 0


def test_apply_to_events_laat_drempel_event_staan():
    events = [
        {"id": "1", "type": "Run", "start_date_local": "2026-07-31T08:00:00",
         "name": "Lange drempel - 3x15 min @ 4:25/km", "moving_time": 72 * 60,
         "description": "Main Set\n3x\n- 15m 4:25/km Pace", "load_target": 137},
        {"id": "2", "type": "Run", "start_date_local": "2026-08-01T08:00:00",
         "name": "Z2 steady - 12km", "moving_time": 62 * 60,
         "description": "- 62m 68% Pace", "load_target": 55},
    ]
    updates = vc.apply_to_events(
        events=events,
        activities=_overshoot_activities(),
        week_start=date(2026, 7, 27),
        today=date(2026, 7, 30),
    )
    assert "1" not in [u["event_id"] for u in updates], \
        "drempel-event mag geen auto-inkorting krijgen"
