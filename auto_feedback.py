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
import shared
from agents import feedback_engine
from agents import adjustments_log
from agents.deviation_classifier import detect_deviations
from agents.adapt_week import adapt_week

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


def _build_week_matched(events: list, activities: list) -> list:
    """Bouw {event, activity, done}-lijst (matched-formaat van feedback_engine)."""
    return shared.match_events_activities(events or [], activities or [])


def find_new_completed_workouts() -> tuple[list[dict], list, list]:
    """Vind workouts die voltooid zijn maar nog geen feedback hebben gekregen.

    Returns: (new_workouts, week_events, week_activities)
    De week_events/activities worden meegegeven zodat de aanroepende code ze
    kan gebruiken voor de buur-workout context in feedback_engine.
    """
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
        return [], [], []

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

    return results, events, activities


_types_match = shared.types_match
_load_state = shared.load_state


def generate_feedback(event: dict, activity: dict, week_matched: list = None) -> str:
    """Genereer workout-specifieke feedback via feedback_engine.

    `week_matched` is de lijst van {event, activity, done} dicts voor de week
    waarin deze workout valt — gebruikt voor de buur-workout context (gisteren/morgen).
    """
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
        week_events=week_matched,
        recent_28d=recent_28d,
    )


def post_feedback_to_intervals(event: dict, feedback: str, dry_run: bool = False):
    """Post feedback als notitie bij het event in intervals.icu."""
    event_id = event.get("id")
    if not event_id:
        return

    # Voeg feedback toe aan de beschrijving
    current_desc = event.get("description", "")
    # Strip **bold** markdown — intervals.icu rendert geen markdown
    clean_feedback = feedback.replace("**", "")
    feedback_block = f"\n\n--- Coach Feedback ---\n{clean_feedback}"

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


def run_adaptive_cycle(
    week_events: list,
    week_activities: list,
    dry_run: bool = False,
    detect_only: bool = False,
) -> dict | None:
    """Detecteer deviations en pas — indien toegestaan — de week aan.

    Returns een dict met samenvatting of None als er niets te doen viel.
    Alle intervals.icu writes + log writes gaan via deze functie.
    """
    from datetime import date as _date

    # Volume-compensatie voor runs: bij overshoot van vandaag resterende
    # runs deze week inkorten. Draait altijd (niet alleen bij deviations).
    try:
        from agents import volume_compensation as _vc
        monday = _date.today() - timedelta(days=_date.today().weekday())
        vc_updates = _vc.apply_to_events(
            events=week_events,
            activities=week_activities,
            week_start=monday,
        )
        if vc_updates and not (dry_run or detect_only):
            print(f"  Volume-compensatie: {len(vc_updates)} run(s) ingekort")
            for u in vc_updates:
                try:
                    api.update_event(u["event_id"], **u["update"])
                    print(f"    {u['event_id']}: {u['van_km']}km → {u['naar_km']}km ({u['reden']})")
                except Exception as _exc:
                    print(f"    {u['event_id']} FAILED: {_exc}")
        elif vc_updates:
            for u in vc_updates:
                print(f"  [DRY] {u['event_id']}: {u['van_km']}km → {u['naar_km']}km")
    except Exception as _vc_exc:
        print(f"  Volume-compensatie skip: {_vc_exc}")

    deviations = detect_deviations(week_events, week_activities)
    if not deviations:
        print("  Geen deviations gedetecteerd.")
        return None

    print(f"  {len(deviations)} deviation(s) gedetecteerd:")
    for d in deviations:
        tag = " [SACRED]" if d.sacred else ""
        print(f"    - {d.type}{tag} (TSS {d.tss_planned:.0f} → {d.tss_actual:.0f})")

    state = _load_state()
    result = adapt_week(week_events, deviations, state)

    print(f"\n  Plan-impact: {len(result.modifications)} wijziging(en)")
    print(f"  Narrative: {result.narrative}")
    print(f"  Invariant: {result.invariant}\n")

    if detect_only:
        print("  [DETECT-ONLY] Geen wijzigingen doorgevoerd.")
        return {"deviations": deviations, "result": result, "applied": False}

    if dry_run:
        print("  [DRY RUN] Geen wijzigingen doorgevoerd.")
        return {"deviations": deviations, "result": result, "applied": False}

    # Apply modifications naar intervals.icu — per-mod success tracking.
    # Bij failure halverwege NIET de hele batch als applied=True markeren;
    # revert moet exact weten welke mods écht live zijn.
    all_ok = True
    for mod in result.modifications:
        try:
            if mod.action == "modify":
                api.update_event(mod.event_id, **{
                    k: v for k, v in mod.after.items()
                    if k in ("name", "description", "load_target", "duration")
                })
                mod.applied = True
            elif mod.action == "create":
                ev = mod.after
                ev_date = _date.fromisoformat(ev["start_date_local"][:10])
                resp = api.create_event(
                    event_date=ev_date,
                    name=ev.get("name", "Herpland"),
                    description=ev.get("description", ""),
                    category="WORKOUT",
                )
                # Persist het nieuwe event-id zodat revert het later kan deleten
                if isinstance(resp, dict) and resp.get("id"):
                    mod.created_event_id = str(resp["id"])
                mod.applied = True
            elif mod.action == "delete":
                api.delete_event(mod.event_id)
                mod.applied = True
            print(f"    {mod.action} {mod.event_id} OK")
        except Exception as exc:  # pragma: no cover — I/O failure
            mod.applied = False
            mod.error = str(exc)
            all_ok = False
            print(f"    {mod.action} {mod.event_id} FAILED: {exc}")

    # Log entry — bevat per-mod applied status zodat revert alleen écht
    # toegepaste mods terugdraait.
    monday = _date.today() - timedelta(days=_date.today().weekday())
    entry = adjustments_log.build_entry(monday, deviations, result, applied=all_ok)
    adjustments_log.append(entry)
    print(f"  Log entry geschreven: {entry['id']} (all_ok={all_ok})")
    return {"deviations": deviations, "result": result, "applied": all_ok}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Auto-feedback op voltooide workouts")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--setup", action="store_true")
    parser.add_argument("--no-adapt", action="store_true",
                        help="Skip de adaptive cycle (alleen feedback, geen plan-wijzigingen)")
    parser.add_argument("--detect-only", action="store_true",
                        help="Detecteer deviations maar schrijf niets")
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

    new_workouts, week_events, week_activities = find_new_completed_workouts()
    if not new_workouts:
        print("  Geen nieuwe voltooide workouts.")
        # Toch adaptive cycle draaien — ook zonder nieuwe feedback kunnen
        # er sacred sessies gemist zijn die herplanning vereisen.
        if not args.no_adapt:
            print("\n  Adaptive cycle: deviations detecteren...")
            try:
                run_adaptive_cycle(
                    week_events,
                    week_activities,
                    dry_run=args.dry_run,
                    detect_only=args.detect_only,
                )
            except Exception as exc:
                print(f"  Adaptive cycle failed: {exc}")
        return

    print(f"  {len(new_workouts)} nieuwe voltooide workout(s) gevonden.\n")

    # Bouw matched-formaat één keer voor de hele week, hergebruik voor elke workout
    week_matched = _build_week_matched(week_events, week_activities)

    log = _load_feedback_log()
    email_body = []

    for item in new_workouts:
        act = item["activity"]
        event = item["event"]
        act_name = act.get("name", "?")
        event_name = event.get("name", "?")
        act_date = act.get("start_date_local", "")[:10]

        print(f"  {act_date} — {event_name}")
        feedback = generate_feedback(event, act, week_matched=week_matched)
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

    # ── Adaptive cycle ───────────────────────────────────────────────────
    if not args.no_adapt:
        print("\n  Adaptive cycle: deviations detecteren...")
        try:
            run_adaptive_cycle(
                week_events,
                week_activities,
                dry_run=args.dry_run,
                detect_only=args.detect_only,
            )
        except Exception as exc:
            print(f"  Adaptive cycle failed: {exc}")


if __name__ == "__main__":
    main()
