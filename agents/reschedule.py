"""
Reschedule — herschik gemiste kwaliteitstrainingen naar later in de week.

Kwaliteitssessies (threshold, sweetspot, over-unders, tempo) zijn de belangrijkste
trainingen van de week. Als ze gemist worden, laten we ze niet vallen maar kijken
we of ze later in de week nog passen.

Regels:
- Geen twee harde sessies achter elkaar
- Niet op de dag voor de lange duurloop (zondag)
- Niet als het TSS-budget al overschreden is
- Niet op een rustdag (maandag)
"""

from datetime import date, timedelta
import intervals_client as api

# Workout types die we willen beschermen (kwaliteitssessies)
QUALITY_TYPES = {"threshold", "sweetspot", "over-under", "over_under", "tempo", "interval"}


def is_quality_workout(event: dict) -> bool:
    """Check of een event een kwaliteitstraining is."""
    name = (event.get("name") or "").lower()
    return any(q in name for q in QUALITY_TYPES)


def find_reschedule_slot(missed_event: dict, week_events: list, week_activities: list) -> dict | None:
    """Zoek een geschikt moment later in de week voor een gemiste kwaliteitstraining.

    Args:
        missed_event: Het gemiste event
        week_events: Alle events van de week
        week_activities: Alle activiteiten van de week (al uitgevoerd)

    Returns:
        dict met {"target_date": date, "swap_event_id": str, "swap_event_name": str}
        of None als er geen plek is.
    """
    missed_date = date.fromisoformat(missed_event.get("start_date_local", "")[:10])
    today = date.today()

    # Bouw een dagschema: wat staat er per dag?
    day_schedule = {}
    for event in week_events:
        e_date = event.get("start_date_local", "")[:10]
        if e_date not in day_schedule:
            day_schedule[e_date] = []
        day_schedule[e_date].append(event)

    # Welke dagen zijn al voltooid?
    done_dates = set()
    for act in week_activities:
        a_date = act.get("start_date_local", "")[:10]
        done_dates.add(a_date)

    # Welke dagen hebben al een harde sessie?
    hard_dates = set()
    for event in week_events:
        if is_quality_workout(event):
            e_date = event.get("start_date_local", "")[:10]
            hard_dates.add(e_date)

    # Zoek een geschikte dag
    monday = missed_date - timedelta(days=missed_date.weekday())
    sunday = monday + timedelta(days=6)

    for day_offset in range(1, 7):
        candidate = missed_date + timedelta(days=day_offset)

        # Niet voorbij zondag
        if candidate > sunday:
            break

        # Niet in het verleden
        if candidate < today:
            continue

        candidate_str = candidate.isoformat()
        weekday = candidate.weekday()

        # Niet op maandag (rustdag)
        if weekday == 0:
            continue

        # Niet op zaterdag (dag voor lange duurloop)
        if weekday == 5:
            continue

        # Niet als er al een harde sessie op die dag staat
        if candidate_str in hard_dates:
            continue

        # Niet als de dag ervoor of erna al hard is (geen 2 hard achter elkaar)
        day_before = (candidate - timedelta(days=1)).isoformat()
        day_after = (candidate + timedelta(days=1)).isoformat()
        if day_before in hard_dates or day_after in hard_dates:
            continue

        # Vind een Z2/easy event op die dag om mee te swappen
        day_events = day_schedule.get(candidate_str, [])
        swap_target = None
        for event in day_events:
            if event.get("category") != "WORKOUT":
                continue
            name = (event.get("name") or "").lower()
            # Swap met een easy/Z2 run of endurance ride
            if any(k in name for k in ["z2", "easy", "duurloop", "herstel", "endurance", "spin"]):
                swap_target = event
                break

        if swap_target:
            return {
                "target_date": candidate,
                "swap_event_id": swap_target.get("id"),
                "swap_event_name": swap_target.get("name"),
                "reason": f"Z2 op {candidate_str} wordt de gemiste kwaliteitstraining. "
                          f"De Z2 run verschuift of vervalt."
            }

        # Geen easy event om te swappen, maar dag is leeg → voeg toe
        if not day_events:
            return {
                "target_date": candidate,
                "swap_event_id": None,
                "swap_event_name": None,
                "reason": f"{candidate_str} is vrij — kwaliteitstraining hier inplannen."
            }

    return None


def suggest_reschedule(missed_event: dict) -> dict | None:
    """Controleer of een gemist event herschikt kan worden en doe een voorstel.

    Returns dict met voorstel of None.
    """
    if not is_quality_workout(missed_event):
        return None

    missed_date_str = missed_event.get("start_date_local", "")[:10]
    missed_date = date.fromisoformat(missed_date_str)
    monday = missed_date - timedelta(days=missed_date.weekday())
    sunday = monday + timedelta(days=6)

    try:
        events = api.get_events(monday, sunday)
        activities = api.get_activities(start=monday, end=sunday)
    except Exception:
        return None

    slot = find_reschedule_slot(missed_event, events, activities)
    if not slot:
        return None

    return {
        "missed_workout": missed_event.get("name"),
        "missed_date": missed_date_str,
        "target_date": slot["target_date"].isoformat(),
        "swap_event_id": slot.get("swap_event_id"),
        "swap_event_name": slot.get("swap_event_name"),
        "reason": slot["reason"],
        "message": (
            f"Je hebt '{missed_event.get('name')}' gemist op {missed_date_str}. "
            f"Voorstel: verschuif naar {slot['target_date'].isoformat()}. "
            f"{slot['reason']}"
        ),
    }
