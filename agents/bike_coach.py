"""
Bike Coach — ontwerpt de fietssessies voor de week.

De fiets is jouw primaire intensiteitstool tijdens de revalidatiefase.
Op de fiets is er geen kniebelasting via impact, en sweetspot-training
is bijzonder effectief voor het opbouwen van aerobe capaciteit.

Zone definities (vermogen, % FTP):
  Z1:        <55% FTP  — herstel
  Z2:        55-75%    — aeroob
  Sweetspot: 88-93%    — hoge trainingsefficiëntie, sub-drempel
  Z4 (VO2):  94-105%   — drempel / VO2max
  Z5:        >105%     — VO2max intervals

Sweetspot uitleg: Net onder drempelwaarde — hoge aerobe stimulus
met beperkte vermoeidheidskosten. Ideaal voor blessure-herstel fase.
"""

from datetime import date, timedelta


def _tss_bike(duration_min: int, intensity_factor: float) -> int:
    """TSS schatting fiets: (duur in uren × IF² × 100)."""
    return round((duration_min / 60) * (intensity_factor ** 2) * 100)


# ── SESSIE TEMPLATES ─────────────────────────────────────────────────────────

def _spin_blocks(main: int) -> str:
    """Splits main duration into ≤12 min blocks at 63%, separated by 2 min at 50%."""
    if main <= 12:
        return f"- {main}m 63% 90rpm"
    elif main <= 22:
        b1 = main // 2
        b2 = main - b1 - 2
        return f"- {b1}m 63% 90rpm\n- 2m 50%\n- {b2}m 63% 90rpm"
    else:
        recovery = 4  # 2 × 2m between 3 blocks
        work = main - recovery
        b = work // 3
        rem = work - b * 3
        return f"- {b}m 63% 90rpm\n- 2m 50%\n- {b}m 63% 90rpm\n- 2m 50%\n- {b + rem}m 63% 90rpm"


BIKE_CROSS_NOTE = (
    "\n\nDelahaije: 'Lopers hoeven niet meer km te maken, maar kunnen wel de "
    "trainingstijd vergroten door te fietsen.' De mitochondrien maken het niet "
    "uit of je ze traint door te fietsen of te lopen — aerobe winst is gelijk, "
    "impactbelasting nul."
)


def _easy_spin(duration_min: int = 45) -> dict:
    main = duration_min - 10
    return {
        "type": "easy_spin",
        "naam": f"Duurrit Z2 – {duration_min} min",
        "beschrijving": (
            f"Warmup\n"
            f"- 5m ramp 45-60% 85rpm\n\n"
            f"Main Set\n"
            f"{_spin_blocks(main)}\n\n"
            f"Cooldown\n"
            f"- 5m ramp 60-45%\n\n"
            f"Aerobe duurrit — vervangt een loopsessie zonder impactbelasting.\n"
            f"Hoge kadans (85-95rpm) = minder kniedruk. Mag lekker voelen."
            f"{BIKE_CROSS_NOTE}"
        ),
        "duur_min": duration_min,
        "tss_geschat": _tss_bike(duration_min, 0.65),
        "sport": "VirtualRide",
        "zone": "Z2",
        "intensiteit_factor": 0.65,
    }


def _sweetspot(ftp: int = 250, ss_count: int = 1) -> dict:
    """Sweetspot progressie: langere blokken en meer volume over de weken.
    2x10 → 2x12 → 2x15 → 3x12 → 3x15 → 2x20 → 3x18 → 2x25 → 3x20 → 1x45."""
    ss_low = round(ftp * 0.88)
    ss_high = round(ftp * 0.93)

    steps = [
        ("2x10 min",  "2x\n- 10m 90% 88rpm\n- 4m 60% 95rpm",  42, 0.82,
         "Kennismaking. Focus op constant vermogen, niet te hard starten."),
        ("2x12 min",  "2x\n- 12m 90% 88rpm\n- 4m 60% 95rpm",  46, 0.83,
         "Iets langer vasthouden. Voel het ritme, adem rustig."),
        ("2x15 min",  "2x\n- 15m 90% 88rpm\n- 5m 60% 95rpm",  55, 0.84,
         "30 min werk. Mag zwaar voelen, niet onhoudbaar."),
        ("3x12 min",  "3x\n- 12m 90% 88rpm\n- 4m 60% 95rpm",  56, 0.84,
         "Eerste keer 3 blokken. Verdeel je energie gelijk over alle drie."),
        ("3x15 min",  "3x\n- 15m 90% 88rpm\n- 5m 60% 95rpm",  70, 0.85,
         "45 min totaal. Blok 3 is karakter — kadans omhoog als vermogen wegzakt."),
        ("2x20 min",  "2x\n- 20m 90% 88rpm\n- 5m 60% 95rpm",  65, 0.86,
         "Langere blokken. Mentale uitdaging — verdeel de 20 min in 4x 5 min."),
        ("3x18 min",  "3x\n- 18m 90% 88rpm\n- 5m 60% 95rpm",  79, 0.87,
         "54 min werk. Je aerobe motor draait nu serieus."),
        ("2x25 min",  "2x\n- 25m 90% 88rpm\n- 5m 60% 95rpm",  75, 0.87,
         "50 min werk in twee lange blokken. Constant vermogen is de sleutel."),
        ("3x20 min",  "3x\n- 20m 90% 88rpm\n- 5m 60% 95rpm",  85, 0.88,
         "60 min werk. Dit is echte race-voorbereiding op de fiets."),
        ("1x45 min",  "- 45m 90% 88rpm",                        65, 0.88,
         "Ononderbroken sweetspot. De ultieme test van aerobe kracht."),
    ]
    idx = min(ss_count - 1, len(steps) - 1)
    naam_suffix, main, duur, if_val, note = steps[idx]

    return {
        "type": "sweetspot",
        "naam": f"Sweetspot – {naam_suffix}",
        "beschrijving": (
            f"Warmup\n"
            f"- 7m ramp 55-80% 90rpm\n"
            f"3x\n"
            f"- 30s 110%\n"
            f"- 1m 55%\n\n"
            f"Main Set\n"
            f"{main}\n\n"
            f"Cooldown\n"
            f"- 10m ramp 75-50%\n\n"
            f"Sweetspot = 88-93% FTP ({ss_low}-{ss_high}W). {note}"
        ),
        "duur_min": duur,
        "tss_geschat": _tss_bike(duur, if_val),
        "sport": "VirtualRide",
        "zone": "Sweetspot",
        "intensiteit_factor": if_val,
    }


# Backwards compatible aliases
def _sweetspot_short(ftp: int = 250) -> dict:
    return _sweetspot(ftp, ss_count=3)  # 2x15

def _sweetspot_long(ftp: int = 250) -> dict:
    return _sweetspot(ftp, ss_count=5)  # 3x15


def _threshold(ftp: int = 250, threshold_count: int = 1) -> dict:
    """Threshold opbouw: progressief meer tijd @ FTP.
    3×8 → 3×10 → 3×12 → 2×15 → 2×20 → 3×15 → 2×25 → 3×20 → 2×30 → 1×40."""
    t_watts = round(ftp * 0.97)

    steps = [
        ("3×8 min (intro)",  "3x\n- 8m 97% 85rpm\n- 3m 55% 95rpm",  45, 0.87,
         "Eerste threshold sessie. Kort en gecontroleerd."),
        ("3×10 min",         "3x\n- 10m 97% 85rpm\n- 3m 55% 95rpm", 52, 0.89,
         "Drie blokken van 10 min. Gelijkmatig vermogen, niet te hard starten."),
        ("3×12 min",         "3x\n- 12m 97% 85rpm\n- 3m 55% 95rpm", 60, 0.91,
         "Blok 3 wordt zwaar — kadans omhoog als vermogen wegzakt."),
        ("2×15 min",         "2x\n- 15m 97% 85rpm\n- 5m 55% 95rpm", 55, 0.91,
         "Langere blokken. Focus op even doortrappen in het tweede blok."),
        ("2×20 min",         "2x\n- 20m 97% 85rpm\n- 5m 55% 95rpm", 65, 0.93,
         "Beide blokken gelijkmatig — niet te hard starten."),
        ("3×15 min",         "3x\n- 15m 97% 85rpm\n- 5m 55% 95rpm", 75, 0.93,
         "45 min totaal @ threshold. Mentale hardheid — derde blok is karakter."),
        ("2×25 min",         "2x\n- 25m 97% 85rpm\n- 5m 55% 95rpm", 75, 0.94,
         "50 min @ threshold. Splitst de inspanning in twee lange blokken."),
        ("3×20 min",         "3x\n- 20m 97% 85rpm\n- 5m 55% 95rpm", 85, 0.94,
         "60 min @ threshold. Dit is FTP-werk op race-niveau."),
        ("2×30 min",         "2x\n- 30m 97% 85rpm\n- 5m 55% 95rpm", 85, 0.95,
         "60 min @ threshold in twee blokken. Dit is serieus uithoudingsvermogen."),
        ("1×40 min",         "- 40m 97% 85rpm",                      65, 0.95,
         "Ononderbroken threshold. De ultieme test — als dit lukt, is je FTP bevestigd."),
    ]
    idx = min(threshold_count - 1, len(steps) - 1)
    naam_suffix, main, duur, if_val, note = steps[idx]

    return {
        "type": "threshold",
        "naam": f"Threshold – {naam_suffix}",
        "beschrijving": (
            f"Warmup\n"
            f"- 10m ramp 50-80% 90rpm\n"
            f"3x\n"
            f"- 30s 105%\n"
            f"- 1m 55%\n\n"
            f"Main Set\n"
            f"{main}\n\n"
            f"Cooldown\n"
            f"- 10m ramp 75-50%\n\n"
            f"Threshold = 94-105% FTP ({t_watts}W = 97%). {note}"
        ),
        "duur_min": duur,
        "tss_geschat": _tss_bike(duur, if_val),
        "sport": "VirtualRide",
        "zone": "Z4 Threshold",
        "intensiteit_factor": if_val,
    }


def _over_unders(ftp: int = 250) -> dict:
    """Over-unders: afwisselend boven en onder FTP. Leert omgaan met lactaat."""
    over = round(ftp * 1.05)
    under = round(ftp * 0.90)
    return {
        "type": "over_unders",
        "naam": "Over-unders – 4×(4m/2m)",
        "beschrijving": (
            f"Warmup\n"
            f"- 10m ramp 50-80% 90rpm\n"
            f"3x\n"
            f"- 30s 105%\n"
            f"- 1m 55%\n\n"
            f"Main Set\n"
            f"4x\n"
            f"- 4m 105%\n"
            f"- 2m 90%\n"
            f"- 2m 55%\n\n"
            f"Cooldown\n"
            f"- 10m ramp 75-50%\n\n"
            f"Over = 105% FTP ({over}W), under = 90% ({under}W).\n"
            f"Doel: leren omgaan met lactaatschommelingen. "
            f"De 'under' voelt zwaar maar je herstelt net genoeg om door te gaan."
        ),
        "duur_min": 57,
        "tss_geschat": _tss_bike(57, 0.89),
        "sport": "VirtualRide",
        "zone": "Z4 Threshold",
        "intensiteit_factor": 0.89,
    }


def _vo2max_short(ftp: int = 250) -> dict:
    """5× 4 min VO2max intervals — opbouwfase."""
    v_low = round(ftp * 1.08)
    v_high = round(ftp * 1.15)
    return {
        "type": "vo2max_intervals",
        "naam": "VO2max fiets – 5×4 min",
        "beschrijving": (
            f"Warmup\n"
            f"- 10m ramp 50-75% 90rpm\n"
            f"3x\n"
            f"- 30s 110%\n"
            f"- 1m 50%\n\n"
            f"Main Set\n"
            f"5x\n"
            f"- 4m 110%\n"
            f"- 4m 55%\n\n"
            f"Cooldown\n"
            f"- 10m ramp 75-50%\n\n"
            f"VO2max = 108-115% FTP ({v_low}-{v_high}W). Hard maar controleerbaar.\n"
            f"Laatste 2 reps niet haalbaar? Volgende keer 3×4 min."
        ),
        "duur_min": 65,
        "tss_geschat": _tss_bike(65, 0.88),
        "sport": "VirtualRide",
        "zone": "Z5 VO2max",
        "intensiteit_factor": 0.88,
    }


# ── WEEK PLAN ────────────────────────────────────────────────────────────────

def plan_sessions(
    phase: str,
    injury_guard: dict,
    load_manager: dict,
    week_start: date,
    ftp: int = 250,
    run_tss_lost: int = 0,
    skip_run_days: list = None,
    marathon_volume: dict = None,
) -> list[dict]:
    """
    Genereer fietssessies voor de week.

    Args:
        phase: huidige trainingsfase
        injury_guard: output van Injury Guard
        load_manager: output van Load Manager
        week_start: maandag van de te plannen week
        ftp: FTP in watt
        run_tss_lost: TSS die door blessure-modifier verloren ging op de run
        skip_run_days: dagen om over te slaan
        marathon_volume: output van marathon_periodizer (bevat fiets_sessies count)

    Returns:
        lijst van sessie-dicts
    """
    bike_intensity_ok = injury_guard.get("bike_intensity_allowed", True)
    volume_mod = injury_guard.get("volume_modifier", 1.0)
    week_number = load_manager.get("week_number", 1)
    skip_run_days = skip_run_days or []

    dag_offset = {"maandag": 0, "dinsdag": 1, "woensdag": 2, "donderdag": 3,
                  "vrijdag": 4, "zaterdag": 5, "zondag": 6}

    sessions = []

    # ── MARATHON FASES (via workout library) ──────────────────────────
    if marathon_volume:
        from agents import workout_library as lib
        import json
        from pathlib import Path

        fiets_sessies = marathon_volume.get("fiets_sessies", 3)
        fiets_intensiteit = marathon_volume.get("fiets_intensiteit", "sweetspot")
        has_long_run = marathon_volume.get("lange_duurloop_km", 0) > 0
        is_deload = load_manager.get("is_deload_week", False)

        # Lees progressie-state
        state_path = Path(__file__).parent.parent / "state.json"
        with open(state_path) as f:
            state = json.load(f)
        prog = state.get("progression", {})
        t_step = prog.get("threshold_step", 1)
        ss_step = prog.get("sweetspot_step", 1)
        ou_step = prog.get("over_unders_step", 1)
        spin_min = prog.get("endurance_spin_min", 90)
        long_ride_min = prog.get("long_ride_min", 120)

        # Schaal duurritten op met de weekly TSS target — meer TSS nodig = langere ritten
        weekly_tss = load_manager.get("recommended_weekly_tss", 350)
        run_tss_available = marathon_volume.get("run_tss", 100)
        bike_tss_needed = max(0, weekly_tss - run_tss_available)
        # Als er meer fiets-TSS nodig is, schaal duurritten op
        if bike_tss_needed > 200:
            spin_min = max(spin_min, 75)
            long_ride_min = max(long_ride_min, 100)

        # Bij deload: GEEN harde sessies — alleen easy rides en group rides
        if is_deload:
            deload_spin = max(45, spin_min - 20)
            deload_long = max(50, long_ride_min - 25)

            if fiets_sessies >= 3:
                sessions = [
                    {"dag": "maandag", "sessie": lib.endurance_ride(deload_spin)},
                    {"dag": "woensdag", "sessie": lib.zwift_group_ride(deload_spin)},
                    {"dag": "vrijdag", "sessie": lib.endurance_ride(deload_spin)},
                ]
                if not has_long_run:
                    sessions.append({"dag": "zondag", "sessie": lib.endurance_ride(deload_long)})
            elif fiets_sessies >= 2:
                sessions = [
                    {"dag": "woensdag", "sessie": lib.zwift_group_ride(deload_spin)},
                    {"dag": "zaterdag", "sessie": lib.endurance_ride(deload_spin)},
                ]
            elif fiets_sessies >= 1:
                sessions = [{"dag": "woensdag", "sessie": lib.endurance_ride(deload_spin)}]
            else:
                sessions = []

            # Voeg datum toe en return
            result = []
            for item in sessions:
                dag = item["dag"]
                sessie = item["sessie"].copy()
                sessie["dag"] = dag
                sessie["datum"] = (week_start + timedelta(days=dag_offset[dag])).isoformat()
                result.append(sessie)
            return result

        cycle = (week_number - 1) % 3

        # Delahaije: accumulatiefases = 100% Zone 1, ook op de fiets.
        # Alleen in transformatiefases mag sweetspot/threshold.
        is_accumulatie = fiets_intensiteit == "z1"

        if fiets_sessies >= 3:
            if is_accumulatie or not bike_intensity_ok:
                # Accumulatie: alleen Z1 duurritten
                sessions = [
                    {"dag": "maandag", "sessie": lib.endurance_ride(spin_min)},
                    {"dag": "woensdag", "sessie": lib.pick_bike_easy(spin_min, week_number)},
                    {"dag": "vrijdag", "sessie": lib.endurance_ride(max(45, spin_min - 10))},
                ]
            elif bike_intensity_ok and fiets_intensiteit == "sweetspot":
                hard_a = lib.pick_bike_hard(ftp, cycle, "A", t_step, ss_step, ou_step)
                hard_b = lib.pick_bike_hard(ftp, cycle, "B", t_step, ss_step, ou_step)
                easy = lib.pick_bike_easy(spin_min, week_number)
                sessions = [
                    {"dag": "maandag", "sessie": hard_a},
                    {"dag": "woensdag", "sessie": hard_b},
                    {"dag": "vrijdag", "sessie": easy},
                ]
            else:
                sessions = [
                    {"dag": "maandag", "sessie": lib.endurance_ride(spin_min)},
                    {"dag": "woensdag", "sessie": lib.endurance_ride(max(45, spin_min - 10))},
                    {"dag": "vrijdag", "sessie": lib.endurance_ride(max(40, spin_min - 15))},
                ]

            if not has_long_run:
                sessions.append({"dag": "zondag",
                                 "sessie": lib.pick_bike_easy(long_ride_min, week_number + 2)})

        elif fiets_sessies == 2:
            if is_accumulatie or not bike_intensity_ok:
                # Accumulatie: Z1 duurritten, +20% duur tov loopequivalent
                sessions = [
                    {"dag": "woensdag", "sessie": lib.endurance_ride(spin_min)},
                    {"dag": "zaterdag", "sessie": lib.pick_bike_easy(max(45, spin_min - 10), week_number)},
                ]
            elif bike_intensity_ok and fiets_intensiteit == "sweetspot":
                hard = lib.pick_bike_hard(ftp, cycle, "A", t_step, ss_step, ou_step)
                easy = lib.pick_bike_easy(spin_min, week_number)
                sessions = [
                    {"dag": "woensdag", "sessie": hard},
                    {"dag": "zaterdag", "sessie": easy},
                ]
            else:
                sessions = [
                    {"dag": "woensdag", "sessie": lib.endurance_ride(spin_min)},
                    {"dag": "zaterdag", "sessie": lib.endurance_ride(max(45, spin_min - 10))},
                ]

        elif fiets_sessies == 1:
            if is_accumulatie or fiets_intensiteit in ("herstel", "geen"):
                sessie = lib.pick_bike_easy(max(40, spin_min - 15), week_number)
            else:
                sessie = lib.pick_bike_hard(ftp, cycle, "A", t_step, ss_step, ou_step)
            sessions = [{"dag": "woensdag", "sessie": sessie}]
        else:
            sessions = []

        # Voeg datum toe
        result = []
        for item in sessions:
            dag = item["dag"]
            sessie = item["sessie"].copy()
            sessie["dag"] = dag
            sessie["datum"] = (week_start + timedelta(days=dag_offset[dag])).isoformat()
            result.append(sessie)
        return result

    # ── LEGACY 10KM FASES ──────────────────────────────────────────────

    # In basis_I week 1-2: zaterdag is nog een fietsdag
    zaterdag_is_fiets = phase == "basis_I" and week_number <= 2
    maandag_is_fiets = "maandag" in skip_run_days

    if phase in ("basis_I", "basis_II"):
        threshold_count = max(1, week_number)
        is_over_under_week = (week_number % 2 == 0)

        if bike_intensity_ok:
            wo_sessie = _sweetspot_long(ftp) if run_tss_lost > 0 else _sweetspot_short(ftp)
            if is_over_under_week:
                za_sessie = _over_unders(ftp)
            else:
                za_sessie = _threshold(ftp, threshold_count)
        else:
            spin_min = int(45 + max(0, run_tss_lost // 2))
            wo_sessie = _easy_spin(spin_min)
            za_sessie = _easy_spin(int(spin_min * 1.1))

        sessions = [
            {"dag": "woensdag", "sessie": wo_sessie},
            {"dag": "vrijdag", "sessie": _easy_spin(60)},
            {"dag": "zaterdag", "sessie": za_sessie},
        ]
        if maandag_is_fiets:
            sessions.append({"dag": "maandag", "sessie": _easy_spin(65)})

    elif phase in ("opbouw_I", "opbouw_II"):
        threshold_count = max(1, week_number)
        is_over_under_week = (week_number % 2 == 0)
        if bike_intensity_ok:
            if is_over_under_week:
                wo_sessie = _over_unders(ftp)
            else:
                wo_sessie = _threshold(ftp, threshold_count)
            za_sessie = _vo2max_short(ftp) if phase == "opbouw_II" else _sweetspot_long(ftp)
        else:
            wo_sessie = _sweetspot_short(ftp)
            za_sessie = _easy_spin(50)
        sessions = [
            {"dag": "woensdag", "sessie": wo_sessie},
            {"dag": "zaterdag", "sessie": za_sessie},
        ]

    elif phase == "specifiek":
        if bike_intensity_ok:
            sessions = [{"dag": "woensdag", "sessie": _sweetspot_short(ftp)}]
        else:
            sessions = [{"dag": "woensdag", "sessie": _easy_spin(45)}]

    elif phase == "afbouw":
        sessions = [{"dag": "woensdag", "sessie": _easy_spin(40)}]

    elif phase == "race_week":
        sessions = []

    # Voeg datum toe
    result = []
    for item in sessions:
        dag = item["dag"]
        sessie = item["sessie"].copy()
        sessie["dag"] = dag
        sessie["datum"] = (week_start + timedelta(days=dag_offset[dag])).isoformat()
        result.append(sessie)

    return result


if __name__ == "__main__":
    mock_injury = {
        "status": "geel",
        "bike_intensity_allowed": True,
        "volume_modifier": 1.0,
    }
    mock_load = {"recommended_weekly_tss": 380}

    monday = date(2026, 3, 16)
    sessies = plan_sessions("basis_I", mock_injury, mock_load, monday, ftp=250)

    print(f"\n=== Bike Coach — Week {monday} ===")
    total_tss = 0
    for s in sessies:
        print(f"\n{s['dag'].upper()} ({s['datum']})")
        print(f"  {s['naam']}")
        print(f"  Zone: {s['zone']} | TSS: {s['tss_geschat']} | Duur: {s['duur_min']} min")
        total_tss += s["tss_geschat"]
    print(f"\nTotaal fiets-TSS: {total_tss}")
