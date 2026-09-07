"""session_lock — één sessie op de kalender vastzetten.

``week_lock`` bevriest een hele week; dat is te grof voor het geval dat de
atleet elke week heeft: het plan mag opnieuw gegenereerd worden, maar één
afspraak staat vast. Denk aan de marathon-bloksessie op zondag — die staat
in de groepsagenda, niet in dit systeem, en de weekplanner wist hem bij de
eerstvolgende regeneratie zonder het te weten (hij verwijdert álle
toekomstige ``WORKOUT``-events van de week en zet er zijn eigen voor in de
plaats).

Waarom de markering in de kalender leeft en niet in ``state.json`` of de
placements-tabel: de planner draait lokaal, via de Railway-scheduler en
handmatig, en die delen geen database. Wat ze wél altijd delen is
intervals.icu. Dezelfde afweging als bij ``week_lock``: de kalender is de
enige plek waar een lock overal geldt — en je ziet hem meteen in de app,
dus je kunt niet vergeten dat hij er staat.

Een vastgezette sessie:
- overleeft een regeneratie van de week (``week_planner.build_week``);
- houdt zijn dag bezet, zodat de planner er niets bovenop stapelt
  (``availability.get_pinned_day_names`` → ``skip_run_days``);
- wordt niet verschoven door de replan-solver (``core.replan``).

Gerichte acties op de sessie zelf — swap, skip, verplaatsen via de app —
blijven gewoon werken. Dat zijn bewuste ingrepen, geen overschrijvingen.
"""

from __future__ import annotations

from datetime import date, timedelta

PIN_MARKER = "[VAST]"

DAYS_NL = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag",
           "zaterdag", "zondag"]


def is_pinned(event: dict | None) -> bool:
    """Staat deze sessie vast?

    De markering telt in de naam én in de beschrijving. De naam is de
    zichtbare plek (je ziet in de kalender meteen wat vaststaat); de
    beschrijving is er voor sessies waarvan de naam uit een externe bron
    komt en die je liever niet hernoemt.
    """
    if not event:
        return False
    haystack = f"{event.get('name') or ''} {event.get('description') or ''}"
    return PIN_MARKER.lower() in haystack.lower()


def find_pinned(events: list[dict] | None) -> list[dict]:
    """Alle vastgezette events uit een lijst. Pure functie, geen API-calls."""
    return [e for e in events or [] if is_pinned(e)]


def strip_marker(name: str | None) -> str:
    """Naam zonder de markering — voor het vrijgeven van een sessie."""
    out = (name or "")
    lowered = out.lower()
    marker = PIN_MARKER.lower()
    while marker in lowered:
        i = lowered.index(marker)
        out = out[:i] + out[i + len(PIN_MARKER):]
        lowered = out.lower()
    return out.strip()


def pinned_day_names(events: list[dict] | None, week_start: date) -> list[str]:
    """NL-dagnamen binnen deze week waarop een vastgezette sessie staat."""
    out: list[str] = []
    for e in find_pinned(events):
        stamp = str(e.get("start_date_local") or e.get("start_date") or "")[:10]
        try:
            offset = (date.fromisoformat(stamp) - week_start).days
        except ValueError:
            continue
        if 0 <= offset < 7 and DAYS_NL[offset] not in out:
            out.append(DAYS_NL[offset])
    return out


def fetch_week(week_start: date) -> list[dict]:
    """Events van één week ophalen. Gooit door bij een API-fout."""
    import intervals_client as api

    return api.get_events(week_start, week_start + timedelta(days=6)) or []


def pin_event(event_id: str, event: dict | None = None) -> dict:
    """Zet één sessie vast: markering vóór de naam.

    Idempotent: een sessie die al vaststaat wordt niet dubbel gemarkeerd.
    Zonder ``event`` halen we de huidige naam op, want intervals.icu
    verwacht bij een PUT de volledige naam en niet een fragment.
    """
    import intervals_client as api

    if event is None:
        event = _find_event(event_id)
    if not event:
        raise LookupError(f"Event {event_id} niet gevonden in de kalender")
    if is_pinned(event):
        return event

    naam = (event.get("name") or "").strip()
    if not naam:
        raise ValueError(f"Event {event_id} heeft geen naam om te markeren")
    nieuwe_naam = f"{PIN_MARKER} {naam}".strip()
    result = api.update_event(event_id, name=nieuwe_naam)
    _set_placement_locked(event_id, True)
    return result


def unpin_event(event_id: str, event: dict | None = None) -> dict:
    """Geef een vastgezette sessie weer vrij."""
    import intervals_client as api

    if event is None:
        event = _find_event(event_id)
    if not event:
        raise LookupError(f"Event {event_id} niet gevonden in de kalender")

    naam = strip_marker(event.get("name")) or "Sessie"
    beschrijving = event.get("description")
    payload: dict = {"name": naam}
    if beschrijving and PIN_MARKER.lower() in beschrijving.lower():
        payload["description"] = _strip_marker_lines(beschrijving)
    result = api.update_event(event_id, **payload)
    _set_placement_locked(event_id, False)
    return result


def pin_day(on_date: date) -> list[dict]:
    """Zet alle workouts van één dag vast. Geeft de gemuteerde events terug."""
    week_start = on_date - timedelta(days=on_date.weekday())
    events = fetch_week(week_start)
    doelen = [
        e for e in events
        if e.get("category") == "WORKOUT"
        and str(e.get("start_date_local") or "")[:10] == on_date.isoformat()
    ]
    return [pin_event(str(e["id"]), e) for e in doelen if e.get("id")]


def unpin_day(on_date: date) -> list[dict]:
    """Geef alle vastgezette sessies van één dag weer vrij."""
    week_start = on_date - timedelta(days=on_date.weekday())
    events = fetch_week(week_start)
    doelen = [
        e for e in find_pinned(events)
        if str(e.get("start_date_local") or "")[:10] == on_date.isoformat()
    ]
    return [unpin_event(str(e["id"]), e) for e in doelen if e.get("id")]


# ── intern ────────────────────────────────────────────────────────────────

def _find_event(event_id: str) -> dict | None:
    import intervals_client as api

    today = date.today()
    try:
        events = api.get_events(today - timedelta(days=7),
                                today + timedelta(days=28))
    except Exception:
        return None
    return next((e for e in events or []
                 if str(e.get("id")) == str(event_id)), None)


def _strip_marker_lines(description: str) -> str:
    kept = [
        line for line in description.splitlines()
        if PIN_MARKER.lower() not in line.lower()
    ]
    return "\n".join(kept).strip()


def _set_placement_locked(event_id: str, locked: bool) -> None:
    """Houd de placements-tabel in de pas — faalt stil.

    De kalender is de bron van waarheid; de placements-rij is metadata voor
    de solver. Een ontbrekende rij (externe sessie, nooit door ons geplaatst)
    mag het vastzetten nooit blokkeren.
    """
    try:
        import history_db

        history_db.set_placement_locked(str(event_id), locked)
    except Exception:
        pass
