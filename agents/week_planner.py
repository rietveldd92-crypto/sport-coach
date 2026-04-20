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


class _DayPlannerDidPlacement(Exception):
    """Intern sentinel — signaleert dat de nieuwe day_planner placement deed,
    zodat de oude avail-remap kan worden overgeslagen zonder indentatie-hack.
    """

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


def add_brick_for_tss_gap(
    sessions: list,
    target_tss: int,
    actual_tss: int,
    ftp: int = 290,
    is_deload: bool = False,
    max_bricks: int = 2,
) -> list:
    """Vul TSS-gap op door brick-fietssessies te plakken op korte-run-dagen.

    Een brick is een run + bike op dezelfde dag (na elkaar). We plaatsen
    alleen op dagen met een korte Z1/herstel-run (di/do voorkeur), nooit op:
    - long-run dag
    - dag met bestaande fietssessie
    - kracht-dag (kracht-placement heeft voorrang)
    - deload-weken

    Args:
        sessions: gecombineerde run+bike sessie-lijst.
        target_tss: weekelijks TSS-doel.
        actual_tss: momenteel geplande TSS.
        ftp: FTP voor tss-berekening van de brick.
        is_deload: in deload-weken voegen we geen extra TSS toe.
        max_bricks: harde cap op aantal bricks per week.

    Returns:
        Nieuwe sessie-lijst met toegevoegde brick-bikes. Gap wordt gesloten
        tot ≤ 80 TSS of tot max_bricks bereikt is.
    """
    if is_deload:
        return sessions

    gap = target_tss - actual_tss
    if gap <= 120:
        return sessions

    # Importeer hier om circulaire imports te voorkomen.
    from agents.bike_coach import fatmax_medium_session

    # Zoek brick-kandidaat-dagen: korte runs (Z1/recovery/easy, duur ≤ 60 min),
    # geen bestaande bike, niet op zondag (long-run-dag conventie).
    sessions_by_day: dict[str, list] = {}
    for s in sessions:
        sessions_by_day.setdefault(s["dag"], []).append(s)

    # Dagen waar kracht op zou staan — vermijd die voor bricks
    long_run_dag = next(
        (s["dag"] for s in sessions if s.get("type") == "lange_duur"),
        "zondag",
    )
    kracht_dagen = set(_select_strength_days(sessions, long_run_dag))

    # Voorkeursvolgorde: di, do, wo, ma, vr, za (niet zondag)
    voorkeur = ["dinsdag", "donderdag", "woensdag", "maandag", "vrijdag", "zaterdag"]

    def _is_korte_run(s: dict) -> bool:
        naam = (s.get("naam") or "").lower()
        t = (s.get("type") or "").lower()
        duur = s.get("duur_min") or 0
        if s.get("sport") != "Run":
            return False
        if duur > 70:
            return False
        korte_types = ("recovery", "easy", "z2_standard", "z2_pickups", "strides",
                       "easy_aerobic", "run_z2_")
        return any(k in t for k in korte_types) or "herstel" in naam

    nieuwe_sessies = list(sessions)
    bricks_toegevoegd = 0

    for dag in voorkeur:
        if bricks_toegevoegd >= max_bricks:
            break
        if gap - (bricks_toegevoegd * 55) <= 80:
            break
        if dag in kracht_dagen:
            continue
        dag_sessies = sessions_by_day.get(dag, [])
        # Skip als er al een fiets staat
        if any((s.get("sport") or "") in ("Ride", "VirtualRide") for s in dag_sessies):
            continue
        # Skip als er geen korte run staat
        if not any(_is_korte_run(s) for s in dag_sessies):
            continue

        # Maak een brick-bike: 45 min fatmax_medium, afgeslankt tot ±50-60 TSS.
        brick = fatmax_medium_session(ftp)
        brick["dag"] = dag
        brick["naam"] = "Brick – 45 min high Z2 (na run)"
        brick["duur_min"] = 45
        # TSS schaal: fatmax_medium is 80 min / ~75 TSS → 45 min ≈ 42 TSS.
        # We bumpen tot 55 voor betere gap-closure (high Z2, IF ~0.75).
        brick["tss_geschat"] = 55
        brick["beschrijving"] = (
            "BRICK (na je korte run vanochtend/eerder vandaag).\n\n"
            "Warmup\n- 5m ramp 50-65% 90rpm\n\n"
            "Main Set\n- 35m 74% 88rpm (steady high Z2)\n\n"
            "Cooldown\n- 5m ramp 60-50%\n\n"
            "Doel: extra aerobe prikkel zonder intervaltraining. "
            "Voeg minstens 2 uur rust toe tussen run en fiets. "
            "Als benen zwaar zijn — skip de brick, geen schade."
        )
        brick["is_brick"] = True

        nieuwe_sessies.append(brick)
        sessions_by_day.setdefault(dag, []).append(brick)
        bricks_toegevoegd += 1

    return nieuwe_sessies


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

    # Onze eigen events: WORKOUT + NOTE events aangemaakt door dit systeem.
    # Match op prefix zodat varianten als "Krachttraining benen" ook geraakt
    # worden — eerder match-op-exact miste die en liet ze dubbel staan.
    OUR_NOTE_PREFIXES = ("Dagelijkse rehab", "Krachttraining")
    events_to_delete = [
        e for e in existing_events
        if e.get("category") == "WORKOUT"
        or (e.get("category") == "NOTE"
            and any((e.get("name") or "").startswith(p) for p in OUR_NOTE_PREFIXES))
    ]
    print(f"  Bestaande events deze week: {len(existing_events)} totaal, "
          f"{len(events_to_delete)} te verwijderen.")

    all_sessions = run_sessions + bike_sessions

    # ── AVAIL-FIRST PLACEMENT (day_planner) ──────────────────────────────────
    # Harde regels: longs eerst op hoogst-avail dagen, hards met spacing,
    # runs nooit back-to-back. Coaches leveren dag-suggesties — die overschrijven we.
    day_planner_ok = False
    try:
        from agents import availability as _av_mod
        from agents.day_planner import SchedulingConflict, plan_days

        _avail = _av_mod.get_week(week_start)
        _avail_by_dag = {
            DAYS_NL[i]: (_avail.get((week_start + timedelta(days=i)).isoformat()) or 0)
            for i in range(7)
        }
        # Alleen herplaatsen als er voldoende avail-data is (anders originele plan)
        if sum(_avail_by_dag.values()) > 0:
            try:
                replaced = plan_days(all_sessions, _avail_by_dag, week_start)
                all_sessions = replaced
                day_planner_ok = True
                print(f"  Day-planner: {len(replaced)} sessies op avail geplaatst.")
            except SchedulingConflict as _sc:
                print(f"  ⚠️  Day-planner conflict — {_sc.reason}")
                print(f"      Niet geplaatst: "
                      f"{[u.get('naam') for u in _sc.unplaced]}")
                print("      Val terug op coach-placement + avail-remap.")
    except Exception as _dp_exc:
        print(f"  Day-planner overgeslagen: {_dp_exc}")

    if not day_planner_ok:
        all_sessions = _validate_no_back_to_back_hard(all_sessions)

    # Groepeer sessies per dag
    sessions_by_day: dict[str, list] = {}
    for s in all_sessions:
        dag = s["dag"]
        sessions_by_day.setdefault(dag, []).append(s)

    # ── BESCHIKBAARHEID — duur cappen per dag ────────────────────────────────
    # Als de atleet minder tijd heeft dan de geplande sessies, schaal
    # proportioneel terug. 0-minuten dagen zijn al als skip_run_days uit
    # de plan_sessions-chain gefilterd; hier handelen we de 30-240 range af.
    # Skip als day_planner al succesvol placement deed — dan is alles avail-aware.
    try:
        if day_planner_ok:
            raise _DayPlannerDidPlacement  # early-skip sentinel
        from agents import availability as _av
        _week_avail = _av.get_week(week_start)
        _day_to_date = {dag: _day_label(week_start, dag) for dag in DAYS_NL}

        def _day_space(dag_naam: str) -> int:
            """Resterende vrije minuten op een dag (0 als rustdag/onbekend)."""
            avail = _week_avail.get(_day_to_date[dag_naam].isoformat())
            if avail is None or avail == 0:
                return 0
            used = sum((s.get("duur_min") or 0) for s in sessions_by_day.get(dag_naam, []))
            return max(0, avail - used)

        def _day_has_hard(dag_naam: str) -> bool:
            return any(_is_hard_session(s) for s in sessions_by_day.get(dag_naam, []))

        def _placement_safe(sessie: dict, to_dag: str) -> bool:
            """Zou plaatsen van `sessie` op `to_dag` back-to-back-hard creëren?

            Runs worden sowieso niet door de availability-remap verplaatst,
            maar we willen ook niet dat een hard bike landt naast een hard
            run/bike — blessurerisico + insufficient herstel.
            """
            if not _is_hard_session(sessie):
                # Zachte sessie: alleen checken of de zelfde dag al zwaar + hard hier = conflict.
                return True
            idx = DAYS_NL.index(to_dag)
            neighbors = []
            if idx > 0:
                neighbors.append(DAYS_NL[idx - 1])
            if idx < len(DAYS_NL) - 1:
                neighbors.append(DAYS_NL[idx + 1])
            for n in neighbors:
                if _day_has_hard(n):
                    return False
            # En zelfde dag mag niet al hard zijn
            if _day_has_hard(to_dag):
                return False
            return True

        def _move(s: dict, from_dag: str, to_dag: str) -> None:
            s["dag"] = to_dag
            s["datum"] = _day_label(week_start, to_dag).isoformat()
            sessions_by_day.setdefault(to_dag, []).append(s)

        # Stap 1: rustdagen (0 min) — bike-sessies remappen, rest droppen.
        for dag in list(sessions_by_day.keys()):
            avail = _week_avail.get(_day_to_date[dag].isoformat())
            if avail != 0:
                continue
            keep: list[dict] = []
            for s in sessions_by_day[dag]:
                if (s.get("sport") or "") in ("Ride", "VirtualRide"):
                    dur = s.get("duur_min") or 0
                    target = next(
                        (d for d in DAYS_NL
                         if d != dag and _day_space(d) >= dur and _placement_safe(s, d)),
                        None,
                    )
                    if target:
                        _move(s, dag, target)
                        print(f"  Fiets '{s.get('naam')}' verplaatst van {dag} → {target}")
                    else:
                        print(f"  Fiets '{s.get('naam')}' geskipt ({dag} rustdag, geen ruimte elders)")
                else:
                    print(f"  Sessie '{s.get('naam')}' geskipt ({dag} rustdag)")
            sessions_by_day[dag] = keep

        # Stap 2: krappe dagen — als totale sessie-duur > beschikbaarheid,
        # probeer eerst grootste bike-sessie te verplaatsen naar een dag met
        # ruimte (eventueel met swap als doeldag óók krap is maar kortere
        # sessie heeft). Pas daarna proportionele cap als laatste redmiddel.
        for dag in list(sessions_by_day.keys()):
            avail = _week_avail.get(_day_to_date[dag].isoformat())
            if avail is None or avail <= 0:
                continue
            sess_list = sessions_by_day.get(dag, [])
            total_min = sum(s.get("duur_min") or 0 for s in sess_list)
            if total_min <= avail:
                continue

            # Probeer bike-sessies (van groot naar klein) te verplaatsen/swappen.
            bike_sessions = sorted(
                [s for s in sess_list if (s.get("sport") or "") in ("Ride", "VirtualRide")],
                key=lambda s: -(s.get("duur_min") or 0),
            )
            for s in bike_sessions:
                dur = s.get("duur_min") or 0
                if sum(x.get("duur_min") or 0 for x in sessions_by_day.get(dag, [])) <= avail:
                    break  # dag past nu
                # 2a: directe verhuizing naar dag met genoeg vrije ruimte
                target = next(
                    (d for d in DAYS_NL
                     if d != dag and _day_space(d) >= dur and _placement_safe(s, d)),
                    None,
                )
                if target:
                    sessions_by_day[dag].remove(s)
                    _move(s, dag, target)
                    print(f"  Fiets '{s.get('naam')}' van krappe dag {dag} → {target}")
                    continue
                # 2b: swap met kortere sessie op een dag met MEER ruimte.
                # Conditie: sessie s krijgt na swap strikt meer minuten op de
                # doeldag dan nu op de krappe dag, en de kortere sessie past
                # na swap op de krappe dag. Beide plaatsingen moeten aan de
                # back-to-back-hard regel voldoen.
                s_space_on_dag = (
                    avail
                    - sum(x.get("duur_min") or 0 for x in sessions_by_day[dag])
                    + dur
                )
                best_d = None
                best_other = None
                best_gain = 0
                for d in DAYS_NL:
                    if d == dag:
                        continue
                    d_avail = _week_avail.get(_day_to_date[d].isoformat())
                    if d_avail is None or d_avail == 0:
                        continue
                    d_sessions = sessions_by_day.get(d, [])
                    for other in d_sessions:
                        other_dur = other.get("duur_min") or 0
                        if other_dur >= dur:
                            continue
                        # Space s zou krijgen op d na wegwerken van other
                        s_space_on_d = min(
                            dur,
                            d_avail
                            - sum(x.get("duur_min") or 0 for x in d_sessions)
                            + other_dur,
                        )
                        # Space s heeft nu (capped) op krappe dag
                        current_space = min(dur, s_space_on_dag)
                        gain = s_space_on_d - current_space
                        if gain <= 0:
                            continue
                        if s_space_on_dag < other_dur:
                            continue  # other past niet op krappe dag na swap
                        if not (_placement_safe(s, d) and _placement_safe(other, dag)):
                            continue
                        if gain > best_gain:
                            best_gain = gain
                            best_d = d
                            best_other = other
                if best_d is not None:
                    sessions_by_day[dag].remove(s)
                    sessions_by_day[best_d].remove(best_other)
                    _move(s, dag, best_d)
                    _move(best_other, best_d, dag)
                    print(f"  Swap: '{s.get('naam')}' {dag}→{best_d}, "
                          f"'{best_other.get('naam')}' {best_d}→{dag}")

            # Stap 3: alsnog cap als er niks passender te verhuizen was.
            final_sess = sessions_by_day.get(dag, [])
            final_total = sum(s.get("duur_min") or 0 for s in final_sess)
            if final_total > avail:
                sessions_by_day[dag] = _av.cap_sessions_for_day(final_sess, avail)
                print(f"  Dag {dag}: ingekort van {final_total} → {avail} min (geen swap mogelijk)")
    except _DayPlannerDidPlacement:
        pass  # day_planner deed de placement al, geen remap nodig
    except Exception as _e:
        print(f"  Beschikbaarheid-cap overgeslagen: {_e}")

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

    # 3. Workoutsessies (run + fiets) — beschrijving verrijkt met pace/watts
    from agents.workout_annotations import annotate_description
    for dag_naam in DAYS_NL:
        if dag_naam in sessions_by_day:
            for sessie in sessions_by_day[dag_naam]:
                dag_date = _day_label(week_start, dag_naam)
                events_to_create.append({
                    "datum": dag_date,
                    "naam": sessie["naam"],
                    "beschrijving": annotate_description(
                        sessie["beschrijving"], sessie["sport"]
                    ),
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
