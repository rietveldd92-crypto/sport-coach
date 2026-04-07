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

import intervals_client as api

STATE_PATH = Path(__file__).parent / "state.json"
FEEDBACK_LOG = Path(__file__).parent / "feedback_log.json"

try:
    import anthropic
    CLAUDE_AVAILABLE = bool(os.getenv("ANTHROPIC_API_KEY"))
except ImportError:
    CLAUDE_AVAILABLE = False

# Email config (optioneel, via .env)
from dotenv import load_dotenv
load_dotenv()
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


def generate_feedback(event: dict, activity: dict) -> str:
    """Genereer AI feedback op een voltooide workout."""
    if not CLAUDE_AVAILABLE:
        return _quick_feedback(event, activity)

    hr = activity.get("average_heartrate") or activity.get("icu_average_hr") or 0
    hr_max = activity.get("max_heartrate") or activity.get("icu_hr_max") or 190
    hr_pct = round(hr / hr_max * 100) if hr and hr_max else 0
    distance = round((activity.get("distance") or 0) / 1000, 1)
    duration = round((activity.get("moving_time") or activity.get("elapsed_time") or 0) / 60)
    tss = activity.get("icu_training_load") or activity.get("training_load") or 0
    avg_power = activity.get("average_watts") or activity.get("icu_average_watts")

    prompt = f"""Je bent een ervaren coach in de stijl van Louis Delahaije.
Atleet traint voor Amsterdam Marathon (18 okt 2026), herstelt van gluteus medius blessure.

GEPLANDE WORKOUT: {event.get('name', '?')}
UITGEVOERD: {activity.get('type', '?')} | {duration}min | {distance}km | HR {hr}bpm ({hr_pct}%HRmax) | TSS {tss:.0f}
{f'Vermogen: {avg_power}W (FTP 290W = {round(avg_power/290*100)}%)' if avg_power else ''}

Geef feedback in 3-4 korte zinnen (Nederlands). Check: juiste zone? Rode vlaggen? Advies morgen?
Eindig met een motiverend Delahaije-achtig zinnetje. Platte tekst."""

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text.strip()
    except Exception as e:
        return f"(AI niet bereikbaar: {e}) " + _quick_feedback(event, activity)


def _quick_feedback(event: dict, activity: dict) -> str:
    """Rule-based feedback fallback."""
    hr = activity.get("average_heartrate") or activity.get("icu_average_hr") or 0
    hr_max = activity.get("max_heartrate") or activity.get("icu_hr_max") or 190
    name = event.get("name", "").lower()

    if hr and hr_max:
        pct = hr / hr_max * 100
        if pct > 82 and "z2" in name:
            return f"HR {pct:.0f}% — boven Z2. Volgende keer rustiger. Een gelukkige atleet is een snelle atleet!"
        elif pct < 70 and "threshold" in name:
            return f"HR {pct:.0f}% — aan de lage kant voor threshold. Niet erg, luister naar je lichaam."

    return "Workout voltooid. Goed bezig! Een gelukkige atleet is een snelle atleet."


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
