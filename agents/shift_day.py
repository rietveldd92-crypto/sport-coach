"""Shift day — verplaats Z1/Z2 trainingen als een dag minder tijd heeft.

Alternatief voor full replan wanneer de gebruiker zijn beschikbaarheid
op één dag verlaagt. In plaats van de hele week opnieuw te bouwen,
proberen we eerst de bestaande planning te behouden door "easy" sessies
van de krappe dag naar andere dagen te verschuiven.

Hard sessies (threshold, intervals, tempo, long run, etc.) blijven op
hun dag — die zijn gepland rond CTL/piek-momenten. Alleen Z1/Z2 schuift.

Regels bij het kiezen van een kandidaatdag:
- Niet in het verleden.
- Moet genoeg resterende beschikbaarheid hebben (planned + shifted ≤ avail).
- Niet op een 0-minuten rustdag.
- Geen 2 runs op opeenvolgende dagen tijdens injury return.
- Long run blijft op zondag (beweging-van zondag vermijden; beweging-naar
  zaterdag alleen als de zondag leeg is).

Puur functioneel — geen API-calls hier. De wrapper in app.py doet de
`api.update_event` aanroepen na confirmation.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

# Keywords die een event als "hard" (kwaliteit) markeren. Overlapt bewust
# met reschedule.QUALITY_TYPES en week_planner hard-types. Hier intentioneel
# ruimer: ook heuvels, sprints, race-sim en marathontempo tellen mee.
HARD_KEYWORDS = (
    "threshold", "drempel", "sweetspot", "sweet spot",
    "tempo", "interval", "intervals", "yasso", "cruise",
    "vo2", "tabata", "microburst", "over-under", "over_under",
    "sprint", "hill", "heuvel", "fartlek", "race",
    "marathon pace", "marathontempo", "cp_intervals",
)

LONG_RUN_KEYWORDS = ("lange duurloop", "long run")

# Easy/Z2 keywords — alleen deze events zijn kandidaat om te verschuiven.
# Als een event geen van deze bevat en ook niet hard is, behandelen we 'm
# als "onbekend" en laten we 'm staan (veilige default).
EASY_KEYWORDS = (
    "z2", "z1", "easy", "duurloop", "endurance", "duurrit",
    "recovery", "herstel", "spin", "fatmax", "lt1",
    "cadence", "single leg", "coffee",
)


def _event_name(event: dict) -> str:
    return (event.get("name") or "").lower()


def is_hard_event(event: dict) -> bool:
    name = _event_name(event)
    return any(k in name for k in HARD_KEYWORDS)


def is_long_run(event: dict) -> bool:
    name = _event_name(event)
    return any(k in name for k in LONG_RUN_KEYWORDS)


def is_easy_event(event: dict) -> bool:
    """True als het event als 'easy' (Z1/Z2) herkend is en dus shiftbaar."""
    if is_hard_event(event):
        return False
    name = _event_name(event)
    return any(k in name for k in EASY_KEYWORDS)


def is_run(event: dict) -> bool:
    return event.get("type") == "Run"


def event_duration_min(event: dict) -> int:
    """Duur in minuten. Probeert moving_time → load_target heuristiek → 0.

    Voor shift-doelen hebben we een ondergrens nodig; als we duur niet
    kunnen vaststellen, retourneren we 0 zodat caller 'm niet plant als
    tijdsvreter (de cap-logica vangt 'm dan alsnog).
    """
    mt = event.get("moving_time")
    if mt:
        return round(mt / 60)
    wd = event.get("workout_doc") or {}
    dur_s = wd.get("duration")
    if dur_s:
        return round(dur_s / 60)
    # Parse "60 min" / "90min" uit naam
    name = _event_name(event)
    if "min" in name:
        for p in name.replace("min", " ").split():
            try:
                v = int(p)
                if 20 <= v <= 300:
                    return v
            except ValueError:
                pass
    return 0


def _group_by_date(events: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for ev in events:
        d = (ev.get("start_date_local") or "")[:10]
        if not d:
            continue
        out.setdefault(d, []).append(ev)
    return out


def _day_used_min(events: list[dict]) -> int:
    return sum(event_duration_min(e) for e in events
               if e.get("category") != "NOTE" and not e.get("is_note"))


def _day_has_run(events: list[dict]) -> bool:
    return any(is_run(e) for e in events if e.get("category") != "NOTE")


def _day_has_hard(events: list[dict]) -> bool:
    return any(is_hard_event(e) for e in events if e.get("category") != "NOTE")


def find_candidate_day(
    event: dict,
    occupancy: dict[str, list[dict]],
    availability: dict[str, Optional[int]],
    week_dates: list[date],
    today: date,
    source_date: str,
    injury_return: bool,
    long_run_sunday: Optional[str],
) -> Optional[str]:
    """Zoek een andere dag in de week waar dit event past.

    Returnt ISO-datumstring of None. `occupancy` wordt NIET gemuteerd;
    caller moet zelf na placement de nieuwe event op de target-dag
    injecteren om dubbele placements te voorkomen.
    """
    dur = event_duration_min(event)
    is_running = is_run(event)

    for d in week_dates:
        d_iso = d.isoformat()
        if d_iso == source_date:
            continue
        if d < today:
            continue

        avail = availability.get(d_iso)
        if avail is None or avail <= 0:
            continue  # rustdag of ongezet

        used = _day_used_min(occupancy.get(d_iso, []))
        if used + dur > avail:
            continue

        # Long run op zondag: blokkeer zaterdag voor een run-shift
        # tenzij we long run zelf verplaatsen (injury/avail).
        if long_run_sunday and d.weekday() == 5 and is_running and not is_long_run(event):
            # Zaterdag staat, alleen als de long run op zondag blijft
            # is het probleem de back-to-back. Overslaan.
            continue

        # Back-to-back run guard tijdens injury return. Bredere regel
        # dan alleen hard-hard: ook Z2+Z2 op opeenvolgende dagen is risk.
        if is_running and injury_return:
            prev_iso = (d - timedelta(days=1)).isoformat()
            next_iso = (d + timedelta(days=1)).isoformat()
            if _day_has_run(occupancy.get(prev_iso, [])):
                continue
            if _day_has_run(occupancy.get(next_iso, [])):
                continue

        # Back-to-back hard guard: als zowel d-1 als d+1 al hard hebben,
        # wordt deze dag effectief de enige rustdag. Laat 'm met rust.
        prev_iso = (d - timedelta(days=1)).isoformat()
        next_iso = (d + timedelta(days=1)).isoformat()
        if _day_has_hard(occupancy.get(prev_iso, [])) and \
           _day_has_hard(occupancy.get(next_iso, [])):
            continue

        return d_iso

    return None


def plan_redistribution(
    events: list[dict],
    availability: dict[str, Optional[int]],
    target_date: str,
    new_avail_min: int,
    week_start: date,
    today: Optional[date] = None,
    injury_return: bool = False,
) -> dict:
    """Plan de herverdeling. Geen API-calls.

    Args:
        events: Alle events van de week (intervals.icu formaat).
        availability: {date_iso: minuten} voor de hele week.
        target_date: ISO-datum die nu minder tijd heeft.
        new_avail_min: De nieuwe tijd op target_date.
        week_start: Maandag van de week.
        today: date.today() als default.
        injury_return: Strictere back-to-back guards.

    Returns:
        {
          "moves": [{"event_id", "event_name", "from", "to", "dur_min"}],
          "kept": [{"event_id", "date"}],         # blijft op target_date
          "overflow": [{"event_id", "event_name", "dur_min"}],  # geen slot
          "fits": bool,                            # True als alles geplaatst
          "reason": str,                           # korte samenvatting
        }
    """
    if today is None:
        today = date.today()

    # Target-dag in het verleden? Dan geen shift mogelijk — events daar
    # zijn al (dis)completed. Laat caller terugvallen op cap of warning.
    try:
        target_d = date.fromisoformat(target_date)
    except ValueError:
        target_d = today
    if target_d < today:
        return {
            "moves": [],
            "kept": [],
            "overflow": [],
            "fits": True,  # "niets te doen" is geen falen
            "reason": "target-datum ligt in het verleden; niet geschift",
        }

    week_dates = [week_start + timedelta(days=i) for i in range(7)]
    occupancy = _group_by_date(events)

    # Long-run-detectie: staat er een long run op zondag? Dat beïnvloedt
    # of we runs op zaterdag mogen laten landen.
    sunday_iso = (week_start + timedelta(days=6)).isoformat()
    long_run_sunday = None
    for ev in occupancy.get(sunday_iso, []):
        if is_long_run(ev) and is_run(ev):
            long_run_sunday = sunday_iso
            break

    target_events = [e for e in occupancy.get(target_date, [])
                     if e.get("category") != "NOTE" and not e.get("is_note")]

    # Sorteer: hard eerst (blijven claim op hun dag), dan easy korte-eerst
    # zodat we bij shift de langste als eerste pakken (grootste kans op
    # een passende dag; korte passen overal makkelijker).
    def _sort_key(e: dict) -> tuple:
        return (
            0 if is_hard_event(e) else 1,     # hard eerst
            -(event_duration_min(e) or 0),    # dan lang-eerst
        )
    target_events.sort(key=_sort_key)

    kept: list[dict] = []
    moves: list[dict] = []
    overflow: list[dict] = []
    used = 0

    # Simuleer occupancy na verwerking, zodat opeenvolgende shifts
    # elkaars placements zien.
    sim_occupancy: dict[str, list[dict]] = {
        k: list(v) for k, v in occupancy.items()
    }
    # Start door het target-date lijstje leeg te maken; events worden
    # één-voor-één weer toegevoegd óf verplaatst.
    sim_occupancy[target_date] = [
        e for e in sim_occupancy.get(target_date, [])
        if e not in target_events
    ]

    for ev in target_events:
        dur = event_duration_min(ev)
        ev_id = str(ev.get("id", ""))
        ev_name = ev.get("name", "")

        # Past nog op target_date binnen nieuwe avail?
        if used + dur <= new_avail_min:
            kept.append({"event_id": ev_id, "date": target_date})
            sim_occupancy.setdefault(target_date, []).append(ev)
            used += dur
            continue

        # Past niet → proberen te verplaatsen als easy, anders overflow
        if is_hard_event(ev) or not is_easy_event(ev):
            overflow.append({
                "event_id": ev_id,
                "event_name": ev_name,
                "dur_min": dur,
                "reason": "hard of onbekend-type; niet automatisch shiftbaar",
            })
            # Hard blijft op target date — zelfs als het dan over-availability gaat.
            # Caller moet dan cap-fallback of waarschuwing doen.
            sim_occupancy.setdefault(target_date, []).append(ev)
            continue

        candidate = find_candidate_day(
            ev, sim_occupancy, availability, week_dates, today,
            source_date=target_date,
            injury_return=injury_return,
            long_run_sunday=long_run_sunday,
        )

        if candidate is None:
            overflow.append({
                "event_id": ev_id,
                "event_name": ev_name,
                "dur_min": dur,
                "reason": "geen kandidaatdag met ruimte + regels",
            })
            sim_occupancy.setdefault(target_date, []).append(ev)
            continue

        # Bewaar het oorspronkelijke tijdstip (HH:MM:SS) zodat apply
        # het niet naar middernacht springt.
        sdl = ev.get("start_date_local") or ""
        from_time = sdl.split("T", 1)[1] if "T" in sdl else "00:00:00"
        moves.append({
            "event_id": ev_id,
            "event_name": ev_name,
            "from": target_date,
            "to": candidate,
            "dur_min": dur,
            "from_time": from_time,
            "sport": ev.get("type"),
        })
        sim_occupancy.setdefault(candidate, []).append(ev)

    fits = (used <= new_avail_min) and not overflow
    if fits and moves:
        reason = f"{len(moves)} sessie(s) verplaatst; rest paste op {target_date}"
    elif fits:
        reason = "Alles paste al op de krappere dag"
    elif overflow:
        reason = f"{len(overflow)} sessie(s) konden niet worden verplaatst"
    else:
        reason = "Target-dag nog steeds overbelast"

    return {
        "moves": moves,
        "kept": kept,
        "overflow": overflow,
        "fits": fits,
        "reason": reason,
    }


def apply_redistribution(plan: dict) -> dict:
    """Voer de plan_redistribution-output uit tegen intervals.icu.

    Verplaatst events via update_event(start_date_local). Houdt het
    bestaande tijdstip (HH:MM:SS uit move['from_time']) intact zodat een
    ochtendtraining niet ineens middernacht wordt.

    Bij API-fout op één van de moves: best-effort rollback van al
    gelukte moves terug naar hun originele datum. Voorkomt inconsistente
    half-toegepaste staat. Rollback-fouten verschijnen apart in errors.

    Returnt {"applied": int, "errors": [str], "rolled_back": int}.
    """
    import intervals_client as api  # lazy import; houdt shift_day importeerbaar zonder API

    errors: list[str] = []
    successful: list[dict] = []  # voor rollback bij latere fout

    for move in plan.get("moves", []):
        try:
            time_part = move.get("from_time") or "00:00:00"
            new_start = f"{move['to']}T{time_part}"
            api.update_event(move["event_id"], start_date_local=new_start)
            successful.append(move)
        except Exception as exc:
            errors.append(
                f"Move {move.get('event_name', move['event_id'])} → {move['to']} faalde: {exc}"
            )
            # Rollback: zet al gelukte moves terug op hun from-datum
            rolled = 0
            for prev in successful:
                try:
                    back_time = prev.get("from_time") or "00:00:00"
                    api.update_event(
                        prev["event_id"],
                        start_date_local=f"{prev['from']}T{back_time}",
                    )
                    rolled += 1
                except Exception as rb_exc:
                    errors.append(
                        f"ROLLBACK faalde voor {prev.get('event_name', prev['event_id'])}: {rb_exc}"
                    )
            return {"applied": 0, "errors": errors, "rolled_back": rolled}

    return {"applied": len(successful), "errors": errors, "rolled_back": 0}
