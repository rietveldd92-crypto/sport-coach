"""APScheduler-jobs voor de API-server (Fase 3, UPGRADE_PLAN §7).

Draait in hetzelfde proces als FastAPI (lifespan in api/main.py):

- dagelijks 07:30 — auto_feedback-run (feedback + adaptive cycle), de
  importeerbare kern uit auto_feedback.run_feedback_cycle;
- zondag 18:00 — weekly_recalibration (rolling re-periodisatie §4.2)
  + de volgende week plannen via de bestaande plan-flow + solver.

Gate: env-flag ``SCHEDULER_ENABLED`` (default uit — tests en losse
CLI-runs starten dus nooit per ongeluk achtergrondjobs).
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

_log = logging.getLogger(__name__)


def run_daily_feedback() -> None:
    """Dagelijkse auto_feedback-run (zelfde kern als de CLI)."""
    try:
        from auto_feedback import run_feedback_cycle

        result = run_feedback_cycle()
        _log.info("auto_feedback: %s workout(s) verwerkt, adapted=%s",
                  result.get("processed"), result.get("adapted"))
    except Exception:
        _log.exception("auto_feedback-job faalde")


def run_sunday_recalibration() -> None:
    """Zondagavond: macroplan herijken + volgende week plannen."""
    try:
        from core.replan_goal import weekly_recalibration

        activities = None
        try:
            import intervals_client as api

            activities = api.get_activities(
                start=date.today() - timedelta(days=42), end=date.today())
        except Exception as exc:
            _log.warning("intervals.icu niet beschikbaar (%s) — "
                         "herijking op state", exc)
        report = weekly_recalibration(activities=activities)
        _log.info("weekly_recalibration: %s (%s)",
                  report.get("status"), report.get("advice"))
    except Exception:
        _log.exception("weekly_recalibration-job faalde")

    try:
        import plan_week

        next_monday = date.today() - timedelta(days=date.today().weekday()) \
            + timedelta(days=7)
        plan_week.run(next_monday, dry_run=False)
        _log.info("volgende week (%s) gepland", next_monday)
    except Exception:
        _log.exception("weekplanning-job faalde")


def create_scheduler():
    """Geconfigureerde (niet-gestarte) BackgroundScheduler."""
    from apscheduler.schedulers.background import BackgroundScheduler

    scheduler = BackgroundScheduler()
    scheduler.add_job(run_daily_feedback, "cron", hour=7, minute=30,
                      id="auto_feedback", replace_existing=True)
    scheduler.add_job(run_sunday_recalibration, "cron",
                      day_of_week="sun", hour=18, minute=0,
                      id="weekly_recalibration", replace_existing=True)
    return scheduler
