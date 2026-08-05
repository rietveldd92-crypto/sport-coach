"""Tests voor add_brick_for_tss_gap helper (week_planner)."""
from __future__ import annotations

from agents.week_planner import add_brick_for_tss_gap


def _run(dag: str, duur: int = 45, t: str = "recovery", naam: str = "Herstelrun – 45 min") -> dict:
    return {
        "dag": dag,
        "naam": naam,
        "beschrijving": "easy",
        "duur_min": duur,
        "tss_geschat": 35,
        "sport": "Run",
        "zone": "Z1",
        "type": t,
    }


def _bike(dag: str, duur: int = 80, t: str = "threshold", tss: int = 100) -> dict:
    return {
        "dag": dag,
        "naam": f"Fiets {t}",
        "beschrijving": "hard",
        "duur_min": duur,
        "tss_geschat": tss,
        "sport": "VirtualRide",
        "zone": "Z4",
        "type": t,
    }


def _long_run(dag: str = "zondag") -> dict:
    return {
        "dag": dag,
        "naam": "Lange duurloop – 24 km",
        "beschrijving": "long",
        "duur_min": 150,
        "tss_geschat": 120,
        "sport": "Run",
        "zone": "Z2",
        "type": "lange_duur",
    }


def test_gap_gt_120_voegt_bricks_toe():
    """Gap > 120 TSS → ten minste 1 brick wordt toegevoegd."""
    sessies = [
        _run("dinsdag"),
        _run("donderdag"),
        _bike("woensdag"),
        _long_run(),
    ]
    actual = sum(s["tss_geschat"] for s in sessies)
    result = add_brick_for_tss_gap(sessies, target_tss=actual + 180, actual_tss=actual)
    bricks = [s for s in result if s.get("is_brick")]
    assert len(bricks) >= 1
    # Bricks moeten op een korte-run-dag staan
    for b in bricks:
        assert b["dag"] in ("dinsdag", "donderdag", "woensdag", "maandag", "vrijdag", "zaterdag")


def test_gap_lt_80_geen_bricks():
    """Gap < 80 TSS → geen bricks toegevoegd."""
    sessies = [_run("dinsdag"), _bike("woensdag"), _long_run()]
    actual = sum(s["tss_geschat"] for s in sessies)
    result = add_brick_for_tss_gap(sessies, target_tss=actual + 60, actual_tss=actual)
    assert all(not s.get("is_brick") for s in result)


def test_deload_week_geen_bricks():
    """Deload-weken → geen bricks, ongeacht gap."""
    sessies = [_run("dinsdag"), _run("donderdag"), _long_run()]
    actual = sum(s["tss_geschat"] for s in sessies)
    result = add_brick_for_tss_gap(
        sessies, target_tss=actual + 300, actual_tss=actual, is_deload=True,
    )
    assert all(not s.get("is_brick") for s in result)


def test_max_2_bricks():
    """Harde cap: nooit meer dan 2 bricks per week."""
    sessies = [
        _run("maandag"), _run("dinsdag"), _run("woensdag"),
        _run("donderdag"), _run("vrijdag"), _long_run(),
    ]
    actual = sum(s["tss_geschat"] for s in sessies)
    result = add_brick_for_tss_gap(sessies, target_tss=actual + 500, actual_tss=actual)
    bricks = [s for s in result if s.get("is_brick")]
    assert len(bricks) <= 2


def test_brick_niet_op_dag_met_bestaande_fiets():
    """Bricks worden niet geplakt op dagen waar al een fietssessie staat."""
    sessies = [
        _run("dinsdag"),
        _bike("dinsdag", duur=60, t="easy_spin", tss=40),  # al fiets op di
        _run("donderdag"),
        _long_run(),
    ]
    actual = sum(s["tss_geschat"] for s in sessies)
    result = add_brick_for_tss_gap(sessies, target_tss=actual + 200, actual_tss=actual)
    bricks_op_di = [s for s in result if s.get("is_brick") and s["dag"] == "dinsdag"]
    assert len(bricks_op_di) == 0


def test_brick_niet_op_long_run_dag():
    """Bricks komen nooit op de long-run-dag."""
    sessies = [_run("dinsdag"), _run("donderdag"), _long_run("zondag")]
    actual = sum(s["tss_geschat"] for s in sessies)
    result = add_brick_for_tss_gap(sessies, target_tss=actual + 300, actual_tss=actual)
    bricks = [s for s in result if s.get("is_brick")]
    assert all(b["dag"] != "zondag" for b in bricks)
