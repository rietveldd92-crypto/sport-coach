"""
Endurance Coach — ontwerpt de loopsessies voor de week.

Filosofie: Guido Hartensveld / Jim van den Berg
- Polarized 80/20: minimaal 80% van het volume in Z1-Z2
- Basis voor intensiteit: eerst volume, dan kwaliteit
- Knie-herstel staat voorop — geen intensiteit zonder Injury Guard groen + ontgrendeling
- Elke sessie heeft een rehab-reminder (glute med activatie)

Zone definities (hartslag, loopspecifiek):
  Z1: <68% HRmax — herstel, actief herstel
  Z2: 68-80% HRmax — aeroob basis (hier wordt het werk gedaan)
  Z3: 81-87% HRmax — drempel (VERMIJDEN tijdens basis/opbouw)
  Z4: 88-95% HRmax — VO2max (alleen specifieke fase)
  Z5: >95% HRmax — maximaal (race-simulatie, week 13)
"""

from datetime import date

REHAB_REMINDER = (
    "Rehab voor de run: 3x15 clamshells | 3x12 side-lying hip abduction | "
    "2x30s single-leg balance. Voer uit voor aanvang."
)

REHAB_REMINDER_SHORT = "Rehab oefeningen voor aanvang (glute med activatie, clamshells, hip abduction)."

# Delahaije coaching filosofie — toegevoegd aan elke sessie
DELAHAIJE_COACHING = (
    "\n\n--- Coaching (Delahaije) ---\n"
    "Gevoel is leidend, niet je horloge. Als de hartslag hoger is dan normaal "
    "(warmte, vermoeidheid, slechte nacht), verlaag je tempo.\n"
    "Zachte ondergrond waar mogelijk (gras, bospad, gravel).\n"
    "Geniet van de training — een gelukkige atleet is een snelle atleet."
)


def _tss_estimate(duration_min: int, intensity_factor: float) -> int:
    """Schat TSS: (duur in uren × IF² × 100)."""
    return round((duration_min / 60) * (intensity_factor ** 2) * 100)


# ── SESSIE TEMPLATES ─────────────────────────────────────────────────────────

def _recovery_run(duration_min: int = 35) -> dict:
    main = duration_min - 8
    return {
        "type": "herstelrun",
        "naam": f"Herstelrun – {duration_min} min Z1",
        "beschrijving": (
            f"Warmup\n"
            f"- 3m ramp 55-68% Pace\n\n"
            f"Main Set\n"
            f"- {main}m 63% Pace\n\n"
            f"Cooldown\n"
            f"- 3m ramp 65-55% Pace\n\n"
            f"Dit is een herstelrun — het doel is bewegen, niet trainen.\n"
            f"Praten = volledig moeiteloos. Kadans 175-180spm.\n"
            f"Zachte ondergrond (gras, bospad) als het kan.\n"
            f"Check linkerheup: draait been naar buiten? Bewust activeren.\n"
            f"Knie of rug: direct stoppen, meld via: python adjust.py\n\n"
            f"Rehab voor vertrek: clamshells 3x15, hip abduction 3x12, glute bridge 3x15."
            f"{DELAHAIJE_COACHING}"
        ),
        "duur_min": duration_min,
        "tss_geschat": _tss_estimate(duration_min, 0.65),
        "sport": "Run",
        "zone": "Z1",
        "intensiteit_factor": 0.65,
    }


def _aerobic_z2(duration_min: int = 65) -> dict:
    main = duration_min - 13
    return {
        "type": "aeroob_z2",
        "naam": f"Z2 duurloop – {duration_min} min",
        "beschrijving": (
            f"Warmup\n"
            f"- 5m ramp 55-80% Pace\n\n"
            f"Main Set\n"
            f"- {main}m 75% Pace\n\n"
            f"Cooldown\n"
            f"- 3m ramp 75-58% Pace\n\n"
            f"DE sleuteltraining (Delahaije): zone 2 bouwt het aerobe fundament "
            f"waarop alles rust. Vetverbranding maximaliseren, mitochondrien trainen.\n"
            f"Praten in volzinnen = goed tempo. Train trager dan je denkt.\n"
            f"Kadans 175-180spm. Zachte ondergrond waar mogelijk.\n"
            f"Linkerheup: elke 15 min check — zakt ie weg? Activeren of tempo terug.\n"
            f"Knie of rug: afschakelen of stoppen, meld via: python adjust.py\n\n"
            f"Rehab voor vertrek: clamshells 3x15, hip abduction 3x12, glute bridge 3x15."
            f"{DELAHAIJE_COACHING}"
        ),
        "duur_min": duration_min,
        "tss_geschat": _tss_estimate(duration_min, 0.75),
        "sport": "Run",
        "zone": "Z2",
        "intensiteit_factor": 0.75,
    }


def _long_run(duration_min: int = 100) -> dict:
    d1 = round(duration_min * 0.15)
    d2 = round(duration_min * 0.40)
    d3 = round(duration_min * 0.35)
    cd = duration_min - d1 - d2 - d3
    return {
        "type": "lange_duur",
        "naam": f"Lange duurloop – {duration_min} min",
        "beschrijving": (
            f"Warmup\n"
            f"- {d1}m ramp 55-78% Pace\n\n"
            f"Main Set\n"
            f"- {d2}m 68% Pace\n"
            f"- {d3}m 76% Pace\n\n"
            f"Cooldown\n"
            f"- {cd}m ramp 75-55% Pace\n\n"
            f"Volume is king (Delahaije). Nooit boven Z2, ook niet in de laatste km.\n"
            f"Begin bewust rustig — de tweede helft mag iets sneller voelen, "
            f"maar alleen als het lichaam het aanbiedt.\n"
            f"Vlak parcours, zachte ondergrond waar mogelijk.\n"
            f"Kadans 175spm+ ook als je moe wordt.\n"
            f"Drinken elke 20m (200ml). Gel of fruit na 45m.\n"
            f"Na afloop: 10m stretchen + rehab.\n"
            f"24u regel: pijn volgende ochtend erger? Meld via: python adjust.py"
            f"{DELAHAIJE_COACHING}"
        ),
        "duur_min": duration_min,
        "tss_geschat": _tss_estimate(duration_min, 0.73),
        "sport": "Run",
        "zone": "Z1/Z2",
        "intensiteit_factor": 0.73,
    }


def _aerobic_with_strides(duration_min: int = 65, strides: int = 8) -> dict:
    main = duration_min - 13
    return {
        "type": "z2_met_strides",
        "naam": f"Z2 + {strides}x strides – {duration_min} min",
        "beschrijving": (
            f"Warmup\n"
            f"- 5m ramp 55-80% Pace\n\n"
            f"Main Set\n"
            f"- {main}m 75% Pace\n\n"
            f"Neuromusculair (na de duurloop)\n"
            f"{strides}x\n"
            f"- 20s 95% Pace\n"
            f"- 1m 60% Pace\n\n"
            f"Cooldown\n"
            f"- 3m 58% Pace\n\n"
            f"Delahaije: neuromusculaire prikkels verbeteren loopeconomie zonder "
            f"overmatige belasting. 50-100m op ~3km-wedstrijdtempo.\n"
            f"Niet sprinten — vloeiend en ontspannen versnellen.\n"
            f"Stop direct bij knie- of heupklachten.\n"
            f"Zachte ondergrond (gras) voor de strides als het kan."
            f"{DELAHAIJE_COACHING}"
        ),
        "duur_min": duration_min + (strides * 1) + 5,
        "tss_geschat": _tss_estimate(duration_min, 0.77) + strides * 3,
        "sport": "Run",
        "zone": "Z2 + strides",
        "intensiteit_factor": 0.78,
    }


def _interval_10km(reps: int = 5, rep_km: float = 1.0) -> dict:
    wu_cd = 30  # warming up + cooling down
    interval_min = int(reps * rep_km * 4.1)  # ~4:06/km pace
    total_min = wu_cd + interval_min + reps * 3  # herstelminuten
    return {
        "type": "interval_10km",
        "naam": f"{reps}×{int(rep_km * 1000)}m @ 10km pace",
        "beschrijving": (
            f"WU: 15 min Z1/Z2. "
            f"Werk: {reps}× {int(rep_km * 1000)} meter @ 4:00–4:05/km (10km race pace). "
            f"Herstel: 3 min rustig lopen tussen elke rep. "
            "CD: 15 min Z1 uitlopen. "
            "Pas direct je pace aan bij knieongemak. Voorkeur: vlakke baan of tartan.\n"
            f"{REHAB_REMINDER_SHORT}"
        ),
        "duur_min": total_min,
        "tss_geschat": _tss_estimate(total_min, 0.88),
        "sport": "Run",
        "zone": "Z4",
        "intensiteit_factor": 0.88,
    }


def _tempo_run(duration_min: int = 25) -> dict:
    total_min = duration_min + 30  # WU + CD
    return {
        "type": "tempoloon",
        "naam": f"Tempoloon – {duration_min} min drempel",
        "beschrijving": (
            f"WU: 15 min rustig opbouwen. "
            f"Werk: {duration_min} min op drempelpace (4:05–4:15/km, Z3-hoog/Z4-laag). "
            "CD: 15 min rustig uitlopen. "
            "Ademhaling net niet comfortabel — dit is niet makkelijk maar wel houdbaar. "
            "Geen kniepijn toegestaan — verlaag direct tempo bij ongemak.\n"
            f"{REHAB_REMINDER_SHORT}"
        ),
        "duur_min": total_min,
        "tss_geschat": _tss_estimate(total_min, 0.86),
        "sport": "Run",
        "zone": "Z3/Z4",
        "intensiteit_factor": 0.86,
    }


def _z2_progression_run(duration_min: int = 65) -> dict:
    """Z2 progressierun: begin rustig, laatste derde iets sneller (nog steeds Z2)."""
    d1 = round(duration_min * 0.15)
    d2 = round(duration_min * 0.45)
    d3 = round(duration_min * 0.30)
    cd = max(3, duration_min - d1 - d2 - d3)
    return {
        "type": "z2_progressie",
        "naam": f"Z2 progressierun – {duration_min} min",
        "beschrijving": (
            f"Warmup\n"
            f"- {d1}m ramp 55-72% Pace\n\n"
            f"Main Set\n"
            f"- {d2}m 70% Pace\n"
            f"- {d3}m 78% Pace\n\n"
            f"Cooldown\n"
            f"- {cd}m ramp 75-55% Pace\n\n"
            f"Delahaije: 'Begin rustiger dan je denkt.' Eerste helft bewust ingehouden, "
            f"tweede helft mag het lichaam iets sneller aanbieden — maar nooit boven Z2.\n"
            f"Zachte ondergrond waar mogelijk."
            f"{DELAHAIJE_COACHING}"
        ),
        "duur_min": duration_min,
        "tss_geschat": _tss_estimate(duration_min, 0.76),
        "sport": "Run",
        "zone": "Z2",
        "intensiteit_factor": 0.76,
    }


def _z2_fartlek(duration_min: int = 55) -> dict:
    """Fartlek: ongestructureerde tempowisselingen binnen Z2. Plezier centraal."""
    main = duration_min - 13
    return {
        "type": "z2_fartlek",
        "naam": f"Z2 fartlek – {duration_min} min",
        "beschrijving": (
            f"Warmup\n"
            f"- 5m ramp 55-75% Pace\n\n"
            f"Main Set\n"
            f"- {main}m 73% Pace\n\n"
            f"Cooldown\n"
            f"- 3m ramp 72-55% Pace\n\n"
            f"Fartlek = 'speedplay'. Wissel spontaan tussen rustig en iets sneller "
            f"(bijv. tot de volgende lantaarnpaal, boom, of bocht). "
            f"Alles binnen Z2 — het gaat om ritmegevoel, niet om snelheid.\n"
            f"Delahaije: plezier in de training is geen luxe maar een voorwaarde.\n"
            f"Zachte ondergrond, wisselend terrein als het kan."
            f"{DELAHAIJE_COACHING}"
        ),
        "duur_min": duration_min,
        "tss_geschat": _tss_estimate(duration_min, 0.76),
        "sport": "Run",
        "zone": "Z2",
        "intensiteit_factor": 0.76,
    }


def _z2_trail(duration_min: int = 60) -> dict:
    """Trail/bosrun: zacht terrein, heuvels toegestaan, focus op proprioceptie."""
    main = duration_min - 10
    return {
        "type": "z2_trail",
        "naam": f"Z2 trail/bos – {duration_min} min",
        "beschrijving": (
            f"Warmup\n"
            f"- 5m ramp 55-75% Pace\n\n"
            f"Main Set\n"
            f"- {main}m 73% Pace\n\n"
            f"Cooldown\n"
            f"- 5m ramp 72-55% Pace\n\n"
            f"Bosrun op zacht terrein. Heuvels zijn ok — pas tempo aan zodat je "
            f"in Z2 blijft (bergop langzamer, bergaf ontspannen).\n"
            f"Zachte ondergrond versterkt enkels en voeten. "
            f"Proprioceptie-training = blessureprevmiddel.\n"
            f"Delahaije: 'Geleidelijke opbouw op zachte ondergrond.'"
            f"{DELAHAIJE_COACHING}"
        ),
        "duur_min": duration_min,
        "tss_geschat": _tss_estimate(duration_min, 0.75),
        "sport": "Run",
        "zone": "Z2",
        "intensiteit_factor": 0.75,
    }


# Z2 varianten roteren per week voor afwisseling
Z2_VARIANTS = [_aerobic_z2, _z2_progression_run, _z2_fartlek, _z2_trail]


# ── WEEK PLAN ────────────────────────────────────────────────────────────────

def _plan_marathon_sessions(
    vol: dict, injury_guard: dict, volume_mod: float,
    strides_ok: bool, tempo_ok: bool, run_intensity_ok: bool,
    week_start: date, skip_run_days: list,
) -> list[dict]:
    """
    Genereer loopsessies op basis van marathon_periodizer volume.

    De periodizer bepaalt het km-doel, deze functie vertaalt dat naar
    concrete sessies met de juiste templates.
    """
    from datetime import timedelta

    fase = vol["fase"]
    km_per_kort = vol.get("km_per_korte_sessie", 6)
    km_per_medium = vol.get("km_per_medium_sessie", 0)
    long_km = vol.get("lange_duurloop_km", 0)
    korte_sessies = vol.get("korte_sessies", 3)
    medium_sessies = vol.get("medium_sessies", 0)
    intensiteit = vol.get("run_intensiteit", "geen")

    # Deload: in vroege fases (fysio-opbouw) raakt deload vooral de fiets.
    # Pas in latere fases reduceer je ook het loopvolume.
    is_deload = injury_guard.get("_is_deload_week", False)
    if is_deload:
        if fase in ("herstel_opbouw_I",):
            # Fysio-schema is heilig — runs nauwelijks aanpassen
            deload_run_mod = 0.95
        elif fase in ("opbouw_II",):
            # Korte runs behouden, lange duurloop iets korter
            deload_run_mod = 0.85
        else:
            # Volle deload op runs
            deload_run_mod = 0.72
    else:
        deload_run_mod = 1.0

    # Pas volume_mod en deload toe
    km_per_kort = round(km_per_kort * volume_mod * deload_run_mod, 1)
    if km_per_medium:
        km_per_medium = round(km_per_medium * volume_mod * deload_run_mod, 1)
    if long_km:
        long_km = round(long_km * volume_mod * deload_run_mod, 1)

    sessions = []

    # Lees variatie-index uit state.json
    import json as _json
    from pathlib import Path as _Path
    _state_path = _Path(__file__).parent.parent / "state.json"
    try:
        with open(_state_path) as _f:
            _state = _json.load(_f)
        _prog = _state.get("progression", {})
        _z2_idx = _prog.get("z2_run_variety_index", 0)
    except Exception:
        _z2_idx = 0

    # ── KORTE SESSIES (Z2 varianten roteren via workout library) ──
    from agents import workout_library as lib

    korte_dagen = ["dinsdag", "donderdag", "zaterdag"][:korte_sessies]
    for i, dag in enumerate(korte_dagen):
        if dag in skip_run_days:
            continue
        duration = _km_to_minutes(km_per_kort)

        # Eerste sessie: intensiteit als toegestaan
        # Delahaije: tempoduur = Z1 (net onder aerobe drempel, 85% HRmax)
        if intensiteit == "tempoduur" and i == 0:
            sessie = lib.tempo_duurloop(reps=4, rep_min=8)
        elif intensiteit == "tempoduur_strides" and strides_ok and i == 0:
            sessie = lib.tempo_duurloop(reps=4, rep_min=8)
        elif intensiteit == "tempoduur_strides" and strides_ok and i == 1:
            sessie = lib.strides(duration, count=6)
        elif intensiteit == "strides" and strides_ok and i == 0:
            sessie = lib.strides(duration, count=8)
        elif intensiteit == "marathon_tempo" and tempo_ok and i == 0:
            sessie = lib.marathon_tempo(tempo_min=25)
        elif intensiteit == "lichte_tempo" and tempo_ok and i == 0:
            sessie = lib.marathon_tempo(tempo_min=20)
        elif intensiteit == "lichte_strides" and strides_ok and i == 0:
            sessie = lib.strides(duration, count=6)
        else:
            # Roteer Z2 varianten: elke dag een ander type uit de library
            sessie = lib.pick_z2_run(max(30, duration), _z2_idx + i)

        sessions.append({"dag": dag, "sessie": sessie})

    # ── MEDIUM SESSIES (Z2, iets langer, ook gevarieerd) ──
    if medium_sessies > 0 and km_per_medium > 0:
        medium_dag = "vrijdag"
        if medium_dag not in skip_run_days:
            duration = _km_to_minutes(km_per_medium)
            # Medium sessie is ook een Z2 variant, verschoven index voor afwisseling
            sessie = lib.pick_z2_run(max(40, duration), _z2_idx + korte_sessies)
            sessions.append({"dag": medium_dag, "sessie": sessie})

    # ── LANGE DUURLOOP (zondag) ──
    if long_km > 0:
        if "zondag" not in skip_run_days:
            sessie = lib.long_run(long_km)
            sessions.append({"dag": "zondag", "sessie": sessie})

    # ── AFBOUW/RACE WEEK ──
    if fase in ("afbouw_race", "realisatie"):
        # Lichte strides op dinsdag als het mag
        if strides_ok and sessions:
            for s in sessions:
                if s["dag"] == "dinsdag":
                    duration = s["sessie"]["duur_min"]
                    s["sessie"] = _aerobic_with_strides(duration, strides=6)
                    if DELAHAIJE_NOTE not in s["sessie"]["beschrijving"]:
                        s["sessie"]["beschrijving"] += DELAHAIJE_NOTE
                    break

    # Voeg datum toe aan elke sessie
    dag_offset = {"maandag": 0, "dinsdag": 1, "woensdag": 2, "donderdag": 3,
                  "vrijdag": 4, "zaterdag": 5, "zondag": 6}
    result = []
    for item in sessions:
        dag = item["dag"]
        sessie = item["sessie"].copy()
        sessie["dag"] = dag
        sessie["datum"] = (week_start + timedelta(days=dag_offset[dag])).isoformat()
        result.append(sessie)

    return result


def _km_to_minutes(km: float, pace_min_per_km: float = 5.8) -> int:
    """Converteer km naar minuten bij een gegeven pace (standaard ~5:48/km = Z2)."""
    return round(km * pace_min_per_km)


DELAHAIJE_NOTE = "\nOp basis van Delahaije: luister naar je lichaam, pas pace aan op gevoel."


def _marathon_long_run(km: float) -> dict:
    """Lange duurloop voor marathon-voorbereiding."""
    duration_min = _km_to_minutes(km, pace_min_per_km=6.0)
    d1 = round(duration_min * 0.12)
    d2 = round(duration_min * 0.45)
    d3 = round(duration_min * 0.35)
    cd = max(5, duration_min - d1 - d2 - d3)
    return {
        "type": "lange_duur",
        "naam": f"Lange duurloop – {km:.0f} km",
        "beschrijving": (
            f"Warmup\n"
            f"- {d1}m ramp 55-75% Pace\n\n"
            f"Main Set\n"
            f"- {d2}m 68% Pace\n"
            f"- {d3}m 74% Pace\n\n"
            f"Cooldown\n"
            f"- {cd}m ramp 73-55% Pace\n\n"
            f"Volume is king (Delahaije). Dit is de belangrijkste training van de week.\n"
            f"Begin bewust langzaam — de tweede helft mag iets sneller voelen, "
            f"maar alleen als het lichaam het aanbiedt. Nooit boven Z2.\n"
            f"Vlak parcours, zachte ondergrond waar mogelijk.\n"
            f"Kadans 175spm+ ook als je moe wordt.\n"
            f"Voeding: drinken elke 20m, gel/fruit na 45m. Oefen racedag-voeding!\n"
            f"Na afloop: 10m stretchen + rehab."
            f"{DELAHAIJE_COACHING}"
        ),
        "duur_min": duration_min,
        "tss_geschat": _tss_estimate(duration_min, 0.73),
        "sport": "Run",
        "zone": "Z1/Z2",
        "intensiteit_factor": 0.73,
    }


def _marathon_tempo_run(tempo_min: int = 25) -> dict:
    """Marathon-specifieke temporun (blokken op marathontempo ~5:20/km)."""
    total_min = tempo_min + 30
    return {
        "type": "marathon_tempo",
        "naam": f"Marathon tempo – {tempo_min} min",
        "beschrijving": (
            f"Warmup\n"
            f"- 15m ramp 55-78% Pace\n\n"
            f"Main Set\n"
            f"- {tempo_min}m 82% Pace\n\n"
            f"Cooldown\n"
            f"- 15m ramp 78-55% Pace\n\n"
            f"Delahaije: 'Loop zo hard als je kunt, maar de laatste minuten moeten "
            f"net zo snel zijn als de eerste.' Niet harder starten dan je kunt volhouden.\n"
            f"Comfortabel hard — praten in korte zinnen. Geen kniepijn toegestaan.\n"
            f"Meld klachten via: python adjust.py"
            f"{DELAHAIJE_COACHING}"
        ),
        "duur_min": total_min,
        "tss_geschat": _tss_estimate(total_min, 0.82),
        "sport": "Run",
        "zone": "Z3",
        "intensiteit_factor": 0.82,
    }


def plan_sessions(
    phase: str,
    injury_guard: dict,
    load_manager: dict,
    week_start: date,
    skip_run_days: list = None,
    marathon_volume: dict = None,
) -> list[dict]:
    """
    Genereer loopsessies voor de week.

    Args:
        phase: huidige trainingsfase
        injury_guard: output van Injury Guard
        load_manager: output van Load Manager
        week_start: maandag van de te plannen week
        skip_run_days: dagen om over te slaan
        marathon_volume: output van marathon_periodizer.calculate_weekly_run_volume()

    Returns:
        lijst van sessie-dicts
    """
    strides_ok = injury_guard.get("strides_allowed", False)
    tempo_ok = injury_guard.get("tempo_allowed", False)
    run_intensity_ok = injury_guard.get("run_intensity_allowed", False)
    volume_mod = injury_guard.get("volume_modifier", 1.0)
    weekly_tss = load_manager.get("recommended_weekly_tss", 380)
    week_number = load_manager.get("week_number", 1)

    sessions = []
    skip_run_days = skip_run_days or []

    # ── MARATHON FASES (als marathon_volume beschikbaar is) ──────────────
    if marathon_volume:
        return _plan_marathon_sessions(
            marathon_volume, injury_guard, volume_mod, strides_ok, tempo_ok,
            run_intensity_ok, week_start, skip_run_days
        )

    # ── LEGACY 10KM FASES ───────────────────────────────────────────────

    # ── BASIS FASE I (wk 1-3): Frequentie opbouwen — kort maar vaak ──
    if phase == "basis_I":
        easy_min  = int(35 * volume_mod)
        z2_min    = 50
        long_min  = int(90 * volume_mod)

        if week_number <= 2:
            sessions = [
                {"dag": "maandag",  "sessie": _recovery_run(easy_min)},
                {"dag": "dinsdag",  "sessie": _aerobic_z2(z2_min)},
                {"dag": "donderdag","sessie": _aerobic_z2(z2_min)},
                {"dag": "vrijdag",  "sessie": _recovery_run(easy_min)},
                {"dag": "zondag",   "sessie": _long_run(long_min)},
            ]
        else:
            sessions = [
                {"dag": "maandag",  "sessie": _recovery_run(easy_min)},
                {"dag": "dinsdag",  "sessie": _aerobic_z2(z2_min)},
                {"dag": "donderdag","sessie": _aerobic_z2(z2_min)},
                {"dag": "vrijdag",  "sessie": _recovery_run(easy_min)},
                {"dag": "zaterdag", "sessie": _recovery_run(easy_min)},
                {"dag": "zondag",   "sessie": _long_run(long_min)},
            ]

    elif phase == "basis_II":
        easy_min = int(40 * volume_mod)
        z2_min   = int(65 * volume_mod)
        long_min = int(90 * volume_mod)

        sessions = [
            {"dag": "maandag",  "sessie": _recovery_run(easy_min)},
            {"dag": "dinsdag",  "sessie": _aerobic_z2(z2_min)},
            {"dag": "donderdag","sessie": _aerobic_z2(z2_min)},
            {"dag": "vrijdag",  "sessie": _recovery_run(easy_min)},
            {"dag": "zaterdag", "sessie": _recovery_run(easy_min)},
            {"dag": "zondag",   "sessie": _long_run(long_min)},
        ]

    elif phase in ("opbouw_I", "opbouw_II"):
        easy_min = int(40 * volume_mod)
        z2_min   = int(70 * volume_mod)
        long_min = int(110 * volume_mod)

        if strides_ok:
            tue_session = _aerobic_with_strides(z2_min, strides=8)
            thu_session = _aerobic_z2(int(65 * volume_mod))
        else:
            tue_session = _aerobic_z2(z2_min)
            thu_session = _aerobic_z2(int(65 * volume_mod))

        sessions = [
            {"dag": "maandag",  "sessie": _recovery_run(easy_min)},
            {"dag": "dinsdag",  "sessie": tue_session},
            {"dag": "donderdag","sessie": thu_session},
            {"dag": "vrijdag",  "sessie": _recovery_run(easy_min)},
            {"dag": "zaterdag", "sessie": _recovery_run(easy_min)},
            {"dag": "zondag",   "sessie": _long_run(long_min)},
        ]

    elif phase == "specifiek":
        if tempo_ok and run_intensity_ok:
            sessions = [
                {"dag": "dinsdag",  "sessie": _interval_10km(reps=5)},
                {"dag": "donderdag","sessie": _aerobic_z2(int(70 * volume_mod))},
                {"dag": "vrijdag",  "sessie": _recovery_run(int(35 * volume_mod))},
                {"dag": "zondag",   "sessie": _long_run(int(105 * volume_mod))},
            ]
        elif strides_ok:
            sessions = [
                {"dag": "dinsdag",  "sessie": _aerobic_with_strides(int(70 * volume_mod), 10)},
                {"dag": "donderdag","sessie": _aerobic_z2(int(65 * volume_mod))},
                {"dag": "vrijdag",  "sessie": _recovery_run(int(35 * volume_mod))},
                {"dag": "zondag",   "sessie": _long_run(int(100 * volume_mod))},
            ]
        else:
            sessions = [
                {"dag": "dinsdag",  "sessie": _aerobic_z2(int(70 * volume_mod))},
                {"dag": "donderdag","sessie": _aerobic_z2(int(65 * volume_mod))},
                {"dag": "vrijdag",  "sessie": _recovery_run(int(35 * volume_mod))},
                {"dag": "zondag",   "sessie": _long_run(int(100 * volume_mod))},
            ]

    elif phase == "afbouw":
        sessions = [
            {"dag": "dinsdag",  "sessie": _aerobic_with_strides(55, 6) if strides_ok else _aerobic_z2(55)},
            {"dag": "donderdag","sessie": _aerobic_z2(50)},
            {"dag": "vrijdag",  "sessie": _recovery_run(30)},
            {"dag": "zondag",   "sessie": _long_run(80)},
        ]

    elif phase == "race_week":
        sessions = [
            {"dag": "maandag",  "sessie": _recovery_run(25)},
            {"dag": "woensdag", "sessie": _aerobic_with_strides(40, 4) if strides_ok else _aerobic_z2(40)},
            {"dag": "vrijdag",  "sessie": _recovery_run(20)},
        ]

    # Verwijder overgeslagen dagen — vervang door extra run op woensdag als maandag wegvalt
    if skip_run_days:
        skipped = [s for s in sessions if s["dag"] in skip_run_days]
        sessions = [s for s in sessions if s["dag"] not in skip_run_days]

        # Als maandag wegvalt en woensdag nog geen run heeft: voeg korte run toe op woensdag
        if "maandag" in skip_run_days:
            has_wednesday_run = any(s["dag"] == "woensdag" for s in sessions)
            if not has_wednesday_run and skipped:
                wo_sessie = skipped[0]["sessie"].copy()  # zelfde type als de overgeslagen sessie
                sessions.append({"dag": "woensdag", "sessie": wo_sessie})

    # Voeg week_start datum toe aan elke sessie
    from datetime import timedelta
    dag_offset = {"maandag": 0, "dinsdag": 1, "woensdag": 2, "donderdag": 3,
                  "vrijdag": 4, "zaterdag": 5, "zondag": 6}

    result = []
    for item in sessions:
        dag = item["dag"]
        sessie = item["sessie"].copy()
        sessie["dag"] = dag
        sessie["datum"] = (week_start + timedelta(days=dag_offset[dag])).isoformat()
        result.append(sessie)

    return result


if __name__ == "__main__":
    from datetime import date
    # Test
    mock_injury = {
        "status": "geel",
        "run_intensity_allowed": False,
        "strides_allowed": False,
        "tempo_allowed": False,
        "bike_intensity_allowed": True,
        "volume_modifier": 0.9,
    }
    mock_load = {
        "recommended_weekly_tss": 380,
        "current_phase": "basis_I",
    }

    monday = date(2026, 3, 16)
    sessies = plan_sessions("basis_I", mock_injury, mock_load, monday)

    print(f"\n=== Endurance Coach — Week {monday} ===")
    total_tss = 0
    for s in sessies:
        print(f"\n{s['dag'].upper()} ({s['datum']})")
        print(f"  {s['naam']}")
        print(f"  Zone: {s['zone']} | TSS: {s['tss_geschat']} | Duur: {s['duur_min']} min")
        total_tss += s["tss_geschat"]
    print(f"\nTotaal loop-TSS: {total_tss}")
