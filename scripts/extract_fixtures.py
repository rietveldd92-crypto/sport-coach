"""Extract 5 representative workout_docs from the dump as test fixtures.

Strips zoneTimes/options/locales (bulky, not needed for conversion) but
keeps the rest of the workout_doc structure intact so fixtures match the
real intervals.icu API shape.

Also writes two synthetic fixtures for edge cases (missing FTP, HR target)
that don't appear in the current calendar.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

DUMP = Path(__file__).parent / "_workout_dump.json"
OUT_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "workout_docs"

REAL_FIXTURES = {
    # filename                          -> (dump_index, sport, filter_func)
    "run_z2_pace_steady.json":          (0,  "Run",         None),
    "bike_threshold_3x8_intervals.json":(7,  "VirtualRide", None),
    "bike_sweetspot_2x15_intervals.json":(10, "VirtualRide", None),
    "bike_endurance_rolling_8step.json":(13, "VirtualRide", None),
    "run_fartlek_5x_pace.json":         (15, "Run",         None),
}


def strip_bulk(doc: dict) -> dict:
    """Remove fields that don't affect conversion."""
    clean = copy.deepcopy(doc)
    for bulk in ("zoneTimes", "options", "locales"):
        clean.pop(bulk, None)
    return clean


def main() -> int:
    data = json.loads(DUMP.read_text(encoding="utf-8"))
    with_doc = [e for e in data if e.get("workout_doc")]

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for filename, (idx, expected_sport, _) in REAL_FIXTURES.items():
        event = with_doc[idx]
        assert event["type"] == expected_sport, (
            f"Fixture {filename}: expected {expected_sport}, got {event['type']}"
        )
        fixture = {
            "sport": event["type"],
            "name": event["name"],
            "workout_doc": strip_bulk(event["workout_doc"]),
        }
        (OUT_DIR / filename).write_text(
            json.dumps(fixture, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"  wrote {filename}")

    # Synthetic fixture: missing FTP (edge case)
    base = with_doc[7]  # bike threshold workout
    bad = {
        "sport": base["type"],
        "name": "Synthetic: missing FTP",
        "workout_doc": strip_bulk(base["workout_doc"]),
    }
    bad["workout_doc"]["ftp"] = None
    (OUT_DIR / "bike_missing_ftp_error.json").write_text(
        json.dumps(bad, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print("  wrote bike_missing_ftp_error.json")

    # Synthetic fixture: empty steps (edge case)
    empty = {
        "sport": "VirtualRide",
        "name": "Synthetic: empty steps",
        "workout_doc": {
            "duration": 0,
            "distance": 0.0,
            "ftp": 290,
            "lthr": 176,
            "target": "POWER",
            "steps": [],
        },
    }
    (OUT_DIR / "bike_empty_steps_error.json").write_text(
        json.dumps(empty, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print("  wrote bike_empty_steps_error.json")

    # Synthetic fixture: HR-target run (no HR workouts in calendar)
    hr_workout = {
        "sport": "Run",
        "name": "Synthetic: HR zone endurance run",
        "workout_doc": {
            "duration": 2400,
            "distance": 0.0,
            "ftp": 515,
            "lthr": 176,
            "threshold_pace": 4.1666665,
            "target": "HR",
            "steps": [
                {
                    "duration": 300,
                    "warmup": True,
                    "hr": {"start": 60, "end": 75, "units": "%lthr"},
                    "_hr": {"value": 118.8, "start": 105.6, "end": 132.0},
                },
                {
                    "duration": 1800,
                    "hr": {"value": 78, "units": "%lthr"},
                    "_hr": {"value": 137.3, "start": 134.0, "end": 140.6},
                },
                {
                    "duration": 300,
                    "cooldown": True,
                    "hr": {"start": 70, "end": 55, "units": "%lthr"},
                    "_hr": {"value": 110.0, "start": 123.2, "end": 96.8},
                },
            ],
        },
    }
    (OUT_DIR / "run_hr_zone_endurance.json").write_text(
        json.dumps(hr_workout, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print("  wrote run_hr_zone_endurance.json")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
