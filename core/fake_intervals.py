"""Gedeelde intervals.icu-fixture: tests én INTERVALS_FAKE-modus (Fase 4).

Eén bron van waarheid voor nep-intervals.icu-data:

- ``tests/mock_intervals.py`` re-exporteert :class:`MockIntervals` +
  :func:`install` voor de pytest-integratietests (monkeypatch-pad);
- ``intervals_client`` roept bij import :func:`install_fake` aan als de
  env-flag ``INTERVALS_FAKE`` aan staat, zodat frontend-dev en smoke
  volledig offline werken tegen exact dezelfde fixture.

Het fixture-weekje is realistisch klein:

- gisteren: voltooide easy run (event + activity, gematcht);
- vandaag: geplande easy run (niet voltooid);
- morgen: endurance-spin (morgen-preview op /api/today);
- volgende week: ma easy run · wo threshold-rit · za long run —
  volledig in de toekomst, dus verplaatsbaar voor de /move-test.
"""
from __future__ import annotations

import itertools
import os
from datetime import date, timedelta

# Functienamen die gepatcht worden op de intervals_client-module.
PATCHED = (
    "get_athlete", "get_activities", "get_wellness", "get_wellness_today",
    "get_events", "create_event", "update_event", "delete_event",
    "bulk_delete_events", "get_activity_detail", "get_activity_streams",
)


def fake_enabled() -> bool:
    """True als de env-flag ``INTERVALS_FAKE`` aan staat."""
    return os.environ.get("INTERVALS_FAKE", "").strip().lower() in {
        "1", "true", "yes", "on"}


def _event(eid: str, d: date, name: str, sport: str = "Run",
           load: int = 45, description: str = "- 40m 60-65% Pace",
           time: str = "07:00:00", category: str = "WORKOUT") -> dict:
    return {
        "id": eid,
        "category": category,
        "start_date_local": f"{d.isoformat()}T{time}",
        "name": name,
        "type": sport,
        "description": description,
        "load_target": load,
    }


def _activity(aid: str, d: date, name: str, sport: str = "Run",
              tss: int = 42, minutes: int = 40, km: float = 7.5) -> dict:
    return {
        "id": aid,
        "start_date_local": f"{d.isoformat()}T07:02:11",
        "name": name,
        "type": sport,
        "icu_training_load": tss,
        "moving_time": minutes * 60,
        "distance": km * 1000,
        "average_heartrate": 138,
        "icu_ftp": 290,
    }


class MockIntervals:
    """In-memory intervals.icu met het fixture-weekje + call-log."""

    def __init__(self, today: date | None = None):
        self.today = today or date.today()
        self.monday = self.today - timedelta(days=self.today.weekday())
        self.next_monday = self.monday + timedelta(days=7)
        self.calls: list[tuple] = []          # (fn, args...) mutatie-log
        self._ids = itertools.count(9000)
        self.fail_events = False              # True → get_events gooit
        self.fail_activities = False          # True → get_activities gooit

        t = self.today
        nm = self.next_monday
        done_day = max(t - timedelta(days=1), self.monday)
        self.events: list[dict] = [
            _event("e_done", done_day, "Easy run 40 min",
                   "Run", 45),
            _event("e_today", t, "Easy run 40 min", "Run", 45),
            _event("e_tomorrow", t + timedelta(days=1),
                   "Endurance spin 60 min", "Ride", 50,
                   description="- 60m 65-75%"),
            # Volgende week — volledig verplaatsbaar (move-test).
            _event("e_nw_run", nm, "Easy run 40 min", "Run", 45),
            _event("e_nw_bike", nm + timedelta(days=2),
                   "Threshold sustained 60 min", "Ride", 75,
                   description="3x\n- 10m 95-100%\n- 5m 55%"),
            _event("e_nw_long", nm + timedelta(days=5), "Long run 90 min",
                   "Run", 95, description="- 90m 60-68% Pace"),
        ]
        self.activities: list[dict] = [
            _activity("a_done", done_day, "Easy run 40 min"),
            # Wat historie voor CTL/trends (3 weken terug, 2/wk).
            *[
                _activity(f"a_hist_{i}", t - timedelta(days=3 + 3 * i),
                          "Easy run", tss=40 + i)
                for i in range(7)
            ],
        ]
        self.wellness: list[dict] = [
            {"id": (t - timedelta(days=i)).isoformat(), "hrv": 62.0 - i,
             "restingHR": 46, "sleepSecs": 7.2 * 3600}
            for i in range(10)
        ]

    # ── reads ───────────────────────────────────────────────────────────

    def get_athlete(self) -> dict:
        return {"name": "Test Atleet", "ftp": 290, "type": "Run"}

    def get_events(self, start=None, end=None, resolve=False) -> list:
        if self.fail_events:
            raise ConnectionError("mock: intervals.icu onbereikbaar")
        start = start or self.today
        end = end or (self.today + timedelta(days=14))
        out = []
        for e in self.events:
            d = e["start_date_local"][:10]
            if start.isoformat() <= d <= end.isoformat():
                e = dict(e)
                if resolve:
                    e["workout_doc"] = {"duration": 2400, "steps": []}
                out.append(e)
        return out

    def get_activities(self, start=None, end=None) -> list:
        if self.fail_activities:
            raise ConnectionError("mock: intervals.icu onbereikbaar")
        start = start or (self.today - timedelta(days=30))
        end = end or self.today
        return [
            a for a in self.activities
            if start.isoformat() <= a["start_date_local"][:10] <= end.isoformat()
        ]

    def get_wellness(self, start=None, end=None) -> list:
        start = start or (self.today - timedelta(days=14))
        end = end or self.today
        return [
            w for w in self.wellness
            if start.isoformat() <= w["id"] <= end.isoformat()
        ]

    def get_wellness_today(self) -> dict:
        recs = [w for w in self.wellness if w["id"] == self.today.isoformat()]
        return recs[0] if recs else {}

    def get_activity_detail(self, activity_id, intervals=True) -> dict:
        return next(
            (a for a in self.activities if str(a["id"]) == str(activity_id)),
            {})

    def get_activity_streams(self, activity_id, types=None) -> dict:
        return {}

    # ── writes (gelogd in self.calls) ───────────────────────────────────

    def create_event(self, event_date, name, description="",
                     category="WORKOUT", sport_type="Ride",
                     load_target=None, start_time=None) -> dict:
        eid = f"mock_{next(self._ids)}"
        time_part = "00:00:00"
        if start_time:
            time_part = (start_time if len(str(start_time)) > 5
                         else f"{start_time}:00")
        event = {
            "id": eid,
            "category": category,
            "start_date_local": f"{event_date.isoformat()}T{time_part}",
            "name": name,
            "description": description,
            "type": sport_type,
            "load_target": load_target,
        }
        self.events.append(event)
        self.calls.append(("create_event", eid, name))
        return event

    def update_event(self, event_id, **kwargs) -> dict:
        event = next(
            (e for e in self.events if str(e["id"]) == str(event_id)), None)
        if event is None:
            raise LookupError(f"mock: event {event_id} bestaat niet")
        event.update(kwargs)
        self.calls.append(("update_event", str(event_id), kwargs))
        return dict(event)

    def delete_event(self, event_id) -> None:
        self.events = [
            e for e in self.events if str(e["id"]) != str(event_id)]
        self.calls.append(("delete_event", str(event_id)))

    def bulk_delete_events(self, start, end, category="WORKOUT") -> int:
        doomed = [
            e["id"] for e in self.get_events(start, end)
            if e.get("category") == category
        ]
        for eid in doomed:
            self.delete_event(eid)
        return len(doomed)


def install(monkeypatch, mock: MockIntervals | None = None) -> MockIntervals:
    """Patch alle netwerk-functies van intervals_client met de mock (tests)."""
    import intervals_client

    mock = mock or MockIntervals()
    for name in PATCHED:
        monkeypatch.setattr(intervals_client, name, getattr(mock, name))
    return mock


def install_fake(mock: MockIntervals | None = None) -> MockIntervals:
    """Patch intervals_client in-place (INTERVALS_FAKE-modus, geen pytest).

    Idempotent genoeg voor server-gebruik: elke aanroep installeert een
    verse fixture. Returnt de geïnstalleerde mock zodat callers (smoke,
    dev-tooling) erbij kunnen.
    """
    import intervals_client

    mock = mock or MockIntervals()
    for name in PATCHED:
        setattr(intervals_client, name, getattr(mock, name))
    intervals_client.FAKE_MODE = True
    return mock
