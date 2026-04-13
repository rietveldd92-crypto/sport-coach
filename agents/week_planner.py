"""
Week Planner — combineert alle agent-outputs en schrijft events naar intervals.icu.

Regels:
1. Nooit twee harde sessies achter elkaar
2. Krachttraining: om de dag (ma/wo/vr OF di/do/za), NIET op dag van lange duur
3. Rehab: elke dag als NOTE in de kalender
4. Rustdagen na ROOD van Injury Guard
5. Zondag = lange loop (tenzij race week of ROOD)
6. Fiets sweetspot bij voorkeur na een herstelloopdag
7. Krachttaining + revalidatie dagelijkse note als apart NOTE event
"""

import sys
from datetime import date, timedelta
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Voeg project root toe aan path
sys.path.insert(0, str(Path(__file__).parent.parent))
import intervals_client as api

DAYS_NL = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"]

STRENGTH_NOTE = (
    "KRACHTTRAINING (30-40 min) — 2-3 sets, stop ruim voor falen\n\n"
    "Adductoren & heup:\n"
    "• Copenhagen plank 2-3×20-30s per kant (adductoren)\n"
    "• Side plank 2-3×30s per kant (glute medius + core)\n"
    "• Clamshells 3×15 per kant\n"
    "• Single-leg deadlift 3×8 per been (langzaam, gecontroleerd)\n"
    "• Lateral band walk 3×15 per kant\n\n"
    "Regels:\n"
    "• Stop elke set ruim voor falen — dit is geen spiergroei training\n"
    "• Geen kniepijn tijdens of direct na de oefening\n"
    "• 24-uurs pijnregel: als de kniepijn volgende ochtend erger is, skip de volgende krachttraining\n"
    "  en meld via: python adjust.py"
)

REHAB_DAILY_NOTE = (
    "DAGELIJKSE REHAB (15-20 min — voor elke run)\n\n"
    "Heupactivatie:\n"
    "• Clamshells 3×15 per kant\n"
    "• Side-lying hip abduction 3×12 per kant\n"
    "• Glute bridge 3×15 (ook single-leg 2×10)\n\n"
    "Mobiliteit:\n"
    "• 90/90 hip stretch 2×60s per kant\n"
    "• Hip flexor stretch 2×45s per kant\n"
    "• Pigeon pose 2×60s per kant\n\n"
    "Activatie:\n"
    "• High knees 2×20\n"
    "• Leg swings 2×15 per been\n\n"
    "24-uurs pijnregel:\n"
    "Als de kniepijn volgende ochtend erger is dan gisteren, reduceer de load.\n"
    "Meld het via: python adjust.py"
)

# Dagen waarop krachttraining ingepland kan worden — fallback als de
# slimme placement (zie _select_strength_days) faalt.
STRENGTH_DAYS = ["dinsdag", "donderdag", "zaterdag"]

# TSS-drempel waarboven een sessie als "zwaar" telt voor kracht-placering.
HARD_TSS_FOR_STRENGTH = 70


def _day_label(week_start: date, dag_naam: str) -> date:
    offset = DAYS_NL.index(dag_naam)
    return week_start + timedelta(days=offset)


def _is_hard_session(sessie: dict) -> bool:
    """Bepaalt of een sessie 'hard' is (sweetspot, VO2max, intervals, tempo)."""
    hard_types = {"sweetspot_kort", "sweetspot_lang", "vo2max_intervals",
                  "interval_10km", "tempoloon", "z2_met_strides"}
    return sessie.get("type") in hard_types


def _select_strength_days(all_sessions: list, long_run_dag: str) -> list[str]:
    """Kies kracht-dagen volgens twee regels:

    1. NOOIT op de dag VOOR een zware sessie (kracht voor zwaar = slechte staat).
    2. NOOIT 2 dagen achter elkaar (48u herstel tussen kracht-sessies).

    Algoritme:
    - Verzamel hard_days (TSS >= 70 of sacred/threshold/drempel/intervals).
    - Forbidden = dag-voor-elke-hard-dag + long_run_dag.
    - Kies uit overige dagen: max 3 sessies, minimum 2 dagen gap.
    """
    sessions_by_day: dict[str, list] = {}
    for s in all_sessions:
        sessions_by_day.setdefault(s["dag"], []).append(s)

    # "Hard" voor kracht-placement = ALLEEN interval-/drempelsessies.
    # Lange continue duurritten (long_slow, long_endurance, fatmax, lange duurloop)
    # zijn aerobe motor — geen explosief/excentrisch werk dat kracht conflicteert.
    hard_keywords = ("threshold", "drempel", "marathon_tempo", "tempo_duurloop",
                     "cp_intervals", "vo2max", "interval", "over_unders",
                     "over-unders", "pyramide", "surges", "vo2", "sweetspot")

    def _day_is_hard(dag: str) -> bool:
        # Alleen interval-/drempelsessies tellen als "hard" voor kracht-placement.
        # TSS alleen is geen criterium: een 165 min long_slow heeft TSS 120 maar
        # is puur aeroob — kracht ervoor is prima.
        for s in sessions_by_day.get(dag, []):
            sessie_type = (s.get("type") or "").lower()
            naam = (s.get("naam") or "").lower()
            if any(k in sessie_type or k in naam for k in hard_keywords):
                return True
        return False

    forbidden: set[str] = set()
    if long_run_dag:
        forbidden.add(long_run_dag)
    for i, dag in enumerate(DAYS_NL):
        if _day_is_hard(dag):
            # Hard day zelf: ambigu of kracht voor of na de sessie zit.
            # Conservatief: blokker de dag zelf óók.
            forbidden.add(dag)
            if i > 0:
                forbidden.add(DAYS_NL[i - 1])  # dag VOOR een zware sessie

    # Kandidaten: dagen die niet forbidden zijn, met spreiding ≥ 2 dagen
    candidates: list[str] = []
    last_picked_idx = -10
    for i, dag in enumerate(DAYS_NL):
        if dag in forbidden:
            continue
        if i - last_picked_idx >= 2:
            candidates.append(dag)
            last_picked_idx = i
        if len(candidates) >= 3:
            break
    return candidates


def _validate_no_back_to_back_hard(all_sessions: list) -> list:
    """
    Controleer of er geen twee harde sessies op opeenvolgende dagen zijn.
    Verschuif de tweede indien nodig naar een rustdag.
    """
    dag_to_sessie = {s["dag"]: s for s in all_sessions}
    for i, dag in enumerate(DAYS_NL[:-1]):
        next_dag = DAYS_NL[i + 1]
        if dag in dag_to_sessie and next_dag in dag_to_sessie:
            if _is_hard_session(dag_to_sessie[dag]) and _is_hard_session(dag_to_sessie[next_dag]):
                # Verzacht de tweede sessie (vervang door herstelrun/easy spin)
                s = dag_to_sessie[next_dag]
                if s["sport"] == "Run":
                    s["naam"] = f"[Aangepast naar herstel] {s['naam']}"
                    s["beschrijving"] = (
                        "⚠️ Twee harde dagen achter elkaar — automatisch aangepast naar hersteldag.\n"
                        + s["beschrijving"]
                    )
                    s["tss_geschat"] = max(30, s["tss_geschat"] // 2)
    return all_sessions


def build_week(
    week_start: date,
    run_sessions: list,
    bike_sessions: list,
    injury_guard: dict,
    load_manager: dict,
    dry_run: bool = True,
) -> list[dict]:
    """
    Bouw het volledige weekschema en schrijf naar intervals.icu.

    Args:
        week_start: Maandag van de te plannen week
        run_sessions: Output van endurance_coach.plan_sessions()
        bike_sessions: Output van bike_coach.plan_sessions()
        injury_guard: Output van Injury Guard
        load_manager: Output van Load Manager
        dry_run: Als True, print alleen — schrijft NIET naar intervals.icu

    Returns:
        Lijst van alle geplande events
    """
    week_end = week_start + timedelta(days=6)
    phase = load_manager.get("current_phase", "basis_I")
    status = injury_guard.get("status", "groen")
    strength_ok = injury_guard.get("strength_allowed", True)

    # ── BESTAANDE EVENTS OPHALEN ─────────────────────────────────────────────
    # Dit doen we altijd, ook in dry_run, zodat je ziet wat er al staat.
    existing_events = []
    try:
        existing_events = api.get_events(week_start, week_end)
    except Exception as e:
        print(f"  Waarschuwing: kan bestaande events niet ophalen: {e}")

    # Onze eigen events: WORKOUT + NOTE events aangemaakt door dit systeem
    OUR_NOTE_NAMES = {"Dagelijkse rehab", "Krachttraining"}
    events_to_delete = [
        e for e in existing_events
        if e.get("category") == "WORKOUT"
        or (e.get("category") == "NOTE" and e.get("name") in OUR_NOTE_NAMES)
    ]

    all_sessions = run_sessions + bike_sessions
    all_sessions = _validate_no_back_to_back_hard(all_sessions)

    # Groepeer sessies per dag
    sessions_by_day: dict[str, list] = {}
    for s in all_sessions:
        dag = s["dag"]
        sessions_by_day.setdefault(dag, []).append(s)

    # Bepaal op welke dagen krachttraining past:
    # 1. NOOIT op de dag VOOR een zware sessie
    # 2. NOOIT 2 dagen achter elkaar
    # 3. NOOIT op long-run dag
    long_run_dag = next((s["dag"] for s in run_sessions if s.get("type") == "lange_duur"), "zondag")
    strength_days_this_week = _select_strength_days(all_sessions, long_run_dag)
    if not strength_days_this_week:
        # Fallback: oude vaste lijst minus long_run_dag — beter dan niks
        strength_days_this_week = [d for d in STRENGTH_DAYS if d != long_run_dag]

    # Bouw het schema
    events_to_create = []

    # 1. Dagelijkse rehab NOTE (maandag t/m zondag)
    for dag_naam in DAYS_NL:
        dag_date = _day_label(week_start, dag_naam)
        events_to_create.append({
            "datum": dag_date,
            "naam": "Dagelijkse rehab",
            "beschrijving": REHAB_DAILY_NOTE,
            "categorie": "NOTE",
            "sport": "Run",
            "tss": None,
        })

    # 2. Krachttraining (om de dag, als toegestaan)
    if strength_ok and phase not in ("race_week",):
        for dag_naam in strength_days_this_week:
            dag_date = _day_label(week_start, dag_naam)
            events_to_create.append({
                "datum": dag_date,
                "naam": "Krachttraining",
                "beschrijving": STRENGTH_NOTE,
                "categorie": "NOTE",
                "sport": "WeightTraining",
                "tss": None,
            })

    # 3. Workoutsessies (run + fiets)
    for dag_naam in DAYS_NL:
        if dag_naam in sessions_by_day:
            for sessie in sessions_by_day[dag_naam]:
                dag_date = _day_label(week_start, dag_naam)
                events_to_create.append({
                    "datum": dag_date,
                    "naam": sessie["naam"],
                    "beschrijving": sessie["beschrijving"],
                    "categorie": "WORKOUT",
                    "sport": sessie["sport"],
                    "tss": sessie.get("tss_geschat"),
                })

    # ── PRINT OVERZICHT ─────────────────────────────────────────────────────
    workout_tss = sum(e["tss"] or 0 for e in events_to_create if e["categorie"] == "WORKOUT")
    run_tss = sum(e["tss"] or 0 for e in events_to_create if e["categorie"] == "WORKOUT" and e["sport"] == "Run")
    bike_tss = sum(e["tss"] or 0 for e in events_to_create if e["categorie"] == "WORKOUT" and e["sport"] == "VirtualRide")

    print("\n" + "═" * 60)
    print(f"  WEEKPLAN {week_start} t/m {week_end}")
    print(f"  Fase: {phase.replace('_', ' ').title()} | Injury Guard: {status.upper()}")
    print("═" * 60)
    print(f"  CTL: {load_manager.get('ctl')} | ATL: {load_manager.get('atl')} | TSB: {load_manager.get('tsb'):+.0f}")
    print(f"  Weekdoel TSS: {load_manager.get('recommended_weekly_tss')} | Gepland: {workout_tss}")
    print(f"  Loop-TSS: {run_tss} | Fiets-TSS: {bike_tss}")
    print("─" * 60)

    for dag_naam in DAYS_NL:
        dag_date = _day_label(week_start, dag_naam)
        dag_events = [e for e in events_to_create if e["datum"] == dag_date and e["categorie"] == "WORKOUT"]
        dag_notes = [e for e in events_to_create if e["datum"] == dag_date and e["categorie"] == "NOTE"]
        if dag_events or dag_notes:
            print(f"\n  {dag_naam.upper()} {dag_date.strftime('%d %b')}")
            for e in dag_events:
                tss_str = f"TSS {e['tss']}" if e["tss"] else ""
                print(f"    🏃 {e['naam']}  {tss_str}")
            for e in dag_notes:
                print(f"    📌 {e['naam']}")

    # ── BESTAANDE EVENTS TONEN ───────────────────────────────────────────────
    print("\n" + "─" * 60)
    if events_to_delete:
        print(f"  Te verwijderen ({len(events_to_delete)} bestaande events):")
        for e in events_to_delete:
            e_date = e.get("start_date_local", "")[:10]
            e_name = e.get("name", "?")
            e_cat = e.get("category", "?")
            print(f"    - [{e_cat}] {e_name}  ({e_date})")
    else:
        print("  Geen bestaande events om te verwijderen.")

    print("\n" + "─" * 60)

    if dry_run:
        print("  [DRY RUN] Geen events geschreven naar intervals.icu.")
        print("  Voer uit met --schrijf om daadwerkelijk in te plannen.")
        print("═" * 60 + "\n")
        return events_to_create

    # ── SCHRIJF NAAR INTERVALS.ICU ──────────────────────────────────────────
    print("  Bezig met schrijven naar intervals.icu...")

    # Verwijder bestaande events (WORKOUT + onze NOTE events)
    deleted = 0
    for e in events_to_delete:
        try:
            api.delete_event(e["id"])
            deleted += 1
        except Exception as ex:
            print(f"  Fout bij verwijderen '{e.get('name')}': {ex}")
    if deleted:
        print(f"  {deleted} bestaande event(s) verwijderd.")

    created_events = []
    errors = []
    for event in events_to_create:
        try:
            result = api.create_event(
                event_date=event["datum"],
                name=event["naam"],
                description=event["beschrijving"],
                category=event["categorie"],
                sport_type=event["sport"],
                load_target=event["tss"],
            )
            created_events.append(result)
        except Exception as e:
            errors.append(f"{event['naam']} op {event['datum']}: {e}")

    print(f"  ✅ {len(created_events)} events aangemaakt in intervals.icu.")
    if errors:
        print(f"  ⚠️  {len(errors)} fout(en):")
        for err in errors:
            print(f"     {err}")

    print("═" * 60 + "\n")
    return created_events
