"""POST /api/sync/tp/{event_id} — TrainingPeaks-sync via tp_sync_service.

De foutteksten hieronder zijn de tekst die de atleet op zijn telefoon te
zien krijgt: de UI toont ``detail`` letterlijk. Ze noemen daarom wat er
mis is én wat de eerstvolgende handeling is, niet alleen de env-var-naam.
De TP-koppeling hangt aan een handmatig uit DevTools geplukte cookie, dus
"cookie verlopen" is de normale faalmodus en verdient een eigen tekst.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

import config
import tp_sync_service
from core import views
from trainingpeaks_errors import TPAPIError, TPAuthError, TPConversionError

router = APIRouter(tags=["sync"])

SYNC_UIT = (
    "TrainingPeaks-sync staat uit op de server. "
    "Zet TP_SYNC_ENABLED=true bij de variabelen van de app."
)
COOKIE_ONTBREEKT = (
    "De server heeft geen TrainingPeaks-cookie. "
    "Zet TP_AUTH_COOKIE bij de variabelen van de app."
)
COOKIE_VERLOPEN = (
    "De TrainingPeaks-cookie is verlopen. Log in op trainingpeaks.com, "
    "kopieer de Production_tpAuth-cookie opnieuw en vervang TP_AUTH_COOKIE."
)
TP_ONBEREIKBAAR = (
    "TrainingPeaks reageerde niet zoals verwacht. Probeer het zo nog eens; "
    "blijft het misgaan, dan ligt het aan TP zelf."
)


@router.post("/sync/tp/{event_id}")
def sync_tp(event_id: str) -> dict:
    if not config.get_bool("TP_SYNC_ENABLED", default=False):
        raise HTTPException(status_code=409, detail=SYNC_UIT)

    event = views.find_event(event_id, resolve=True)
    if event is None:
        raise HTTPException(status_code=404,
                            detail=f"Event {event_id} niet gevonden")

    cookie = config.get_secret("TP_AUTH_COOKIE") or ""
    # Zonder cookie hoeven we TP niet lastig te vallen: dit is een
    # configuratiefout op de server, geen storing bij TrainingPeaks.
    if not cookie.strip():
        raise HTTPException(status_code=409, detail=COOKIE_ONTBREEKT)

    try:
        return tp_sync_service.sync_event(event, cookie)
    except TPAuthError:
        raise HTTPException(status_code=502, detail=COOKIE_VERLOPEN)
    except TPConversionError as exc:
        # Deze teksten komen uit de service en zijn al specifiek genoeg
        # ("Workout is al gesynced naar TP", "Sport X wordt niet ondersteund").
        raise HTTPException(status_code=422, detail=str(exc))
    except TPAPIError:
        raise HTTPException(status_code=502, detail=TP_ONBEREIKBAAR)
