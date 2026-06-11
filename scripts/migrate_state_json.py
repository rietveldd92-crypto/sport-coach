"""Eenmalige migratie: state.json → SQLite (history.db).

Fase 0 van UPGRADE_PLAN.md:
- elke top-level sectie van state.json (injury, signal_buffer, load,
  build_deload, progression, tp_sync_log, weekly_log, ... en scalaire keys
  zoals athlete_id/race_date/current_phase/week_number/plan_start) wordt
  als JSON-string in `athlete_state` gezet;
- de `availability` sectie ({date: minuten}) wordt één slot per dag in
  `availability_override`: slot_start "07:00", slot_end = 07:00 + minuten.
  0-minuten-dagen (bewuste rustdagen) worden "00:00"–"00:00" zodat de
  informatie behouden blijft;
- bestaande `tp_sync_log` entries worden óók in `workout_tp_sync` geüpsert
  zodat tp_sync_service (die nu op die tabel draait) ze blijft zien.

Het script is idempotent: opnieuw draaien geeft hetzelfde resultaat.
Voor de eerste run wordt een backup state.json.bak gemaakt (bestaande
backup wordt niet overschreven). state.json zelf blijft onaangetast en
dient als read-only fallback tot je hem verwijdert.

Gebruik:
    python3 scripts/migrate_state_json.py
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

# Project-root op sys.path zodat history_db importeerbaar is.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import history_db  # noqa: E402

STATE_PATH = PROJECT_ROOT / "state.json"
BACKUP_PATH = PROJECT_ROOT / "state.json.bak"


def migrate(state_path: Path = STATE_PATH, backup_path: Path = BACKUP_PATH) -> dict:
    """Voer de migratie uit. Returnt een klein rapport-dict."""
    if not state_path.exists():
        return {"ok": False, "error": f"{state_path} bestaat niet — niets te migreren."}

    # 1. Backup (alleen als er nog geen is — origineel bewaren)
    backed_up = False
    if not backup_path.exists():
        shutil.copy2(state_path, backup_path)
        backed_up = True

    with open(state_path, encoding="utf-8") as f:
        state = json.load(f)

    history_db.ensure_migrations()

    # 2. availability → availability_override (één slot per dag)
    availability = state.pop("availability", None) or {}
    history_db.replace_availability_minutes(availability)

    # 3. Alle overige top-level keys → athlete_state (whole-state replace,
    #    zelfde semantiek als het oude state.json-bestand)
    history_db.replace_athlete_state(state)

    # 4. tp_sync_log óók naar workout_tp_sync (tp_sync_service leest die)
    tp_sync_log = state.get("tp_sync_log") or {}
    for event_id, entry in tp_sync_log.items():
        if not isinstance(entry, dict):
            continue
        history_db.record_tp_sync(
            str(event_id),
            tp_workout_id=str(entry.get("tp_workout_id") or ""),
            event_name=entry.get("title") or "",
            sync_hash=None,
            workout_day=entry.get("workout_day"),
            synced_at=entry.get("synced_at"),
        )

    return {
        "ok": True,
        "backup_created": backed_up,
        "athlete_state_keys": len(state),
        "availability_days": len(availability),
        "tp_sync_entries": len(tp_sync_log),
    }


def main() -> int:
    report = migrate()
    if not report.get("ok"):
        print(f"FOUT: {report.get('error')}")
        return 1
    print(f"Migratie klaar → {history_db.DB_PATH}")
    print(f"  backup gemaakt:       {report['backup_created']} ({BACKUP_PATH.name})")
    print(f"  athlete_state keys:   {report['athlete_state_keys']}")
    print(f"  availability dagen:   {report['availability_days']}")
    print(f"  tp_sync_log entries:  {report['tp_sync_entries']} → workout_tp_sync")
    print("state.json blijft staan als fallback; shared.load_state() leest nu uit SQLite.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
