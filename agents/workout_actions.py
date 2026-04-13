"""Workout actions — swap / shorten / skip met impact-preview.

Preview-functies berekenen de TSS-delta en CTL-delta-schatting (3wk).
Apply-functies roepen intervals_client aan om de kalender te muteren.

CTL-delta-model (lineair):
    ctl_delta_3wk = (tss_delta / 42) * 3

Grove benadering: CTL neemt ~tss/42 per dag toe bij constante belasting;
over 3 weken is het totale effect dus ongeveer tss_delta/42 * 3.
"""
from __future__ import annotations

from typing import Literal, Optional

try:
    from pydantic import BaseModel, Field
except ImportError:  # pragma: no cover
    BaseModel = object  # type: ignore
    Field = lambda *a, **k: None  # type: ignore


# ── MODEL ──────────────────────────────────────────────────────────────────

class ImpactPreview(BaseModel):
    """Preview van wat een workout-action zou doen."""

    tss_delta: int
    ctl_delta_3wk: float
    narrative: str


# ── HELPERS ────────────────────────────────────────────────────────────────

def _event_tss(event: dict) -> int:
    """Huidige TSS van een event (0 als onbekend)."""
    for key in ("load_target", "tss", "icu_training_load"):
        v = event.get(key)
        if v is not None:
            try:
                return int(v)
            except (TypeError, ValueError):
                continue
    return 0


def _event_duration(event: dict) -> int:
    """Huidige duur (min) van een event. Probeer meerdere velden."""
    for key in ("duration", "duur_min", "moving_time"):
        v = event.get(key)
        if v is None:
            continue
        try:
            val = int(v)
        except (TypeError, ValueError):
            continue
        # moving_time is seconden
        if key == "moving_time":
            return val // 60
        return val
    # Parse uit naam
    naam = (event.get("name") or event.get("naam") or "").lower()
    for p in naam.replace("min", " ").split():
        try:
            d = int(p)
            if 10 <= d <= 300:
                return d
        except ValueError:
            pass
    return 0


def _ctl_delta(tss_delta: int) -> float:
    """3-weken CTL-schatting op basis van TSS-delta."""
    return round((tss_delta / 42.0) * 3, 2)


# ── PREVIEW FUNCTIES ───────────────────────────────────────────────────────

def preview_swap(event: dict, alternative_type: str) -> ImpactPreview:
    """Preview van swap naar een andere workout-type/categorie.

    Probeert eerst een echte swap-optie op te halen uit workout_library
    zodat we de werkelijke TSS van de vervanger kennen. Fallback: typische
    TSS-ranges per categorie.
    """
    current_tss = _event_tss(event)
    new_tss = current_tss  # fallback

    try:
        from agents import workout_library as lib
        opts = lib.get_swap_options(event, alternative_type)
        if opts:
            new_tss = int(opts[0].get("tss_geschat") or current_tss)
    except Exception:
        # Heuristische fallback op basis van categorie-label
        cat = alternative_type.lower()
        if cat in ("makkelijker", "easier", "rustiger"):
            new_tss = max(20, int(current_tss * 0.55))
        elif cat in ("harder", "zwaarder"):
            new_tss = int(current_tss * 1.2)
        else:
            new_tss = current_tss

    tss_delta = new_tss - current_tss
    ctl = _ctl_delta(tss_delta)
    narrative = (
        f"Swap naar '{alternative_type}'. "
        f"TSS {current_tss} → {new_tss} ({tss_delta:+d}). "
        f"CTL-effect over 3 weken: {ctl:+.1f}."
    )
    return ImpactPreview(tss_delta=tss_delta, ctl_delta_3wk=ctl, narrative=narrative)


def preview_shorten(event: dict, factor: float = 0.8) -> ImpactPreview:
    """Preview van workout-inkorting (duur × factor, TSS × factor)."""
    if factor <= 0 or factor >= 1:
        raise ValueError(f"factor moet tussen 0 en 1 liggen, kreeg {factor}")

    current_tss = _event_tss(event)
    current_dur = _event_duration(event)
    new_tss = int(round(current_tss * factor))
    new_dur = int(round(current_dur * factor))
    tss_delta = new_tss - current_tss
    ctl = _ctl_delta(tss_delta)
    pct = int(round((1 - factor) * 100))

    narrative = (
        f"Inkorten met {pct}%. "
        f"Duur {current_dur} → {new_dur} min. "
        f"TSS {current_tss} → {new_tss} ({tss_delta:+d}). "
        f"CTL-effect over 3 weken: {ctl:+.1f}."
    )
    return ImpactPreview(tss_delta=tss_delta, ctl_delta_3wk=ctl, narrative=narrative)


def preview_skip(event: dict) -> ImpactPreview:
    """Preview van workout skippen (verwijderen)."""
    current_tss = _event_tss(event)
    tss_delta = -current_tss
    ctl = _ctl_delta(tss_delta)
    narrative = (
        f"Skip deze sessie. "
        f"TSS {current_tss} → 0 ({tss_delta:+d}). "
        f"CTL-effect over 3 weken: {ctl:+.1f}."
    )
    return ImpactPreview(tss_delta=tss_delta, ctl_delta_3wk=ctl, narrative=narrative)


# ── APPLY FUNCTIES ─────────────────────────────────────────────────────────

def apply_swap(event_id: str, alternative_type: str, event: dict | None = None) -> dict:
    """Schrijf swap-mutatie naar intervals.icu.

    Kiest de eerste optie uit workout_library.get_swap_options voor het
    gegeven event + categorie en update het bestaande event.
    """
    import intervals_client as api
    from agents import workout_library as lib

    if event is None:
        event = {"id": event_id}
    opts = lib.get_swap_options(event, alternative_type)
    if not opts:
        raise ValueError(f"Geen swap-opties voor categorie '{alternative_type}'")
    pick = opts[0]
    return api.update_event(
        event_id,
        name=pick.get("naam") or pick.get("name") or "Swapped workout",
        description=pick.get("beschrijving") or "",
        load_target=pick.get("tss_geschat"),
    )


def apply_shorten(event_id: str, factor: float, event: dict | None = None) -> dict:
    """Schrijf kortere versie naar intervals.icu."""
    import intervals_client as api

    if event is None:
        event = {"id": event_id}
    current_tss = _event_tss(event)
    current_dur = _event_duration(event)
    new_tss = int(round(current_tss * factor))
    new_dur_sec = int(round(current_dur * factor * 60))

    payload: dict = {}
    if new_tss > 0:
        payload["load_target"] = new_tss
    if new_dur_sec > 0:
        payload["moving_time"] = new_dur_sec
    return api.update_event(event_id, **payload)


def apply_skip(event_id: str) -> None:
    """Verwijder event uit intervals.icu."""
    import intervals_client as api

    api.delete_event(event_id)
