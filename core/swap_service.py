"""Swap-service — gedeelde swap-logica voor app.py (Streamlit) en api/ (Fase 3).

Geëxtraheerd uit app.py zodat de FastAPI-laag exact dezelfde flow
gebruikt (UPGRADE_PLAN §7, POST /api/placements/{event_id}/swap) zonder
duplicatie. app.py importeert deze functies en doet er alleen nog
Streamlit-presentatie (flash/undo) en TP-propagatie omheen.
"""
from __future__ import annotations

import random
from typing import Optional

DEFAULT_FTP = 290

# Variatie-poolgrootte: bij TSS-sorting top-5, bij random top-3 (legacy).
POOL_WITH_TARGET = 5
POOL_RANDOM = 3

IDEAL_TSS_MIN = 30.0
IDEAL_TSS_MAX = 200.0


def resolve_phase_tss_range() -> Optional[tuple[float, float]]:
    """TSS-band van de huidige fase uit de periodizer (plan_provider).

    Returnt (min, max) of None als de periodizer faalt. Gebruikt als
    post-swap sanity check: valt de week na swap buiten deze band, dan
    hoort daar een waarschuwing bij.
    """
    try:
        from agents.marathon_periodizer import get_current_phase
        phase = get_current_phase()
        band = phase.get("tss_doel")
        if band and isinstance(band, (tuple, list)) and len(band) == 2:
            return (float(band[0]), float(band[1]))
    except Exception:
        pass
    return None


def predict_week_tss(matched: list, current_event_id, new_tss: float) -> float:
    """Voorspel het week-TSS-totaal na een swap van ``current_event_id``.

    = done TSS (voltooide activities) + overige planned TSS + nieuwe TSS.
    """
    done_tss = 0.0
    other_planned_tss = 0.0
    cur_id = str(current_event_id)
    for item in matched:
        event = item.get("event", {})
        eid = str(event.get("id", ""))
        if item.get("done") and item.get("activity"):
            done_tss += item["activity"].get("icu_training_load") or 0
        elif eid != cur_id:
            other_planned_tss += event.get("load_target") or 0
    return done_tss + other_planned_tss + (new_tss or 0)


def compute_ideal_tss(matched: list, current_event_id, weekly_target: float) -> float:
    """Hoeveel TSS deze ene workout 'idealiter' zou moeten leveren.

    Weekelijks TSS-target minus voltooid minus elders gepland; clamp
    [30, 200] tegen extreme targets bij lege of overvolle weken.
    """
    done_tss = 0.0
    other_planned_tss = 0.0
    current_id = str(current_event_id)

    for item in matched:
        event = item.get("event", {})
        eid = str(event.get("id", ""))
        if item.get("done") and item.get("activity"):
            done_tss += item["activity"].get("icu_training_load") or 0
        elif eid != current_id:
            other_planned_tss += event.get("load_target") or 0

    ideal = weekly_target - done_tss - other_planned_tss
    return max(IDEAL_TSS_MIN, min(IDEAL_TSS_MAX, ideal))


def build_phase_warning(matched: Optional[list], event_id, new_tss: float,
                        phase_tss_range: Optional[tuple[float, float]]) -> str:
    """Waarschuwing als het week-totaal na swap buiten de fase-band valt."""
    if matched is None or not phase_tss_range:
        return ""
    week_total = predict_week_tss(matched, event_id, new_tss)
    lo, hi = phase_tss_range
    if week_total < lo:
        tekort = lo - week_total
        return (f" · ⚠ week {week_total:.0f} TSS < fase-min {lo:.0f} "
                f"(−{tekort:.0f}); overweeg elders bij te plussen")
    if week_total > hi:
        surplus = week_total - hi
        return (f" · ⚠ week {week_total:.0f} TSS > fase-max {hi:.0f} "
                f"(+{surplus:.0f}); overweeg elders te minderen")
    return ""


def perform_swap(event: dict, category: str, *, ftp: int = DEFAULT_FTP,
                 ideal_tss: Optional[float] = None,
                 matched: Optional[list] = None,
                 phase_tss_range: Optional[tuple[float, float]] = None,
                 rng: Optional[random.Random] = None) -> dict:
    """Kies de best-passende swap-optie en schrijf die naar intervals.icu.

    Pure service-variant van app.py's perform_instant_swap: geen
    Streamlit, geen TP-propagatie — de caller doet presentatie.

    Returns dict::

        {ok, message, chosen, undo, phase_warning, new_tss}

    ``undo`` bevat de originele eventvelden zodat de caller een
    terugzet-actie kan aanbieden.
    """
    from agents import workout_library as lib

    rng = rng or random

    options = lib.get_swap_options(event, category, ftp=ftp, target_tss=ideal_tss)
    if not options:
        return {"ok": False, "chosen": None, "undo": None, "phase_warning": "",
                "new_tss": None,
                "message": f"Geen alternatieven gevonden in categorie '{category}'"}

    # Vermijd dezelfde workout als we toch al hebben — filter op naam
    current_name = (event.get("name") or "").lower()
    options = [o for o in options if o.get("naam", "").lower() != current_name]
    if not options:
        return {"ok": False, "chosen": None, "undo": None, "phase_warning": "",
                "new_tss": None,
                "message": "Alleen deze workout-variant beschikbaar in library"}

    pool_size = POOL_WITH_TARGET if ideal_tss is not None else POOL_RANDOM
    chosen = rng.choice(options[:pool_size])

    try:
        import intervals_client as api
        from agents.workout_annotations import annotate_description

        new_sport = chosen.get("sport", event.get("type"))
        new_desc = annotate_description(chosen["beschrijving"], new_sport)
        api.update_event(
            event["id"],
            name=chosen["naam"],
            description=new_desc,
            type=new_sport,
            load_target=chosen.get("tss_geschat"),
        )
    except Exception as exc:
        return {"ok": False, "chosen": None, "undo": None, "phase_warning": "",
                "new_tss": None, "message": f"Swap mislukt: {exc}"}

    new_tss = chosen.get("tss_geschat") or 0
    orig_tss = event.get("load_target") or 0
    tss_info = f" ({new_tss:.0f} TSS"
    if orig_tss:
        tss_info += f", {new_tss - orig_tss:+.0f} vs origineel"
    if ideal_tss is not None:
        tss_info += f", week-target {ideal_tss:.0f}"
    tss_info += ")"

    phase_warning = build_phase_warning(matched, event.get("id"), new_tss,
                                        phase_tss_range)

    return {
        "ok": True,
        "message": f"→ Gewisseld naar '{chosen['naam']}'{tss_info}",
        "chosen": chosen,
        "new_tss": new_tss,
        "phase_warning": phase_warning,
        "undo": {
            "event_id": event["id"],
            "orig_name": event.get("name", ""),
            "orig_description": event.get("description", ""),
            "orig_type": event.get("type", ""),
            "orig_load_target": event.get("load_target"),
        },
    }
