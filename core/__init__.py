"""core/ — pure planner-services (UPGRADE_PLAN §2).

Fase 1: availability_v2 (tijdvensters), slot_solver (CP-SAT) en replan
(minimale verschuiving bij beschikbaarheidswijziging).
"""
from __future__ import annotations


def planner_v2_enabled() -> bool:
    """Feature flag PLANNER_V2 (default aan).

    Uitzetten: PLANNER_V2=0 in .env / secrets.toml → legacy day_planner-pad.
    """
    import config

    raw = config.get_secret("PLANNER_V2", default="1")
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}
