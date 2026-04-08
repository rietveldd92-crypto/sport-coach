import os
import requests
from dotenv import load_dotenv
from datetime import date, timedelta

load_dotenv()

ATHLETE_ID = os.getenv("INTERVALS_ATHLETE_ID")
API_KEY = os.getenv("INTERVALS_API_KEY")
BASE_URL = "https://intervals.icu/api/v1"
TIMEOUT = 10  # seconden


def _auth():
    return ("API_KEY", API_KEY)


def get_athlete() -> dict:
    """Haal basis athlete informatie op."""
    r = requests.get(f"{BASE_URL}/athlete/{ATHLETE_ID}", auth=_auth(), timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def get_activities(start: date = None, end: date = None) -> list:
    """Haal activiteiten op. Standaard: afgelopen 30 dagen."""
    if end is None:
        end = date.today()
    if start is None:
        start = end - timedelta(days=30)

    params = {
        "oldest": start.isoformat(),
        "newest": end.isoformat(),
    }
    r = requests.get(f"{BASE_URL}/athlete/{ATHLETE_ID}/activities", auth=_auth(), params=params)
    r.raise_for_status()
    return r.json()


def get_wellness(start: date = None, end: date = None) -> list:
    """Haal wellness data op (HRV, slaap, gewicht, etc.)."""
    if end is None:
        end = date.today()
    if start is None:
        start = end - timedelta(days=14)

    params = {
        "oldest": start.isoformat(),
        "newest": end.isoformat(),
    }
    r = requests.get(f"{BASE_URL}/athlete/{ATHLETE_ID}/wellness", auth=_auth(), params=params)
    r.raise_for_status()
    return r.json()


def get_events(start: date = None, end: date = None, resolve: bool = False) -> list:
    """Haal geplande events/workouts op uit de kalender.

    Args:
        start: oudste datum (default vandaag).
        end: nieuwste datum (default +14 dagen).
        resolve: als True wordt workout_doc meegestuurd met resolved
            power/hr/pace targets (nodig voor TrainingPeaks-sync). Default
            False om bestaande callsites niet te breken.
    """
    if end is None:
        end = date.today() + timedelta(days=14)
    if start is None:
        start = date.today()

    params = {
        "oldest": start.isoformat(),
        "newest": end.isoformat(),
    }
    if resolve:
        params["resolve"] = "true"
    r = requests.get(f"{BASE_URL}/athlete/{ATHLETE_ID}/events", auth=_auth(), params=params)
    r.raise_for_status()
    return r.json()


def create_event(event_date: date, name: str, description: str = "", category: str = "WORKOUT",
                 sport_type: str = "Ride", load_target: int = None) -> dict:
    """Maak een nieuw event/workout aan in de kalender."""
    payload = {
        "category": category,
        "start_date_local": f"{event_date.isoformat()}T00:00:00",
        "name": name,
        "description": description,
        "type": sport_type,
    }
    if load_target is not None:
        payload["load_target"] = load_target

    r = requests.post(f"{BASE_URL}/athlete/{ATHLETE_ID}/events", auth=_auth(), json=payload, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def update_event(event_id: str, **kwargs) -> dict:
    """Wijzig een bestaand event. Geef velden mee als keyword arguments."""
    r = requests.put(f"{BASE_URL}/athlete/{ATHLETE_ID}/events/{event_id}", auth=_auth(), json=kwargs, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def delete_event(event_id: str) -> None:
    """Verwijder een event uit de kalender."""
    r = requests.delete(f"{BASE_URL}/athlete/{ATHLETE_ID}/events/{event_id}", auth=_auth(), timeout=TIMEOUT)
    r.raise_for_status()


def bulk_delete_events(start: date, end: date, category: str = "WORKOUT") -> int:
    """Verwijder alle events van een bepaalde categorie in een periode. Geeft aantal verwijderde events terug."""
    events = get_events(start, end)
    deleted = 0
    for event in events:
        if event.get("category") == category:
            try:
                delete_event(event["id"])
                deleted += 1
            except Exception:
                pass
    return deleted


def get_wellness_today() -> dict:
    """Haal wellness data van vandaag op."""
    today = date.today()
    r = requests.get(
        f"{BASE_URL}/athlete/{ATHLETE_ID}/wellness/{today.isoformat()}",
        auth=_auth()
    )
    if r.status_code == 404:
        return {}
    r.raise_for_status()
    return r.json()


def get_activity_detail(activity_id: str, intervals: bool = True) -> dict:
    """Haal volledige activiteit op inclusief intervals/laps."""
    params = {}
    if intervals:
        params["intervals"] = "true"
    r = requests.get(f"{BASE_URL}/activity/{activity_id}", auth=_auth(), params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def get_activity_streams(activity_id: str, types: list[str] = None) -> dict:
    """Haal second-by-second streams op (heartrate, watts, cadence, pace, distance).

    Returns dict met keys per stream type, elk een lijst van waarden.
    """
    params = {}
    if types:
        params["types"] = ",".join(types)
    r = requests.get(f"{BASE_URL}/activity/{activity_id}/streams.json",
                     auth=_auth(), params=params, timeout=30)
    r.raise_for_status()
    return r.json()


if __name__ == "__main__":
    print("=== Intervals.icu connectie test ===\n")
    athlete = get_athlete()
    print(f"Verbonden als: {athlete.get('name', 'Onbekend')}")
    print(f"Athlete ID: {ATHLETE_ID}")
    print(f"Sport: {athlete.get('type', '-')}")
    print(f"FTP: {athlete.get('ftp', '-')} W")
    print("\nConnectie OK!")
