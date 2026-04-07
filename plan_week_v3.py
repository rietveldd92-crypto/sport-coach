"""
Weekplan 23-29 maart 2026 — inplannen in intervals.icu
Wist eerst alle bestaande workouts, plant dan de nieuwe week.
"""
from datetime import date
from intervals_client import bulk_delete_events, create_event

START = date(2026, 3, 23)
END = date(2026, 3, 29)

STRENGTH_DESCRIPTION = """\
Heup stretches
- Hip flexor stretch 2x 45s per kant
- Pigeon stretch 2x 45s per kant

Kopenhagen plank
- 3x 30s per kant

Zij plank been omhoog
- 3x 12 per kant

Single leg squats
- 3x 10 per kant

Single leg Romanian deadlifts
- 3x 10 per kant

Stabiliteitsdrills
- Single leg balance eyes closed 3x 30s per kant
- Banded lateral walks 3x 12 per kant
- Bird dogs 3x 10 per kant
"""

WORKOUTS = [
    # Ma 23: Krachttraining + Fiets threshold
    {
        "date": date(2026, 3, 23),
        "name": "Krachttraining",
        "sport_type": "WeightTraining",
        "description": STRENGTH_DESCRIPTION,
    },
    {
        "date": date(2026, 3, 23),
        "name": "Threshold sustained",
        "sport_type": "Ride",
        "description": """\
Warm-up
- 10m 55%
- 5m ramp 55-75%
3x
- 10m 95-100%
- 5m 55%
Cool-down
- 10m 50%""",
    },
    # Di 24: Easy run 6km
    {
        "date": date(2026, 3, 24),
        "name": "Easy run 6km",
        "sport_type": "Run",
        "description": "- 35m 60-65% Pace",
    },
    # Wo 25: Easy run 9km
    {
        "date": date(2026, 3, 25),
        "name": "Easy run 9km",
        "sport_type": "Run",
        "description": "- 50m 60-65% Pace",
    },
    # Do 26: Krachttraining + Fiets threshold over-unders
    {
        "date": date(2026, 3, 26),
        "name": "Krachttraining",
        "sport_type": "WeightTraining",
        "description": STRENGTH_DESCRIPTION,
    },
    {
        "date": date(2026, 3, 26),
        "name": "Threshold over-unders",
        "sport_type": "Ride",
        "description": """\
Warm-up
- 10m 55%
- 5m ramp 55-75%
4x
- 4m 100-105%
- 2m 85-90%
- 2m 50%
Cool-down
- 10m 50%""",
    },
    # Vr 27: Krachttraining + Easy run 5km
    {
        "date": date(2026, 3, 27),
        "name": "Krachttraining",
        "sport_type": "WeightTraining",
        "description": STRENGTH_DESCRIPTION,
    },
    {
        "date": date(2026, 3, 27),
        "name": "Easy run 5km",
        "sport_type": "Run",
        "description": "- 30m 60-65% Pace",
    },
    # Za 28: Long run 14km
    {
        "date": date(2026, 3, 28),
        "name": "Long run 14km",
        "sport_type": "Run",
        "description": "- 75m 60-68% Pace",
    },
    # Zo 29: Duurrit fiets 2u30-3u
    {
        "date": date(2026, 3, 29),
        "name": "Duurrit zone 2",
        "sport_type": "Ride",
        "description": "- 170m 65-75%",
    },
]


if __name__ == "__main__":
    print("=== Weekplan 23-29 maart inplannen ===\n")

    # Stap 1: Wis bestaande workouts
    print("Bestaande workouts verwijderen...")
    deleted = bulk_delete_events(START, END)
    print(f"  {deleted} workouts verwijderd\n")

    # Stap 2: Plan nieuwe workouts in
    print("Nieuwe workouts aanmaken...")
    for w in WORKOUTS:
        event = create_event(
            event_date=w["date"],
            name=w["name"],
            description=w["description"],
            sport_type=w["sport_type"],
        )
        print(f"  OK {w['date']} - {w['name']} ({w['sport_type']})")

    print(f"\nKlaar! {len(WORKOUTS)} workouts ingepland.")
