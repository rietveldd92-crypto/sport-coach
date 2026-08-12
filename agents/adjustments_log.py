"""adjustments_log — persistentie van adaptieve aanpassingen.

Schrijft naar `adjustments_log.json` in de project root. UI leest hieruit.
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from .models import AdaptResult, Deviation, Modification

LOG_PATH = Path(__file__).resolve().parent.parent / "adjustments_log.json"


def _default_path() -> Path:
    return LOG_PATH


def _read_all(path: Optional[Path] = None) -> list[dict[str, Any]]:
    p = path or _default_path()
    if not p.exists():
        return []
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        return []
    except (json.JSONDecodeError, OSError):
        return []


def _write_all(entries: list[dict[str, Any]], path: Optional[Path] = None) -> None:
    p = path or _default_path()
    with open(p, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False, default=str)


def build_entry(
    week_start: date,
    deviations: list[Deviation],
    adapt_result: AdaptResult,
    applied: bool = True,
) -> dict[str, Any]:
    """Bouw een log-entry (nog niet weggeschreven)."""
    return {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "week_start": week_start.isoformat(),
        "deviations": [d.model_dump() for d in deviations],
        "modifications": [m.model_dump() for m in adapt_result.modifications],
        "new_events": adapt_result.new_events,
        "narrative": adapt_result.narrative,
        "invariant": adapt_result.invariant,
        "applied": applied,
        "dismissed": False,
        "reverted": False,
    }


def append(entry: dict[str, Any], path: Optional[Path] = None) -> dict[str, Any]:
    """Voeg een entry toe aan de log. Returnt de entry (met eventueel gevulde id)."""
    entries = _read_all(path)
    if "id" not in entry or not entry["id"]:
        entry["id"] = str(uuid.uuid4())
    entries.append(entry)
    _write_all(entries, path)
    return entry


def _mark(
    entry_id: str,
    field: str,
    value: bool = True,
    path: Optional[Path] = None,
) -> bool:
    entries = _read_all(path)
    changed = False
    for e in entries:
        if e.get("id") == entry_id:
            e[field] = value
            changed = True
            break
    if changed:
        _write_all(entries, path)
    return changed


def mark_dismissed(entry_id: str, path: Optional[Path] = None) -> bool:
    return _mark(entry_id, "dismissed", True, path)


def mark_reverted(entry_id: str, path: Optional[Path] = None) -> bool:
    return _mark(entry_id, "reverted", True, path)


def get_active(path: Optional[Path] = None) -> Optional[dict[str, Any]]:
    """Return meest recente entry die niet dismissed en niet reverted is."""
    entries = _read_all(path)
    active = [
        e
        for e in entries
        if not e.get("dismissed") and not e.get("reverted") and e.get("applied")
    ]
    if not active:
        return None
    # laatste toegevoegd = laatste in lijst
    return active[-1]


def get_all(path: Optional[Path] = None) -> list[dict[str, Any]]:
    return _read_all(path)


def get_by_id(entry_id: str, path: Optional[Path] = None) -> Optional[dict[str, Any]]:
    for e in _read_all(path):
        if e.get("id") == entry_id:
            return e
    return None
