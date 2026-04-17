"""Tests voor de TSS/duur-window filter in get_swap_options.

Doel: een 2,5u long run (150 TSS) mag niet stilletjes vervangen worden
door een 45-min recovery (30 TSS). Het window-filter moet dat blokkeren.
"""
from __future__ import annotations

import pytest

from agents import workout_library as lib


def _run_event(name: str, tss: float, minutes: int) -> dict:
    return {
        "type": "Run",
        "name": name,
        "load_target": tss,
        "moving_time": minutes * 60,
    }


def _bike_event(name: str, tss: float, minutes: int) -> dict:
    return {
        "type": "VirtualRide",
        "name": name,
        "load_target": tss,
        "moving_time": minutes * 60,
    }


# ── Fix 2a: TSS-window filter ─────────────────────────────────────────────


def test_long_run_vergelijkbaar_blijft_long_run():
    """Een 150 TSS long run krijgt geen 45min recovery als 'vergelijkbaar'."""
    evt = _run_event("Lange duurloop 22km", tss=150, minutes=150)
    opts = lib.get_swap_options(evt, "vergelijkbaar", ftp=290)

    assert len(opts) > 0, "moet opties hebben"
    lo, hi = 150 * 0.75, 150 * 1.25
    for o in opts:
        tss = o.get("tss_geschat") or 0
        assert lo <= tss <= hi, (
            f"Optie buiten vergelijkbaar-window: {o['naam']} {tss} TSS"
        )


def test_tempo_makkelijker_heeft_geen_zwaardere_workouts():
    """'Makkelijker' mag niet zwaarder zijn dan origineel."""
    evt = _run_event("Tempo 60 min", tss=80, minutes=60)
    opts = lib.get_swap_options(evt, "makkelijker", ftp=290)

    assert len(opts) > 0
    for o in opts:
        tss = o.get("tss_geschat") or 0
        assert tss <= 80, f"Makkelijker optie zwaarder dan origineel: {o['naam']} {tss}"


def test_harder_blijft_boven_origineel():
    """'Harder' mag niet veel lichter zijn — min widening toegestaan."""
    evt = _run_event("Tempo 60 min", tss=80, minutes=60)
    opts = lib.get_swap_options(evt, "harder", ftp=290)

    assert len(opts) > 0
    # Na widening kunnen iets lichtere options sluipen, maar niet extreem.
    # Hard grens: niet onder 50% van origineel.
    for o in opts:
        tss = o.get("tss_geschat") or 0
        assert tss >= 80 * 0.5, f"Harder optie veel te licht: {o['naam']} {tss}"


def test_geen_load_target_geen_filter():
    """Zonder load_target skippen we de hard filter (legacy gedrag)."""
    evt = {"type": "Run", "name": "Tempo 60 min", "load_target": None}
    opts = lib.get_swap_options(evt, "vergelijkbaar", ftp=290)
    assert len(opts) > 0  # zonder filter zijn er gewoon opties


def test_widening_voor_extreme_tss():
    """Ultra-high TSS (300) zou zonder widening 0 opties geven — laat
    zien dat de widening-logica werkt door uiteindelijk iets te retourneren
    (desnoods 0 als geen enkele variant past)."""
    evt = _run_event("Imaginary ultra", tss=300, minutes=240)
    opts = lib.get_swap_options(evt, "vergelijkbaar", ftp=290)
    # We eisen niet dat er opties zijn — enkel dat het geen crash is.
    assert isinstance(opts, list)


def test_sort_prioriteert_dichtstbij_origineel():
    """Zonder target_tss: eerste optie moet dichtst bij origineel TSS zijn."""
    evt = _bike_event("Endurance 90min", tss=90, minutes=90)
    opts = lib.get_swap_options(evt, "vergelijkbaar", ftp=290, target_tss=None)

    assert len(opts) >= 2
    first_dist = abs((opts[0].get("tss_geschat") or 0) - 90)
    last_dist = abs((opts[-1].get("tss_geschat") or 0) - 90)
    assert first_dist <= last_dist


# ── _event_duration_min helper ────────────────────────────────────────────


def test_duration_van_moving_time():
    assert lib._event_duration_min({"moving_time": 3600}) == 60


def test_duration_van_naam():
    assert lib._event_duration_min({"name": "Z2 90 min easy"}) == 90


def test_duration_km_naam_geeft_none():
    """'22km' mag niet geïnterpreteerd worden als 22 minuten."""
    assert lib._event_duration_min({"name": "Lange duurloop 22km"}) is None


def test_duration_onbekend():
    assert lib._event_duration_min({"name": "foo"}) is None
    assert lib._event_duration_min({}) is None


# ── _apply_tss_window ─────────────────────────────────────────────────────


def test_apply_tss_window_filtert():
    opts = [
        {"tss_geschat": 30},
        {"tss_geschat": 80},
        {"tss_geschat": 100},
        {"tss_geschat": 120},
        {"tss_geschat": 200},
    ]
    filtered, widen = lib._apply_tss_window(opts, "vergelijkbaar", orig_tss=100)
    # Window 75-125, widen=0 moet 80, 100, 120 overhouden (3 opties exact)
    tss_vals = sorted((o["tss_geschat"] for o in filtered))
    assert 80 in tss_vals and 100 in tss_vals and 120 in tss_vals
    assert 30 not in tss_vals and 200 not in tss_vals
    assert widen == 0.0


def test_apply_tss_window_widens_bij_te_weinig_opties():
    """Als window te strak is, moet widening intredden."""
    opts = [
        {"tss_geschat": 50},
        {"tss_geschat": 160},
    ]
    filtered, widen = lib._apply_tss_window(opts, "vergelijkbaar", orig_tss=100)
    # Exact window 75-125 → 0 opties → widen tot beide pakken
    assert len(filtered) >= 1
    assert widen > 0.0


def test_apply_tss_window_skipt_bij_geen_tss():
    opts = [{"tss_geschat": 10}, {"tss_geschat": 500}]
    filtered, widen = lib._apply_tss_window(opts, "vergelijkbaar", orig_tss=0)
    assert filtered == opts
    assert widen == 0.0


# ── predict_week_tss (in app.py) ──────────────────────────────────────────


def test_predict_week_tss_telt_done_plus_planned_plus_new():
    # app.predict_week_tss is puur functie — isoleerbaar testen
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
    # Gebruik directe import, geen Streamlit side-effects
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_swap_app_helpers", str(__import__("pathlib").Path(__file__).parent.parent / "app.py")
    )
    # Kan Streamlit importeren falen — skippen als dat zo is
    try:
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception:
        pytest.skip("app.py vereist Streamlit runtime")
        return

    matched = [
        {"event": {"id": "1"}, "done": True,
         "activity": {"icu_training_load": 50}},
        {"event": {"id": "2", "load_target": 40}, "done": False, "activity": None},
        {"event": {"id": "3", "load_target": 60}, "done": False, "activity": None},
    ]
    # Swap event id=3 met nieuwe TSS 80 → 50 (done) + 40 (other planned) + 80 = 170
    result = mod.predict_week_tss(matched, "3", 80)
    assert result == 170
