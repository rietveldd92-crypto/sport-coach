"""Throwaway: fetch workouts from TP calendar to see their structure shape."""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

import config
import trainingpeaks_client as tpc


def main() -> int:
    cookie = config.get_secret("TP_AUTH_COOKIE", required=True)
    token = tpc.exchange_cookie_for_token(cookie)
    user_id = tpc.get_user_id(token)
    print(f"userId: {user_id}")

    start = (date.today() - timedelta(days=60)).isoformat()
    end = (date.today() + timedelta(days=14)).isoformat()
    url = f"{tpc.BASE_URL}/fitness/v6/athletes/{user_id}/workouts/{start}/{end}"

    r = requests.get(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=20,
    )
    print(f"status: {r.status_code}")
    body = r.json()
    print(f"got {len(body) if isinstance(body, list) else '?'} workouts")

    # Find one Run (type 3) and one Bike (type 2) with structure
    want = {2: None, 3: None}
    for w in body if isinstance(body, list) else []:
        struct = w.get("structure")
        if not struct or struct in ("null", ""):
            continue
        t = w.get("workoutTypeValueId")
        if t in want and want[t] is None:
            want[t] = w
        if all(want.values()):
            break

    for type_id, w in want.items():
        sport = {2: "Bike", 3: "Run"}[type_id]
        print(f"\n=== {sport} (type {type_id}) ===")
        if w is None:
            print("  <none found>")
            continue
        print(f"  title: {w.get('title')}")
        print(f"  workoutDay: {w.get('workoutDay')}")
        struct = w["structure"]
        if isinstance(struct, str):
            try:
                struct = json.loads(struct)
            except Exception:
                pass
        # Show top-level structure metadata + first 2 steps
        meta = {k: v for k, v in struct.items() if k != "structure"}
        print(f"  top-level meta: {json.dumps(meta, ensure_ascii=False)}")
        first_steps = struct.get("structure", [])[:2]
        print(f"  first 2 steps:")
        print(json.dumps(first_steps, indent=2, ensure_ascii=False)[:1500])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
