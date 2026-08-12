"""assess() bepaalt de trainingsmodus — de duurste beslissing in het systeem.

Deze functie had geen enkele test terwijl hij bepaalt of je volgende week
doorbouwt, consolideert of terugschakelt. De vijfde as (aerobe efficiëntie)
maakte dat urgenter: een metriek die weken kan stilzetten hoort vastgelegd.
"""

from datetime import date, timedelta

import pytest

import evaluate_week


GROEN = {
    "status": "groen", "flags": [], "active_signals": [],
    "strides_allowed": True, "tempo_allowed": True,
    "days_symptom_free": 30, "message": "GROEN",
}


def _review(**overrides) -> dict:
    basis = {
        "week_start": date(2026, 7, 27),
        "week_end": date(2026, 8, 2),
        "week_activities": [],
        "all_activities": [],
        "wellness": [],
        "aerobic": None,
        "week_tss": 500,
        "week_run_km": 50.0,
        "week_ride_km": 120.0,
        "run_count": 3,
        "ride_count": 3,
        "hrv_trend": "stabiel",
        "hrv_values": [],
        "signal_words": [],
    }
    basis.update(overrides)
    return basis


def _aerobic(slope, *, betrouwbaar, n=6, warme=0, temp_bekend=True) -> dict:
    metingen = [
        {"date": (date(2026, 6, 1) + timedelta(days=7 * i)).isoformat(),
         "pace_sec": 300 + i, "samples_sec": 600, "distance_km": 20.0,
         "temp_c": 18.0 if temp_bekend else None, "usable": True,
         "te_warm": False}
        for i in range(n)
    ]
    return {
        "hr_band": (142, 150), "metingen": metingen, "huidig": metingen[-1],
        "vorige": metingen[-2] if n >= 2 else None, "delta_sec": 1,
        "slope_sec_per_week": slope, "richting": "achteruit" if slope > 1 else "vooruit",
        "samenvatting": "Pace @ 142-150 bpm: 5:01/km.", "fouten": [],
        "temp_bekend": temp_bekend, "warme_metingen": warme,
        "betrouwbaar_voor_besluit": betrouwbaar,
    }


@pytest.fixture(autouse=True)
def _isoleer(monkeypatch, tmp_path):
    """Geen echte state, geen echte adherence-schrijfacties, geen API."""
    from agents import adherence, injury_guard, load_manager

    monkeypatch.setattr(evaluate_week, "_load_state",
                        lambda: {"load": {"ctl_estimate": 50.0}, "weekly_log": []})
    monkeypatch.setattr(injury_guard, "analyze", lambda **kw: dict(GROEN))
    monkeypatch.setattr(load_manager, "analyze", lambda **kw: {
        "ctl": 52.0, "atl": 60.0, "tsb": -8.0, "current_phase": "transformatie_I",
        "recommended_weekly_tss": 520, "overtraining_risk": "laag",
    })
    monkeypatch.setattr(adherence, "record_week", lambda *a, **kw: None)
    monkeypatch.setattr(adherence, "analyze", lambda **kw: {
        "band": "op_streef", "required_pct": 90, "weeks_counted": 4,
    })


def test_alles_op_orde_geeft_progressie():
    a = evaluate_week.assess(_review())
    assert a["modus"] == "PROGRESSIE"


def test_ctl_te_snel_geeft_consolidatie(monkeypatch):
    from agents import load_manager

    monkeypatch.setattr(load_manager, "analyze", lambda **kw: {
        "ctl": 60.0, "atl": 70.0, "tsb": -10.0, "current_phase": "transformatie_I",
        "recommended_weekly_tss": 520, "overtraining_risk": "hoog",
    })
    a = evaluate_week.assess(_review())
    assert a["modus"] == "CONSOLIDATIE"
    assert "CTL groeit te snel" in a["modus_reden"]


def test_blessuresignaal_geeft_terugschakelen():
    a = evaluate_week.assess(_review(), feedback="kniepijn bij km 5")
    assert a["modus"] == "TERUGSCHAKELEN"


# ── De vijfde as: aerobe efficiëntie ──────────────────────────────────────

def test_wegzakkende_efficientie_duwt_naar_consolidatie():
    a = evaluate_week.assess(_review(aerobic=_aerobic(3.0, betrouwbaar=True)))
    assert a["modus"] == "CONSOLIDATIE"
    assert "aerobe efficiëntie gaat achteruit" in a["modus_reden"]


def test_korte_reeks_mag_de_week_niet_stilzetten():
    """Een hittegolf of één rare run mag geen weekbesluit forceren."""
    a = evaluate_week.assess(_review(aerobic=_aerobic(3.0, betrouwbaar=False, n=3)))
    assert a["modus"] == "PROGRESSIE"
    assert any("te kort om er een weekbesluit" in n for n in a["coaching_notes"])


def test_verbeterende_efficientie_verandert_niets():
    a = evaluate_week.assess(_review(aerobic=_aerobic(-6.0, betrouwbaar=True)))
    assert a["modus"] == "PROGRESSIE"


def test_vlakke_trend_verandert_niets():
    a = evaluate_week.assess(_review(aerobic=_aerobic(0.5, betrouwbaar=True)))
    assert a["modus"] == "PROGRESSIE"


def test_samenvatting_landt_altijd_in_de_coaching_notes():
    a = evaluate_week.assess(_review(aerobic=_aerobic(-6.0, betrouwbaar=True)))
    assert any("Pace @ 142-150 bpm" in n for n in a["coaching_notes"])


def test_zonder_aerobe_data_blijft_assess_werken():
    a = evaluate_week.assess(_review(aerobic=None))
    assert a["modus"] == "PROGRESSIE"
    assert a["aerobic"] is None


def test_aerobic_gaat_mee_in_de_assessment():
    aerobic = _aerobic(-6.0, betrouwbaar=True)
    a = evaluate_week.assess(_review(aerobic=aerobic))
    assert a["aerobic"] is aerobic
