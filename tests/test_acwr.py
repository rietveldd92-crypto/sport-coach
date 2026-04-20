"""Tests voor ACWR-berekening in load_manager.compute_acwr."""
from agents.load_manager import compute_acwr


def test_sweet_spot():
    # ATL gelijk aan CTL → ratio 1.0, midden van sweet spot
    r = compute_acwr(ctl=50.0, atl=50.0)
    assert r["acwr"] == 1.0
    assert r["zone"] == "sweet"


def test_detrained_when_atl_drops():
    r = compute_acwr(ctl=60.0, atl=40.0)
    assert r["acwr"] < 0.8
    assert r["zone"] == "detrained"


def test_elevated_zone():
    # 1.35 > 1.30 maar < 1.50 → elevated voor normale atleet
    r = compute_acwr(ctl=50.0, atl=67.5)
    assert r["zone"] == "elevated"


def test_high_zone():
    r = compute_acwr(ctl=40.0, atl=65.0)  # 1.625
    assert r["zone"] == "high"


def test_injury_return_stricter_thresholds():
    # 1.25: sweet voor normale atleet, elevated bij injury-return
    normal = compute_acwr(ctl=40.0, atl=50.0)
    injured = compute_acwr(ctl=40.0, atl=50.0, injury_return=True)
    assert normal["zone"] == "sweet"
    assert injured["zone"] == "elevated"


def test_injury_return_high_threshold_stricter():
    # 1.40: elevated voor normale atleet, high bij injury-return
    normal = compute_acwr(ctl=40.0, atl=56.0)
    injured = compute_acwr(ctl=40.0, atl=56.0, injury_return=True)
    assert normal["zone"] == "elevated"
    assert injured["zone"] == "high"


def test_zero_ctl_returns_unknown():
    r = compute_acwr(ctl=0.0, atl=20.0)
    assert r["zone"] == "unknown"
    assert r["acwr"] == 0.0


def test_negative_ctl_returns_unknown():
    r = compute_acwr(ctl=-5.0, atl=10.0)
    assert r["zone"] == "unknown"


def test_message_includes_ratio():
    r = compute_acwr(ctl=50.0, atl=60.0)
    assert "1.20" in r["message"]


def test_current_dennis_state_is_sweet():
    # Werkelijke waarden uit state.json ~ 2026-04-20: CTL 52.9, ATL 57.6
    r = compute_acwr(ctl=52.9, atl=57.6, injury_return=True)
    # 57.6/52.9 = 1.089 → sweet (< 1.20 injury-strict)
    assert r["zone"] == "sweet"
    assert 1.05 < r["acwr"] < 1.15
