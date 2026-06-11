"""FastAPI-laag (Fase 3, UPGRADE_PLAN §7).

Start lokaal met::

    uvicorn api.main:app --reload

Routers zijn dun: Pydantic request/response + calls naar core/agents.
Auth: bearer-token uit env ``API_TOKEN`` (zonder token: alleen localhost).
Achtergrondtaken (auto_feedback, zondagse herijking) draaien via
APScheduler in hetzelfde proces, achter env-flag ``SCHEDULER_ENABLED``.
"""
