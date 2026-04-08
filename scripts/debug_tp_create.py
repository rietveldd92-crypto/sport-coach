"""Throwaway: POST a minimal workout and print the full TP response body.

Lets us see what TP is actually complaining about — our production client
strips response bodies to avoid cookie leakage.
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

import config
import intervals_client
import trainingpeaks_client as tpc
from workout_converter import convert


def main() -> int:
    cookie = config.get_secret("TP_AUTH_COOKIE", required=True)
    token = tpc.exchange_cookie_for_token(cookie)
    user_id = tpc.get_user_id(token)
    print(f"userId: {user_id}")

    target = date(2026, 4, 9)
    events = intervals_client.get_events(
        start=target, end=target, resolve=True
    )
    event = next(
        e for e in events
        if e.get("start_date_local", "").startswith(target.isoformat())
        and e.get("workout_doc")
    )
    print(f"event: {event['name']} ({event['type']})")

    conv = convert(event["workout_doc"], event["type"])
    print(f"conversion: {conv['total_seconds']}s, type_id={conv['workout_type_id']}")

    payload = {
        "athleteId": user_id,
        "workoutDay": f"{target.isoformat()}T00:00:00",
        "workoutTypeValueId": conv["workout_type_id"],
        "title": event.get("name", "debug"),
        "description": event.get("description") or "",
        "totalTimePlanned": round(conv["total_seconds"] / 3600, 4),
        "structure": conv["tp_structure"],
    }
    tss = event.get("icu_training_load")
    if tss is not None:
        payload["tssPlanned"] = tss

    print("\n--- request payload ---")
    print(json.dumps(payload, indent=2, ensure_ascii=False)[:3000])

    url = f"{tpc.BASE_URL}{tpc.CREATE_WORKOUT_PATH.format(user_id=user_id)}"
    r = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=20,
    )

    print(f"\n--- response ---")
    print(f"status: {r.status_code}")
    print(f"content-type: {r.headers.get('content-type')}")
    print("body:")
    try:
        print(json.dumps(r.json(), indent=2, ensure_ascii=False))
    except Exception:
        print(r.text[:3000])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
