"""Throwaway: dump the raw /users/v3/user response to see its shape."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

import config
import trainingpeaks_client as tpc


def main() -> int:
    cookie = config.get_secret("TP_AUTH_COOKIE", required=True)
    token = tpc.exchange_cookie_for_token(cookie)
    print(f"token (truncated): {token[:20]}...")

    r = requests.get(
        f"{tpc.BASE_URL}{tpc.USER_PATH}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=15,
    )
    print(f"status: {r.status_code}")
    body = r.json()
    print("body shape (top-level keys):", sorted(body.keys()) if isinstance(body, dict) else type(body))
    print("full body:")
    print(json.dumps(body, indent=2, ensure_ascii=False)[:3000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
