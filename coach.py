"""
coach.py — Interactieve coach CLI.

Toont de komende week, geeft AI feedback op voltooide workouts,
en kan workouts swappen voor alternatieven uit de library.

Gebruik:
    python coach.py                  # Toon komende week + feedback op voltooide workouts
    python coach.py --check          # Check voltooide workouts, geef feedback, non-interactive
    python coach.py --week 2026-04-13  # Bekijk specifieke week
"""

import os
import sys
import json
import argparse
from datetime import date, timedelta
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import intervals_client as api
from agents import workout_library as lib

STATE_PATH = Path(__file__).parent / "state.json"

try:
    import anthropic
    CLAUDE_AVAILABLE = bool(os.getenv("ANTHROPIC_API_KEY"))
except ImportError:
    CLAUDE_AVAILABLE = False

DAYS_NL = {0: "maandag", 1: "dinsdag", 2: "woensdag", 3: "donderdag",
           4: "vrijdag", 5: "zaterdag", 6: "zondag"}


# ── DATA ────────────────────────────────────────────────────────────────────

def _this_monday() -> date:
    today = date.today()
    return today - timedelta(days=today.weekday())


def get_week_events(monday: date) -> list[dict]:
    """Haal alle events van een week op, verrijkt met status."""
    sunday = monday + timedelta(days=6)
    events = api.get_events(monday, sunday)

    # Haal activiteiten op om te matchen met geplande workouts
    activities = []
    try:
        activities = api.get_activities(start=monday, end=sunday)
    except Exception:
        pass

    # Markeer voltooide workouts
    activity_dates_types = set()
    for act in activities:
        d = act.get("start_date_local", "")[:10]
        t = act.get("type", "")
        activity_dates_types.add((d, t))

    result = []
    for event in events:
        if event.get("category") != "WORKOUT":
            continue

        e_date = event.get("start_date_local", "")[:10]
        e_type = event.get("type", "")
        e_name = event.get("name", "")

        # Check of er een activiteit is op dezelfde dag met hetzelfde type
        done = False
        matched_activity = None
        for act in activities:
            a_date = act.get("start_date_local", "")[:10]
            a_type = act.get("type", "")
            if a_date == e_date and _types_match(e_type, a_type):
                done = True
                matched_activity = act
                break

        result.append({
            "id": event.get("id"),
            "date": e_date,
            "day": DAYS_NL.get(date.fromisoformat(e_date).weekday(), "?"),
            "name": e_name,
            "type": e_type,
            "description": event.get("description", ""),
            "load_target": event.get("load_target"),
            "done": done,
            "activity": matched_activity,
        })

    result.sort(key=lambda e: e["date"])
    return result


def _types_match(event_type: str, activity_type: str) -> bool:
    """Check of een event-type en activity-type bij elkaar passen."""
    run_types = {"Run"}
    bike_types = {"Ride", "VirtualRide"}
    if event_type in run_types and activity_type in run_types:
        return True
    if event_type in bike_types and activity_type in bike_types:
        return True
    if event_type == activity_type:
        return True
    return False


def get_recent_activities(days: int = 7) -> list[dict]:
    """Haal recente activiteiten op voor context."""
    try:
        return api.get_activities(
            start=date.today() - timedelta(days=days),
            end=date.today()
        )
    except Exception:
        return []


# ── AI FEEDBACK ─────────────────────────────────────────────────────────────

FEEDBACK_PROMPT = """Je bent een ervaren hardloop/fietscoach in de stijl van Louis Delahaije.
Filosofie: gevoel boven data, gelukkige atleet = snelle atleet, volume boven intensiteit.

De atleet traint voor de Amsterdam Marathon (18 oktober 2026) en herstelt van een gluteus medius blessure.
Huidige CTL: {ctl}, FTP: 290W.

GEPLANDE WORKOUT:
{workout_name}
{workout_description}

UITGEVOERDE ACTIVITEIT:
Type: {activity_type}
Duur: {activity_duration} min
Afstand: {activity_distance} km
Gem. HR: {activity_hr} bpm ({hr_pct}% HRmax)
TSS: {activity_tss}
{activity_power_info}

RECENTE CONTEXT (afgelopen 3 dagen):
{recent_context}

Geef kort feedback (max 4 zinnen, Nederlands):
1. Was de workout goed uitgevoerd? (intensiteit, duur, zone)
2. Rode vlaggen? (te hard gelopen, knie-signalen, overtraining)
3. Advies voor morgen/volgende sessie
4. Motiverend Delahaije-achtig afsluitzinnetje

Antwoord in platte tekst, geen JSON.
"""


def generate_feedback(event: dict, recent_activities: list) -> str:
    """Genereer AI feedback op een voltooide workout."""
    if not CLAUDE_AVAILABLE:
        return _rule_based_feedback(event)

    act = event.get("activity", {})
    if not act:
        return "Geen activiteit gevonden om feedback op te geven."

    # Bouw context
    hr = act.get("average_heartrate") or act.get("icu_average_hr") or 0
    hr_max = act.get("max_heartrate") or act.get("icu_hr_max") or 190
    hr_pct = round(hr / hr_max * 100) if hr and hr_max else 0
    distance = round((act.get("distance") or 0) / 1000, 1)
    duration = round((act.get("moving_time") or act.get("elapsed_time") or 0) / 60)
    tss = act.get("icu_training_load") or act.get("training_load") or 0

    power_info = ""
    avg_power = act.get("average_watts") or act.get("icu_average_watts")
    if avg_power:
        power_info = f"Gem. vermogen: {avg_power}W (FTP 290W = {round(avg_power/290*100)}%)"

    # Recente activiteiten context
    recent_lines = []
    for ra in recent_activities[:5]:
        ra_date = ra.get("start_date_local", "")[:10]
        ra_name = ra.get("name", "")
        ra_tss = ra.get("icu_training_load") or 0
        recent_lines.append(f"  {ra_date}: {ra_name} (TSS {ra_tss:.0f})")
    recent_context = "\n".join(recent_lines) if recent_lines else "Geen recente data."

    # State lezen voor CTL
    try:
        with open(STATE_PATH) as f:
            state = json.load(f)
        ctl = state.get("load", {}).get("ctl_estimate", 49)
    except Exception:
        ctl = 49

    prompt = FEEDBACK_PROMPT.format(
        ctl=ctl,
        workout_name=event["name"],
        workout_description=event.get("description", "")[:500],
        activity_type=act.get("type", "?"),
        activity_duration=duration,
        activity_distance=distance,
        activity_hr=hr,
        hr_pct=hr_pct,
        activity_tss=tss,
        activity_power_info=power_info,
        recent_context=recent_context,
    )

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text.strip()
    except Exception as e:
        return f"AI feedback niet beschikbaar ({e}). " + _rule_based_feedback(event)


def _rule_based_feedback(event: dict) -> str:
    """Simpele rule-based feedback als Claude niet beschikbaar is."""
    act = event.get("activity", {})
    if not act:
        return "Workout niet uitgevoerd."

    hr = act.get("average_heartrate") or act.get("icu_average_hr") or 0
    hr_max = act.get("max_heartrate") or act.get("icu_hr_max") or 190
    tss = act.get("icu_training_load") or 0

    feedback = []
    if hr and hr_max:
        hr_pct = hr / hr_max * 100
        if hr_pct > 82 and "Z2" in event["name"]:
            feedback.append(f"Hartslag was {hr_pct:.0f}% HRmax — dat is boven Z2. Volgende keer rustiger.")
        elif hr_pct < 65 and "threshold" in event["name"].lower():
            feedback.append(f"Hartslag was {hr_pct:.0f}% HRmax — dat is aan de lage kant voor threshold.")
        else:
            feedback.append("Intensiteit ziet er goed uit.")

    if tss > 0:
        target = event.get("load_target") or 0
        if target and tss > target * 1.2:
            feedback.append(f"TSS ({tss:.0f}) was hoger dan gepland ({target}). Let op herstel.")
        elif target and tss < target * 0.7:
            feedback.append(f"TSS ({tss:.0f}) was lager dan gepland ({target}).")

    feedback.append("Gelukkige atleet = snelle atleet. Geniet van het proces!")
    return " ".join(feedback)


# ── SWAP ────────────────────────────────────────────────────────────────────

def get_alternatives(event: dict) -> list[dict]:
    """Genereer alternatieve workouts voor een event."""
    e_type = event.get("type", "")
    e_name = event.get("name", "").lower()

    try:
        with open(STATE_PATH) as f:
            state = json.load(f)
        prog = state.get("progression", {})
    except Exception:
        prog = {}

    alternatives = []

    if e_type in ("Ride", "VirtualRide"):
        t_step = prog.get("threshold_step", 3)
        ss_step = prog.get("sweetspot_step", 3)
        ou_step = prog.get("over_unders_step", 2)

        if "threshold" in e_name or "sweetspot" in e_name or "over-under" in e_name:
            # Hard → makkelijker of ander type hard
            alternatives = [
                lib.endurance_ride(90),
                lib.zwift_group_ride(75),
                lib.cadence_pyramids(290),
                lib.sweetspot(290, max(1, ss_step - 2)),
                lib.threshold(290, max(1, t_step - 2)),
                lib.single_leg_drills(290),
            ]
        else:
            # Easy → ander type easy of licht hard
            alternatives = [
                lib.zwift_group_ride(75),
                lib.endurance_ride(75),
                lib.cadence_pyramids(290),
                lib.single_leg_drills(290),
                lib.sweetspot(290, max(1, ss_step - 1)),
                lib.tempo_blocks(290),
            ]
    elif e_type == "Run":
        duration = 45  # default
        # Probeer duur uit de naam te halen
        for part in e_name.split():
            if part.endswith("min"):
                try:
                    duration = int(part.replace("min", ""))
                except ValueError:
                    pass

        alternatives = [
            lib.z2_standard(duration),
            lib.z2_progression(duration),
            lib.z2_fartlek(duration),
            lib.z2_trail(duration),
            lib.z2_with_pickups(duration),
            lib.recovery_run(max(25, duration - 10)),
        ]

    # Filter: niet dezelfde als het huidige event
    return [a for a in alternatives if a["naam"].lower() != e_name][:5]


def swap_workout(event: dict, new_workout: dict) -> bool:
    """Vervang een workout in intervals.icu."""
    event_id = event.get("id")
    if not event_id:
        print("  Geen event ID — kan niet swappen.")
        return False

    try:
        api.update_event(event_id,
                         name=new_workout["naam"],
                         description=new_workout["beschrijving"],
                         type=new_workout.get("sport", event.get("type")))
        return True
    except Exception as e:
        print(f"  Fout bij swappen: {e}")
        return False


# ── CHECK VOLTOOIDE WORKOUTS ────────────────────────────────────────────────

def check_completed(events: list, recent: list) -> list[dict]:
    """Check welke workouts voltooide zijn en genereer feedback."""
    completed = [e for e in events if e["done"]]
    results = []
    for event in completed:
        feedback = generate_feedback(event, recent)
        results.append({"event": event, "feedback": feedback})
    return results


# ── DISPLAY ─────────────────────────────────────────────────────────────────

def print_week(events: list, monday: date):
    """Print het weekoverzicht."""
    sunday = monday + timedelta(days=6)
    print(f"\n{'=' * 60}")
    print(f"  WEEK {monday} t/m {sunday}")
    print(f"{'=' * 60}")

    total_tss = 0
    done_tss = 0

    for i, event in enumerate(events, 1):
        status = "DONE" if event["done"] else "    "
        tss = ""
        if event.get("activity"):
            act_tss = event["activity"].get("icu_training_load") or 0
            tss = f"TSS {act_tss:.0f}"
            done_tss += act_tss
        elif event.get("load_target"):
            tss = f"TSS ~{event['load_target']}"

        target_tss = event.get("load_target") or 0
        total_tss += target_tss

        sport = "Run  " if event["type"] == "Run" else "Fiets"
        print(f"  {i:2d}. [{status}] {event['day']:10s} {sport} {event['name']:38s} {tss}")

    print(f"\n  Gepland: ~{total_tss} TSS | Voltooid: {done_tss:.0f} TSS")
    print(f"{'=' * 60}")


def print_feedback(completed: list[dict]):
    """Print feedback op voltooide workouts."""
    if not completed:
        print("\n  Geen voltooide workouts deze week.")
        return

    print(f"\n{'─' * 60}")
    print(f"  FEEDBACK OP VOLTOOIDE WORKOUTS")
    print(f"{'─' * 60}")
    for item in completed:
        event = item["event"]
        print(f"\n  {event['day']} — {event['name']}")
        print(f"  {'.' * 50}")
        # Wrap feedback text
        feedback = item["feedback"]
        for line in feedback.split("\n"):
            print(f"  {line}")


# ── INTERACTIVE MODE ────────────────────────────────────────────────────────

def interactive(events: list, recent: list):
    """Interactieve modus: kies workout, feedback, swap."""
    while True:
        try:
            choice = input("\n  Kies workout (1-{}) voor feedback/swap, 'q' om te stoppen: ".format(
                len(events))).strip()
        except (EOFError, KeyboardInterrupt):
            break

        if choice.lower() in ("q", "quit", "exit", ""):
            break

        try:
            idx = int(choice) - 1
            if idx < 0 or idx >= len(events):
                print("  Ongeldig nummer.")
                continue
        except ValueError:
            print("  Voer een nummer in.")
            continue

        event = events[idx]

        # Feedback
        if event["done"]:
            print(f"\n  Feedback op: {event['name']}")
            print(f"  {'.' * 50}")
            feedback = generate_feedback(event, recent)
            print(f"  {feedback}")
        else:
            print(f"\n  {event['name']} is nog niet uitgevoerd.")

        # Alternatieven tonen
        alternatives = get_alternatives(event)
        if alternatives:
            print(f"\n  Alternatieven:")
            for j, alt in enumerate(alternatives, 1):
                print(f"    {j}. {alt['naam']:40s} TSS ~{alt.get('tss_geschat', '?')}")

            try:
                swap_choice = input("  Swap naar (1-{}), of Enter om te houden: ".format(
                    len(alternatives))).strip()
            except (EOFError, KeyboardInterrupt):
                continue

            if swap_choice:
                try:
                    swap_idx = int(swap_choice) - 1
                    if 0 <= swap_idx < len(alternatives):
                        new_workout = alternatives[swap_idx]
                        if swap_workout(event, new_workout):
                            print(f"  Geswapped: {event['name']} -> {new_workout['naam']}")
                            event["name"] = new_workout["naam"]
                        else:
                            print("  Swap mislukt.")
                except ValueError:
                    pass


# ── MAIN ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Sport Coach — interactieve workout feedback")
    parser.add_argument("--week", type=str, default=None,
                        help="Maandag van de week (YYYY-MM-DD). Standaard: deze week.")
    parser.add_argument("--check", action="store_true",
                        help="Check voltooide workouts en geef feedback (non-interactive)")
    args = parser.parse_args()

    if args.week:
        monday = date.fromisoformat(args.week)
    else:
        monday = _this_monday()

    print("\n  Data ophalen uit intervals.icu...")
    events = get_week_events(monday)
    recent = get_recent_activities(days=7)

    if not events:
        print("  Geen workouts gevonden deze week.")
        return

    # Toon week
    print_week(events, monday)

    # Feedback op voltooide workouts
    completed = check_completed(events, recent)
    if completed:
        print_feedback(completed)

    # Interactive of exit
    if args.check:
        return

    interactive(events, recent)


if __name__ == "__main__":
    main()
