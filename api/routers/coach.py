"""GET /api/coach/feedback?event_id= — SSE-stream met coach-feedback.

Gemini-streaming via feedback_engine; zonder API-key valt de stream
terug op één rule-based event (non-streaming fallback, UPGRADE_PLAN §7).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from core import views

router = APIRouter(tags=["coach"])


@router.get("/coach/feedback")
def coach_feedback(event_id: str) -> StreamingResponse:
    try:
        data = views.prepare_coach_feedback(event_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return StreamingResponse(
        views.coach_feedback_sse(data),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
