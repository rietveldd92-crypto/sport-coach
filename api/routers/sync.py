"""POST /api/sync/tp/{event_id} — TrainingPeaks-sync via tp_sync_service."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

import config
import tp_sync_service
from core import views
from trainingpeaks_errors import TPAPIError, TPAuthError, TPConversionError

router = APIRouter(tags=["sync"])


@router.post("/sync/tp/{event_id}")
def sync_tp(event_id: str) -> dict:
    if not config.get_bool("TP_SYNC_ENABLED", default=False):
        raise HTTPException(status_code=409,
                            detail="TP-sync staat uit (TP_SYNC_ENABLED)")

    event = views.find_event(event_id, resolve=True)
    if event is None:
        raise HTTPException(status_code=404,
                            detail=f"Event {event_id} niet gevonden")

    cookie = config.get_secret("TP_AUTH_COOKIE") or ""
    try:
        return tp_sync_service.sync_event(event, cookie)
    except TPAuthError as exc:
        raise HTTPException(status_code=502, detail=f"TP-auth: {exc}")
    except TPConversionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except TPAPIError as exc:
        raise HTTPException(status_code=502, detail=f"TP API: {exc}")
