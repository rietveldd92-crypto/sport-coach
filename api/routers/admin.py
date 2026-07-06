"""Admin: database export/import (Railway-deploy, UPGRADE_PLAN restpunt).

- GET  /api/admin/export-db  → download van het SQLite-bestand (backup).
- POST /api/admin/import-db  → upload van een SQLite-bestand naar
  ``SPORT_DB_PATH``; bestaande DB wordt eerst weggeschreven als ``.pre-import``.
  Hiermee seed je een verse deploy (lege volume) met je lokale history.db:

      curl -X POST https://<app>/api/admin/import-db \
           -H "Authorization: Bearer $API_TOKEN" \
           --data-binary @history.db

Alleen zinvol single-user; beveiligd door dezelfde bearer-token als de rest.
"""
from __future__ import annotations

import shutil
import sqlite3
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

import history_db

router = APIRouter(prefix="/admin", tags=["admin"])

_SQLITE_MAGIC = b"SQLite format 3\x00"
_MAX_BYTES = 64 * 1024 * 1024  # ruim; history.db is enkele MB's


@router.get("/export-db")
def export_db() -> Response:
    """Download de actuele database (backup)."""
    path = Path(history_db.DB_PATH)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Geen database aanwezig.")
    return Response(
        content=path.read_bytes(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": 'attachment; filename="history.db"'},
    )


@router.post("/import-db")
async def import_db(request: Request) -> dict:
    """Vervang de database door het geüploade SQLite-bestand (raw body)."""
    body = await request.body()
    if len(body) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="Bestand te groot.")
    if not body.startswith(_SQLITE_MAGIC):
        raise HTTPException(status_code=422,
                            detail="Geen geldig SQLite-bestand.")

    # Integriteitscheck op een tempfile vóór we iets overschrijven.
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp.write(body)
        tmp_path = Path(tmp.name)
    try:
        conn = sqlite3.connect(tmp_path)
        try:
            ok = conn.execute("PRAGMA integrity_check").fetchone()
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            conn.close()
        if not ok or ok[0] != "ok":
            raise HTTPException(status_code=422,
                                detail="integrity_check faalde.")
        if "athlete_state" not in tables:
            raise HTTPException(
                status_code=422,
                detail="Geen Sport Coach-database (athlete_state ontbreekt).")

        target = Path(history_db.DB_PATH)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_file():
            shutil.copy2(target, target.with_suffix(".pre-import"))
        for suffix in ("-wal", "-shm", "-journal"):
            try:
                target.with_name(target.name + suffix).unlink(missing_ok=True)
            except PermissionError:
                pass
        shutil.move(str(tmp_path), target)
        for suffix in ("-wal", "-shm", "-journal"):
            try:
                target.with_name(target.name + suffix).unlink(missing_ok=True)
            except PermissionError:
                pass
    finally:
        tmp_path.unlink(missing_ok=True)

    # Migraties bijtrekken voor het geval de upload een oudere versie is.
    # Op Windows kan de oude DB kort gelockt blijven rond export/import-tests;
    # ensure_migrations is idempotent en loopt dan bij de volgende DB-open weer.
    try:
        history_db.ensure_migrations()
    except sqlite3.OperationalError as exc:
        if "locked" not in str(exc).lower():
            raise
    return {"imported": True, "bytes": len(body),
            "path": str(history_db.DB_PATH)}
