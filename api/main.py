"""FastAPI-app (Fase 3, UPGRADE_PLAN §7).

Start::

    uvicorn api.main:app --reload

- Alle routes onder /api, beveiligd met de bearer-token-dependency
  (api/auth.py). OpenAPI-spec op /docs (zelfde auth-regels niet van
  toepassing op de docs zelf — die zijn statisch).
- intervals.icu-fouten (core.views.IntervalsUnavailable) → nette 502.
- APScheduler (dagelijkse auto_feedback + zondagse herijking) start in
  de lifespan, alleen als env-flag ``SCHEDULER_ENABLED`` aan staat.
"""
from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Project-root op sys.path zodat `uvicorn api.main:app` ook werkt als de
# cwd niet de repo-root is.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import Depends, FastAPI, HTTPException, Request, Response  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402

import config  # noqa: E402
import history_db  # noqa: E402
from api import auth  # noqa: E402
from api.auth import require_auth  # noqa: E402
from core.views import IntervalsUnavailable  # noqa: E402


class LoginBody(BaseModel):
    password: str

_log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    history_db.ensure_migrations()

    scheduler = None
    if config.get_bool("SCHEDULER_ENABLED", default=False):
        from api.scheduler import create_scheduler

        scheduler = create_scheduler()
        scheduler.start()
        _log.info("APScheduler gestart (auto_feedback + weekly_recalibration)")
    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=False)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Sport Coach API",
        version="0.3.0",
        description="REST-laag over de core-agents (UPGRADE_PLAN §7).",
        lifespan=lifespan,
    )

    @app.exception_handler(IntervalsUnavailable)
    async def _intervals_unavailable(request: Request,
                                     exc: IntervalsUnavailable):
        return JSONResponse(
            status_code=502,
            content={"detail": f"intervals.icu niet bereikbaar: {exc}"},
        )

    from api.routers import ALL_ROUTERS

    for router in ALL_ROUTERS:
        app.include_router(router, prefix="/api",
                           dependencies=[Depends(require_auth)])

    @app.get("/api/health")
    def health() -> dict:
        """Onbeveiligde liveness-check (geen data)."""
        return {"status": "ok"}

    # ── auth: bewust zónder require_auth, anders kun je nooit inloggen ────

    @app.get("/api/auth/status")
    def auth_status(request: Request) -> dict:
        return {
            "authenticated": auth.is_authenticated(request),
            "auth_required": auth.auth_enabled(),
        }

    @app.post("/api/auth/login")
    def auth_login(request: Request, response: Response,
                   body: LoginBody) -> dict:
        auth.login(request, response, body.password)
        return {"ok": True}

    @app.post("/api/auth/logout")
    def auth_logout(response: Response) -> dict:
        auth.logout(response)
        return {"ok": True}

    _mount_spa(app)

    return app


def _mount_spa(app: FastAPI) -> None:
    """Serveer de PWA-build (web/dist) als die aanwezig is (Fase 5 deploy).

    Catch-all ná alle /api-routes: echte bestanden (assets, sw.js,
    manifest, icons) worden as-is geserveerd; alle overige niet-/api-paden
    vallen terug op index.html (SPA-routing). ``WEB_DIST_DIR`` overschrijft
    de locatie (tests/Docker).
    """
    dist = Path(os.environ.get("WEB_DIST_DIR")
                or PROJECT_ROOT / "web" / "dist").resolve()
    if not (dist / "index.html").is_file():
        return  # geen frontend-build → alleen API (dev-modus)

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        candidate = (dist / full_path).resolve() if full_path else dist
        if candidate.is_file() and candidate.is_relative_to(dist):
            return FileResponse(candidate)
        return FileResponse(dist / "index.html")


app = create_app()
