"""CLI: sync one intervals.icu workout to TrainingPeaks.

Usage:
    # Dry run (default) — shows what would be sent, no network writes:
    python sync_to_tp.py --date 2026-04-10

    # Actually push to TrainingPeaks:
    python sync_to_tp.py --date 2026-04-10 --push

    # Default date is today:
    python sync_to_tp.py --push

Requirements before running:
    1. Set TP_SYNC_ENABLED = true  in .streamlit/secrets.toml
    2. Set TP_AUTH_COOKIE = "Production_tpAuth=..."  (see secrets.toml.example)
    3. Have a planned workout on the chosen date in intervals.icu

The dry run goes all the way through fetch + convert, so it's the fastest
way to validate the whole pipeline without polluting your TP calendar.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta

import config
import intervals_client
from trainingpeaks_errors import TPAPIError, TPAuthError, TPConversionError
from workout_converter import convert


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync one intervals.icu workout to TrainingPeaks."
    )
    parser.add_argument(
        "--date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        default=None,
        help="Target date YYYY-MM-DD (default: today)",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="Actually POST to TrainingPeaks. Without this flag, dry-run only.",
    )
    parser.add_argument(
        "--event-index",
        type=int,
        default=0,
        help="If multiple workouts on the target date, pick this index (default 0).",
    )
    return parser.parse_args(argv)


def log(step: str, message: str) -> None:
    print(f"[{step}] {message}")


def mask_cookie(cookie: str) -> str:
    if not cookie:
        return "<empty>"
    tail = cookie[-6:] if len(cookie) > 10 else "***"
    return f"***masked*** (len={len(cookie)}, ...{tail})"


def check_config() -> str:
    """Verify feature flag and cookie are present. Returns the cookie string."""
    log("1/5", "Checking config...")
    enabled = config.get_bool("TP_SYNC_ENABLED", default=False)
    print(f"       TP_SYNC_ENABLED: {enabled}")
    if not enabled:
        print(
            "       Aborting: set TP_SYNC_ENABLED=true in "
            ".streamlit/secrets.toml to proceed."
        )
        sys.exit(2)

    cookie = config.get_secret("TP_AUTH_COOKIE")
    print(f"       TP_AUTH_COOKIE: {mask_cookie(cookie or '')}")
    if not cookie:
        print(
            "       Aborting: TP_AUTH_COOKIE is missing. Copy the "
            "Production_tpAuth cookie from DevTools on trainingpeaks.com. "
            "See .streamlit/secrets.toml.example for the full procedure."
        )
        sys.exit(2)
    return cookie


def fetch_workout(target: date, event_index: int) -> dict:
    """Fetch events with resolve=true and pick the one on the target date."""
    log("2/5", f"Fetching workouts from intervals.icu for {target}...")
    # ±1-day window keeps the request small while tolerating TZ edge cases.
    events = intervals_client.get_events(
        start=target - timedelta(days=1),
        end=target + timedelta(days=1),
        resolve=True,
    )
    on_day = [
        e
        for e in events
        if e.get("category") == "WORKOUT"
        and e.get("start_date_local", "")[:10] == target.isoformat()
        and e.get("workout_doc")
    ]
    if not on_day:
        print(f"       No planned workout found on {target}.")
        sys.exit(3)

    if event_index >= len(on_day):
        print(
            f"       --event-index {event_index} out of range "
            f"({len(on_day)} workouts on this date)."
        )
        sys.exit(3)

    for i, e in enumerate(on_day):
        marker = ">" if i == event_index else " "
        print(
            f"       {marker} [{i}] {e.get('type'):12s}  "
            f"{e.get('name', '<no name>')[:60]}"
        )

    return on_day[event_index]


def convert_workout(event: dict) -> dict:
    log("3/5", "Converting to TrainingPeaks structure...")
    try:
        conversion = convert(event["workout_doc"], event["type"])
    except TPConversionError as exc:
        print(f"       Conversion failed: {exc}")
        sys.exit(4)

    mins = conversion["total_seconds"] / 60
    n_top = len(conversion["tp_structure"]["structure"])
    n_rep = sum(
        1
        for s in conversion["tp_structure"]["structure"]
        if s["type"] == "repetition"
    )
    print(
        f"       {n_top} top-level steps ({n_rep} repetition group(s)), "
        f"total {mins:.1f} min"
    )
    return conversion


def build_payload_preview(
    event: dict, conversion: dict, target: date
) -> dict:
    """Build the dict we'd POST — for dry-run display."""
    return {
        "workoutDay": target.isoformat(),
        "workoutTypeValueId": conversion["workout_type_id"],
        "title": event.get("name", "(untitled)"),
        "description": event.get("description", "") or "",
        "totalTimePlanned": round(conversion["total_seconds"] / 3600, 4),
        "tssPlanned": event.get("icu_training_load"),
        "structure": conversion["tp_structure"],
    }


def push_workout(cookie: str, event: dict, conversion: dict, target: date) -> None:
    """Exchange cookie, fetch user id, and create the workout."""
    # Local import so `--dry-run` path never touches the network client.
    import trainingpeaks_client as tpc

    log("4/5", "Exchanging cookie for access token...")
    token = tpc.exchange_cookie_for_token(cookie)
    print("       OK")

    log("4/5", "Fetching TrainingPeaks user id...")
    user_id = tpc.get_user_id(token)
    print(f"       userId={user_id}")

    log("5/5", "POST /fitness/v6/athletes/{uid}/workouts ...")
    response = tpc.create_workout(
        token=token,
        user_id=user_id,
        workout_day=target,
        workout_type_id=conversion["workout_type_id"],
        title=event.get("name", "(untitled)"),
        description=event.get("description") or "",
        total_seconds=conversion["total_seconds"],
        tp_structure=conversion["tp_structure"],
        tss_planned=event.get("icu_training_load"),
    )
    print(f"       OK — response: {json.dumps(response)[:120]}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    target = args.date or date.today()

    cookie = check_config()
    event = fetch_workout(target, args.event_index)
    conversion = convert_workout(event)

    preview = build_payload_preview(event, conversion, target)
    print("\n--- Dry-run payload preview ---")
    print(json.dumps(preview, indent=2, ensure_ascii=False, default=str))
    print("--- end preview ---\n")

    if not args.push:
        print(
            "Dry-run complete. Re-run with --push to actually create this "
            "workout in TrainingPeaks."
        )
        return 0

    try:
        push_workout(cookie, event, conversion, target)
    except TPAuthError as exc:
        print(f"\nAuth error: {exc}")
        return 5
    except TPAPIError as exc:
        status = f" (HTTP {exc.status_code})" if exc.status_code else ""
        print(f"\nAPI error{status}: {exc}")
        return 6

    print("\nSuccess: workout created in TrainingPeaks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
