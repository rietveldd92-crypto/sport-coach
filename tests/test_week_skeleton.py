from agents.week_skeleton import build_skeleton, build_skeleton_with_warnings


def _volume(
    *,
    week=15,
    long_km=17.0,
    short_km=8.0,
    run_intensity="drempel",
):
    return {
        "week": week,
        "fase": "transformatie_I",
        "run_km_totaal": 45.0,
        "run_sessies": 4,
        "korte_sessies": 3,
        "km_per_korte_sessie": short_km,
        "medium_sessies": 0,
        "km_per_medium_sessie": 0.0,
        "lange_duurloop_km": long_km,
        "fiets_sessies": 2,
        "run_intensiteit": run_intensity,
        "fiets_intensiteit": "toolkit",
    }


def _guard():
    return {
        "run_intensity_allowed": True,
        "tempo_allowed": True,
        "strides_allowed": True,
        "bike_intensity_allowed": True,
        "volume_modifier": 1.0,
    }


def _prefs(**extra):
    base = {
        "progression": {
            "run_quality_step": 2,
            "run_quality_variety_index": 0,
            "z2_run_variety_index": 0,
            "long_run_variety_index": 0,
        },
        "fourth_run_gate_open": False,
        "run_km_ceiling": 65,
    }
    base.update(extra)
    return base


def _fixed_commutes():
    return [
        {"weekday": 1, "name": "Forenzen-rit", "sport": "VirtualRide",
         "duration_min": 100, "if_estimate": 0.65, "enabled": True},
        {"weekday": 4, "name": "Forenzen-rit", "sport": "VirtualRide",
         "duration_min": 100, "if_estimate": 0.65, "enabled": True},
    ]


def _roles(slots):
    return [slot.rol for slot in slots]


def test_buildweek_heeft_twee_intervallen_long_en_commutes():
    slots = build_skeleton(
        15, _volume(week=15), _guard(), {"is_deload_week": False},
        _prefs(), _fixed_commutes(),
    )

    assert _roles(slots).count("interval_a") == 1
    assert _roles(slots).count("interval_b") == 1
    assert _roles(slots).count("long_run") == 1
    assert _roles(slots).count("commute") == 2

    interval_types = [s.sessie["type"] for s in slots if s.rol.startswith("interval")]
    assert interval_types[0].startswith("run_threshold")
    assert interval_types[1] == "run_vo2max"
    assert {s.vaste_dag for s in slots if s.rol == "commute"} == {"dinsdag", "vrijdag"}


def test_gate_kiest_juiste_quality_toolkit():
    guard = _guard()
    prefs = _prefs()

    tempoduur = build_skeleton(
        15, _volume(run_intensity="tempoduur"), guard,
        {"is_deload_week": False}, prefs, [],
    )
    assert [s.sessie["type"] for s in tempoduur if s.rol.startswith("interval")] == [
        "run_threshold_long", "run_speed",
    ]

    race = build_skeleton(
        15, {**_volume(), "run_intensiteit": "race_specifiek"}, guard,
        {"is_deload_week": False}, prefs, [],
    )
    race_types = [s.sessie["type"] for s in race if s.rol.startswith("interval")]
    assert race_types[0] == "run_marathon"
    assert race_types[1].startswith("run_threshold")


def test_deloadweek_heeft_een_interval():
    slots = build_skeleton(
        15, _volume(week=15), _guard(), {"is_deload_week": True},
        _prefs(), _fixed_commutes(),
    )

    assert _roles(slots).count("interval_a") == 1
    assert "interval_b" not in _roles(slots)
    assert _roles(slots).count("long_run") == 1


def test_vierde_loopdag_pas_met_gate_en_km_ruimte():
    closed = build_skeleton(
        17, _volume(week=17, long_km=22), _guard(), {"is_deload_week": False},
        _prefs(fourth_run_gate_open=False), [],
    )
    open_ = build_skeleton(
        17, _volume(week=17, long_km=22), _guard(), {"is_deload_week": False},
        _prefs(fourth_run_gate_open=True), [],
    )

    assert "easy_run" not in _roles(closed)
    assert _roles(open_).count("easy_run") == 1


def test_km_ceiling_laat_easy_vallen_en_overschrijdt_niet():
    slots, warnings = build_skeleton_with_warnings(
        17, _volume(week=17, long_km=50, short_km=10), _guard(),
        {"is_deload_week": False},
        _prefs(fourth_run_gate_open=True, run_km_ceiling=65),
        [],
    )

    assert "easy_run" not in _roles(slots)
    assert any(w["code"] == "easy_run_dropped_ceiling" for w in warnings)
    run_meta = [
        s.sessie.get("_skeleton", {}) for s in slots
        if s.sessie.get("sport") == "Run"
    ]
    assert run_meta
    assert all(m["planned_run_km"] <= 65 for m in run_meta)


def test_geen_run_korter_dan_45_minuten():
    slots = build_skeleton(
        17, _volume(week=17, long_km=18, short_km=4), _guard(),
        {"is_deload_week": False},
        _prefs(fourth_run_gate_open=True),
        [],
    )

    runs = [s.sessie for s in slots if s.sessie.get("sport") == "Run"]
    assert runs
    assert all(r["duur_min"] >= 45 for r in runs)


def test_bike_fill_geen_threshold_bij_twee_intervallen():
    slots = build_skeleton(
        15, _volume(week=15), _guard(), {"is_deload_week": False},
        _prefs(), [],
    )

    bike_types = {s.sessie["type"] for s in slots if s.rol == "bike_fill"}
    assert bike_types
    assert "threshold" not in bike_types
    assert "sweetspot" not in bike_types


def test_fixed_sessions_uit_db_vormen_commute_slots():
    import history_db

    history_db.upsert_fixed_session(
        1,
        name="Forenzen-rit",
        sport="VirtualRide",
        duration_min=100,
        if_estimate=0.65,
        enabled=True,
    )
    slots = build_skeleton(
        15, _volume(week=15), _guard(), {"is_deload_week": False},
        _prefs(), history_db.list_fixed_sessions(),
    )

    commutes = [s for s in slots if s.rol == "commute"]
    assert len(commutes) == 1
    assert commutes[0].vaste_dag == "dinsdag"
    assert commutes[0].sessie["duur_min"] == 100


# ── Epoch-onafhankelijkheid (bug 2026-07-12) ───────────────────────────────
# Het plan-weeknummer herstart bij elke (her)generatie van het macroplan.
# Het geraamte mag daar dus nooit ontwikkelingsbeslissingen aan koppelen:
# na een planherstart verdween de 2e intervalsessie en viel de kwaliteit
# terug op instap-workouts.

def test_twee_intervallen_ook_bij_laag_plan_weeknummer():
    slots = build_skeleton(
        2, _volume(week=2), _guard(), {"is_deload_week": False},
        _prefs(), [],
    )

    assert _roles(slots).count("interval_a") == 1
    assert _roles(slots).count("interval_b") == 1


def test_fallback_quality_step_volgt_gate_niet_weeknummer():
    prefs = _prefs()
    del prefs["progression"]["run_quality_step"]

    drempel = build_skeleton(
        2, _volume(week=2), _guard(), {"is_deload_week": False}, prefs, [],
    )
    basis = build_skeleton(
        2, _volume(week=2, run_intensity="geen"), _guard(),
        {"is_deload_week": False}, prefs, [],
    )

    # Gate drempel → middentrede (3); gate geen → instap (1). Zonder deze
    # fallback zakte een marathonatleet na een planherstart terug naar 5x1km.
    drempel_tss = [s.sessie["tss_geschat"] for s in drempel if s.rol == "interval_a"][0]
    basis_tss = [s.sessie["tss_geschat"] for s in basis if s.rol == "interval_a"][0]
    assert drempel_tss > basis_tss


def test_bike_fill_genoeg_voor_volle_week():
    slots = build_skeleton(
        15, _volume(week=15), _guard(), {"is_deload_week": False},
        _prefs(), [],
    )

    fills = [s for s in slots if s.rol == "bike_fill"]
    # 7 dagen − 3 runs = 4 potentiële fietsdagen; de assigner laat vallen
    # wat niet past, maar het geraamte mag dagen niet structureel leeg laten.
    assert len(fills) >= 4
