"""Eenmalige exploratie: haal events met workout_doc op en dump naar disk.

Gebruik:
    python scripts/explore_workout_docs.py

Schrijft naar scripts/_workout_dump.json zodat we de structuur kunnen
inspecteren voor het aanmaken van realistische test-fixtures voor de
TrainingPeaks sync. Wordt NIET meegecommit.
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import intervals_client  # noqa: E402


def main() -> int:
    start = date.today() - timedelta(days=7)
    end = date.today() + timedelta(days=21)
    print(f"Haal events op van {start} t/m {end} (resolve=true) ...")
    events = intervals_client.get_events(start=start, end=end, resolve=True)
    print(f"  {len(events)} events ontvangen")

    out = Path(__file__).parent / "_workout_dump.json"
    out.write_text(json.dumps(events, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Geschreven naar {out}")

    with_doc = [e for e in events if e.get("workout_doc")]
    print(f"  waarvan {len(with_doc)} met workout_doc")

    types_seen: dict[str, int] = {}
    for e in with_doc:
        t = e.get("type") or "?"
        types_seen[t] = types_seen.get(t, 0) + 1
    if types_seen:
        print("  sporttypes:", ", ".join(f"{k}={v}" for k, v in types_seen.items()))

    for i, e in enumerate(with_doc[:3]):
        name = e.get("name", "<no name>")
        sport = e.get("type", "?")
        doc = e.get("workout_doc", {})
        n_steps = len(doc.get("steps", [])) if isinstance(doc, dict) else "?"
        print(f"  [{i}] {e.get('start_date_local', '?')[:10]}  {sport:6s}  {n_steps} steps  {name}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
