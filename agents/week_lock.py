"""week_lock — een week vastzetten zodat de planner hem niet overschrijft.

Waarom dit in intervals.icu leeft en niet in state.json: de planner draait op
meerdere plekken (lokaal, Railway-scheduler, handmatig) en die delen geen
state-bestand. Wat ze wel altijd delen is de intervals.icu-kalender. Een
NOTE-event in de week zelf is dus de enige lock die overal geldt — en hij is
meteen zichtbaar in de app, dus je kunt hem niet per ongeluk vergeten.

De lock stopt alleen *regeneratie* van een hele week (plan_week /
week_planner.build_week). Gerichte acties op één sessie — swap, skip,
verzachten via adjust.py — blijven werken; dat zijn bewuste ingrepen, geen
overschrijvingen.
"""

from __future__ import annotations

from datetime import date, timedelta

LOCK_NOTE_NAME = "[LOCK] Week vastgezet"
LOCK_CATEGORY = "NOTE"


def find_locks(events: list[dict]) -> list[dict]:
    """Alle lock-events in een lijst events.

    Meervoud, want er kunnen er meer dan één zijn: als `lock_week` draait
    terwijl intervals.icu even onbereikbaar is, kan hij een tweede notitie
    aanmaken. Zou `unlock_week` er dan maar één weghalen, dan lijkt de week
    ontgrendeld terwijl hij het niet is.
    """
    return [e for e in events or []
            if (e.get("name") or "").startswith(LOCK_NOTE_NAME)]


def find_lock(events: list[dict]) -> dict | None:
    """Het eerste lock-event, of None.

    Pure functie: geen API-calls, zodat callers die de events toch al ophaalden
    geen tweede round-trip doen.
    """
    locks = find_locks(events)
    return locks[0] if locks else None


def is_locked(events: list[dict]) -> bool:
    return find_lock(events) is not None


def lock_reason(events: list[dict]) -> str:
    """De reden-tekst uit het lock-event (regel 1 van de beschrijving)."""
    lock = find_lock(events)
    if not lock:
        return ""
    desc = (lock.get("description") or "").strip()
    return desc.splitlines()[0] if desc else ""


def fetch_lock(week_start: date) -> dict | None:
    """Haal het lock-event op uit intervals.icu voor de week van `week_start`.

    Bij een API-fout geven we een *pseudo-lock* terug in plaats van None.
    Reden: als we niet kunnen vaststellen dat een week vrij is, is wissen de
    gevaarlijke gok. Niet-plannen is altijd terug te draaien, een gewiste week
    niet.
    """
    import intervals_client as api

    try:
        events = api.get_events(week_start, week_start + timedelta(days=6))
    except Exception as exc:
        return {
            "name": LOCK_NOTE_NAME,
            "description": f"Lock-status onbekend — intervals.icu niet bereikbaar ({exc}).",
            "_unknown": True,
        }
    return find_lock(events)


def lock_week(week_start: date, reason: str = "") -> dict:
    """Zet een week vast. Idempotent: bestaat de lock al, dan hergebruiken we hem.

    Kunnen we de bestaande events niet ophalen, dan schrijven we niets. Blind
    een lock aanmaken zou een tweede notitie kunnen opleveren naast een lock
    die er al is, en dan haalt `unlock_week` er straks maar één weg.
    """
    import intervals_client as api

    existing = fetch_lock(week_start)
    if existing and existing.get("_unknown"):
        raise RuntimeError(
            f"Kan lock-status van {week_start} niet vaststellen: "
            f"{existing.get('description')}. Niets gewijzigd — probeer opnieuw."
        )
    if existing:
        return existing

    body = reason.strip() or "Handmatig vastgezet."
    body += (
        "\n\nZolang deze notitie in de week staat laat de planner hem met rust:"
        "\n- de zondagavond-scheduler slaat deze week over"
        "\n- plan_week.py --schrijf weigert te wissen"
        "\n\nOntgrendelen: verwijder deze notitie, of draai"
        f"\n  python plan_week.py --week {week_start.isoformat()} --ontgrendel"
    )
    return api.create_event(
        event_date=week_start,
        name=LOCK_NOTE_NAME,
        description=body,
        category=LOCK_CATEGORY,
        sport_type="Other",
    )


def unlock_week(week_start: date) -> bool:
    """Haal alle locks van deze week weg. Geeft True als er iets verwijderd is.

    Alle, niet de eerste: één achtergebleven lock-notitie houdt de week
    vergrendeld terwijl het commando zegt dat hij vrij is.
    """
    import intervals_client as api

    try:
        events = api.get_events(week_start, week_start + timedelta(days=6))
    except Exception as exc:
        raise RuntimeError(
            f"Kan events van {week_start} niet ophalen ({exc}) — "
            "lock niet verwijderd."
        )

    verwijderd = 0
    for lock in find_locks(events):
        if lock.get("id"):
            api.delete_event(lock["id"])
            verwijderd += 1
    return verwijderd > 0
