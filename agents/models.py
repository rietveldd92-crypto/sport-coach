"""Pydantic v2 modellen voor het adaptive-core systeem.

Deze modellen zijn het contract tussen deviation_classifier, adapt_week,
adjustments_log en de UI-laag. Houd ze stabiel — wijzigingen raken state-files.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

DeviationType = Literal[
    "replaced_harder",
    "replaced_easier",
    "skipped",
    "extra",
    "longer",
    "none",
]

Severity = Literal["low", "medium", "high"]

ModificationAction = Literal["modify", "create", "delete"]


class Deviation(BaseModel):
    """Afwijking tussen een geplande sessie en een uitgevoerde activiteit."""

    type: DeviationType
    planned_event_id: Optional[str] = None
    actual_activity_id: Optional[str] = None
    tss_planned: float = 0.0
    tss_actual: float = 0.0
    severity: Severity = "low"
    # Extra context voor downstream agents (bijv. datum, sacred-flag)
    planned_date: Optional[str] = None
    sacred: bool = False
    note: Optional[str] = None


class Modification(BaseModel):
    """Één concrete wijziging aan een intervals.icu event."""

    event_id: str
    action: ModificationAction
    before: dict[str, Any] = Field(default_factory=dict)
    after: dict[str, Any] = Field(default_factory=dict)
    tss_delta: int = 0
    reason: Optional[str] = None
    # Per-mod apply tracking — wordt door auto_feedback gezet na intervals.icu write.
    # applied=True alleen als de write succesvol was; revert kan dan zinvol terugdraaien.
    applied: bool = False
    # Voor 'create'-mods: id van het ZOJUIST aangemaakte event (response van API).
    # Nodig om revert te kunnen doen — event_id is voor 'create' het PLANNED-id (oud), niet het nieuwe.
    created_event_id: Optional[str] = None
    # Foutmelding bij failed apply, voor debug en transparantie in log.
    error: Optional[str] = None


class AdaptResult(BaseModel):
    """Resultaat van adapt_week — lijst wijzigingen + uitleg."""

    new_events: list[dict[str, Any]] = Field(default_factory=list)
    modifications: list[Modification] = Field(default_factory=list)
    narrative: str = ""
    invariant: str = ""
