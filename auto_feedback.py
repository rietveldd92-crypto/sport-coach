"""
auto_feedback.py — Automatische feedback na voltooide workouts.

Draai als scheduled task (elke 30 min of elk uur).
Checkt intervals.icu op nieuwe voltooide workouts, genereert feedback,
en stuurt die als notitie in intervals.icu + optioneel als email.

Gebruik:
    python auto_feedback.py              # Check en stuur feedback
    python auto_feedback.py --dry-run    # Check zonder te schrijven
    python auto_feedback.py --setup      # Toon setup instructies

Windows Task Scheduler:
    schtasks /create /tn "SportCoachFeedback" /tr "python C:\\Projects\\Sport\\auto_feedback.py" /sc hourly /st 00:15
"""

import os
import sys
import json
import smtplib
from email.mime.text import MIMEText
from datetime import date, timedelta
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv()

import intervals_client as api
from agents import feedback_engine

STATE_PATH = Path(__file__).parent / "state.json"
FEEDBACK_LOG = Path(__file__).parent / "feedback_log.json"

# Email config (optioneel, via .env)
EMAIL_TO = os.getenv("FEEDBACK_EMAIL_TO")  # jouw email
EMAIL_FROM = os.getenv("FEEDBACK_EMAIL_FROM")  # sender
EMAIL_SMTP = os.getenv("FEEDBACK_SMTP_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("FEEDBACK_SMTP_PORT", "587"))
EMAIL_USER = os.getenv("FEEDBACK_SMTP_USER")
EMAIL_PASS = os.getenv("FEEDBACK_SMTP_PASS")


def _load_feedback_log() -> dict:
    """Laad log van eerder gegeven feedback (voorkomt duplicaten)."""
    if FEEDBACK_LOG.exists():
        with open(FEEDBACK_LOG) as f:
            return json.load(f)
    return {"processed_activities": []}


def _save_feedback_log(log: dict):
    with open(FEEDBACK_LOG, "w") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)


def find_new_completed_workouts() -> list[dict]:
    """Vind workouts die voltooid zijn maar nog geen feedback hebben gekregen."""
    log = _load_feedback_log()
    processed = set(log.get("processed_activities", []))

    # Haal events en activiteiten van deze week
    monday = date.today() - timedelta(days=date.today().weekday())
    sunday = monday + timedelta(days=6)

    try:
        events = api.get_events(monday, sunday)
        activities = api.get_activities(start=monday, end=sunday)
    except Exception as e:
        print(f"  Kan data niet ophalen: {e}")
        return []

    # Match activiteiten met events
    results = []
    for act in activities:
        act_id = str(act.get("id", ""))
        if act_id in processed:
            continue

        act_date = act.get("start_date_local", "")[:10]
        act_type = act.get("type", "")

        # Zoek bijbehorend event
        matched_event = None
        for event in events:
            if event.get("category") != "WORKOUT":
                continue
            e_date = event.get("start_date_local", "")[:10]
            e_type = event.get("type", "")
            if e_date == act_date and _types_match(e_type, act_type):
                matched_event = event
                break

        if matched_event:
            results.append({
                "activity": act,
                "event": matched_event,
                "activity_id": act_id,
            })

    return results


def _types_match(event_type: str, activity_type: str) -> bool:
    run_types = {"Run"}
    bike_types = {"Ride", "VirtualRide"}
    if event_type in run_types and activity_type in run_types:
        return True
    if event_type in bike_types and activity_type in bike_types:
        return True
    return event_type == activity_type


def _load_state() -> dict:
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def generate_feedback(event: dict, activity: dict) -> str:
    """Genereer workout-specifieke feedback via feedback_engine."""
    state = _load_state()

    try:
        wellness = api.get_wellness(
            start=date.today() - timedelta(days=14),
            end=date.today(),
        )
    except Exception:
        wellness = []

    try:
        recent_28d = api.get_activities(
            start=date.today() - timedelta(days=28),
            end=date.today(),
        )
    except Exception:
        recent_28d = []

    return feedback_engine.generate_feedback(
        event, activity,
        state=state,
        wellness_records=wellness,
        week_events=None,  # auto_feedback heeft geen weeklijst — single-event focus
        recent_28d=recent_28d,
    )


def post_feedback_to_intervals(event: dict, feedback: str, dry_run: bool = False):
    """Post feedback als notitie bij het event in intervals.icu."""
    event_id = event.get("id")
    if not event_id:
        return

    # Voeg feedback toe aan de beschrijving
    current_desc = event.get("description", "")
    feedback_block = f"\n\n--- Coach Feedback ---\n{feedback}"

    if "--- Coach Feedback ---" in current_desc:
        # Al feedback gegeven, niet dubbel posten
        return

    new_desc = current_desc + feedback_block

    if dry_run:
        print(f"  [DRY RUN] Zou feedback toevoegen aan '{event.get('name')}'")
        return

    try:
        api.update_event(event_id, description=new_desc)
    except Exception as e:
        print(f"  Fout bij posten feedback: {e}")


def send_email(subject: str, body: str):
    """Stuur feedback als email (optioneel)."""
    if not all([EMAIL_TO, EMAIL_FROM, EMAIL_USER, EMAIL_PASS]):
        return

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO

    try:
        with smtplib.SMTP(EMAIL_SMTP, EMAIL_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.send_message(msg)
        print(f"  Email verstuurd naar {EMAIL_TO}")
    except Exception as e:
        print(f"  Email niet verstuurd: {e}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Auto-feedback op voltooide workouts")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--setup", action="store_true")
    args = parser.parse_args()

    if args.setup:
        print("""
  AUTO-FEEDBACK SETUP
  ─────────────────────────────────
  1. Zorg dat .env bevat:
     INTERVALS_ATHLETE_ID=i85836
     INTERVALS_API_KEY=...
     ANTHROPIC_API_KEY=...

  2. Optioneel voor email:
     FEEDBACK_EMAIL_TO=dennis@example.com
     FEEDBACK_EMAIL_FROM=coach@example.com
     FEEDBACK_SMTP_HOST=smtp.gmail.com
     FEEDBACK_SMTP_PORT=587
     FEEDBACK_SMTP_USER=...
     FEEDBACK_SMTP_PASS=...

  3. Windows Task Scheduler (elk uur):
     schtasks /create /tn "SportCoachFeedback" /tr "python C:\\Projects\\Sport\\auto_feedback.py" /sc hourly /st 00:15

  4. Of handmatig: python auto_feedback.py
""")
        return

    print(f"\n  Auto-feedback check — {date.today()}")

    new_workouts = find_new_completed_workouts()
    if not new_workouts:
        print("  Geen nieuwe voltooide workouts.")
        return

    print(f"  {len(new_workouts)} nieuwe voltooide workout(s) gevonden.\n")

    log = _load_feedback_log()
    email_body = []

    for item in new_workouts:
        act = item["activity"]
        event = item["event"]
        act_name = act.get("name", "?")
        event_name = event.get("name", "?")
        act_date = act.get("start_date_local", "")[:10]

        print(f"  {act_date} — {event_name}")
        feedback = generate_feedback(event, act)
        print(f"  {feedback}\n")

        # Post naar intervals.icu
        post_feedback_to_intervals(event, feedback, dry_run=args.dry_run)

        # Verzamel voor email
        email_body.append(f"{act_date} — {event_name}\n{feedback}\n")

        # Markeer als verwerkt
        log["processed_activities"].append(item["activity_id"])

    # Sla log op
    if not args.dry_run:
        _save_feedback_log(log)

    # Stuur email als er feedback is
    if email_body and not args.dry_run:
        subject = f"Coach feedback — {date.today()}"
        body = "Coach feedback op je workouts:\n\n" + "\n".join(email_body)
        body += "\n\nEen gelukkige atleet is een snelle atleet. — Delahaije"
        send_email(subject, body)

    print(f"  Klaar. {len(new_workouts)} workout(s) verwerkt.")


if __name__ == "__main__":
    main()
