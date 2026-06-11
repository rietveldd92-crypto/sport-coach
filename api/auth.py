"""Auth-dependency — simpele single-user bearer-token (UPGRADE_PLAN §7).

- ``API_TOKEN`` gezet (env/.env/secrets) → elke request moet
  ``Authorization: Bearer <token>`` meesturen.
- Geen token gezet → alleen verkeer vanaf localhost toegestaan
  (dev-modus; de TestClient telt ook als localhost).
"""
from __future__ import annotations

import secrets

from fastapi import HTTPException, Request

import config

# 'testclient' is de host die Starlette's TestClient meegeeft.
LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


def require_auth(request: Request) -> None:
    """FastAPI-dependency: 401 bij ontbrekende/foute token."""
    token = config.get_secret("API_TOKEN")
    if token:
        header = request.headers.get("authorization") or ""
        scheme, _, supplied = header.partition(" ")
        if scheme.lower() != "bearer" or not secrets.compare_digest(
                supplied.strip(), str(token)):
            raise HTTPException(
                status_code=401,
                detail="Ongeldige of ontbrekende bearer-token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return

    host = request.client.host if request.client else ""
    if host not in LOCAL_HOSTS:
        raise HTTPException(
            status_code=401,
            detail="Geen API_TOKEN geconfigureerd — alleen localhost toegestaan",
        )
