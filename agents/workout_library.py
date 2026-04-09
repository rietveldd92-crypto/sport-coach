"""
Workout Library — bibliotheek van alle beschikbare sessies.

De coaches (endurance_coach, bike_coach) selecteren uit deze bibliotheek
op basis van fase, progressie-stap, variatie-index en deload-status.

Elke workout heeft:
- Een structured intervals.icu beschrijving (met correcte Nx herhalingen)
- Tags voor selectie (intensity, type, indoor/outdoor, fun_factor)
- Een progressie-ladder waar van toepassing
- Delahaije coaching notes

Structuur:
  BIKE_WORKOUTS  — dict per categorie (threshold, sweetspot, endurance, fun, ...)
  RUN_WORKOUTS   — dict per categorie (z2_variants, long_run_variants, speed, ...)
"""


# ── DELAHAIJE COACHING ──────────────────────────────────────────────────────

DELAHAIJE_RUN = (
    "\n\n--- Coaching (Delahaije) ---\n"
    "Gevoel is leidend, niet je horloge. Als de hartslag hoger is dan normaal "
    "(warmte, vermoeidheid, slechte nacht), verlaag je tempo.\n"
    "Zachte ondergrond waar mogelijk (gras, bospad, gravel).\n"
    "Geniet van de training — een gelukkige atleet is een snelle atleet."
)

DELAHAIJE_BIKE = (
    "\n\nDelahaije: 'Lopers hoeven niet meer km te maken, maar kunnen wel de "
    "trainingstijd vergroten door te fietsen.' De mitochondrien maken het niet "
    "uit of je ze traint door te fietsen of te lopen — aerobe winst is gelijk, "
    "impactbelasting nul."
)

REHAB_PRE_RUN = (
    "Rehab voor vertrek: clamshells 3x15, hip abduction 3x12, glute bridge 3x15."
)


# ── HELPER ──────────────────────────────────────────────────────────────────

def _tss_run(duration_min: int, intensity_factor: float) -> int:
    return round((duration_min / 60) * (intensity_factor ** 2) * 100)

def _tss_bike(duration_min: int, intensity_factor: float) -> int:
    return round((duration_min / 60) * (intensity_factor ** 2) * 100)

def _km_to_min(km: float, pace: float = 5.8) -> int:
    return round(km * pace)


# ═══════════════════════════════════════════════════════════════════════════
# FIETS WORKOUTS
# ═══════════════════════════════════════════════════════════════════════════

def threshold(ftp: int, step: int) -> dict:
    """Threshold progressie-ladder. Wisselt volume, intensiteit en piek af.

    Drie dimensies:
    - Volume: langer op standaard vermogen (97%)
    - Intensiteit: zelfde duur, hoger vermogen (100-102%)
    - Piek: korter maar harder (103-105%)
    """
    steps = [
        # (naam, main_set, duur_min, IF, note, dimensie)
        ("3x8 min @ 95%",   "3x\n- 8m 95% 85rpm\n- 3m 55% 95rpm",   45, 0.86,
         "Intro. Net onder FTP — voel het ritme.", "intro"),
        ("2x10 min @ 100%", "2x\n- 10m 100% 85rpm\n- 4m 55% 95rpm", 45, 0.89,
         "Meer vermogen, korter. FTP exact.", "intensiteit"),
        ("3x10 min @ 97%",  "3x\n- 10m 97% 85rpm\n- 3m 55% 95rpm",  52, 0.89,
         "Volume: meer sets op standaard vermogen.", "volume"),
        ("2x12 min @ 100%", "2x\n- 12m 100% 85rpm\n- 4m 55% 95rpm", 48, 0.91,
         "Langer op FTP. Gelijkmatig — niet te hard starten.", "intensiteit"),
        ("2x15 min @ 97%",  "2x\n- 15m 97% 85rpm\n- 5m 55% 95rpm",  55, 0.91,
         "Langere blokken. Even doortrappen in het tweede blok.", "volume"),
        ("3x8 min @ 103%",  "3x\n- 8m 103% 85rpm\n- 4m 55% 95rpm",  49, 0.92,
         "Piek: boven FTP. Kort maar pittig.", "piek"),
        ("3x15 min @ 97%",  "3x\n- 15m 97% 85rpm\n- 5m 55% 95rpm",  75, 0.93,
         "45 min totaal. Mentale hardheid — derde blok is karakter.", "volume"),
        ("2x15 min @ 100%", "2x\n- 15m 100% 85rpm\n- 5m 55% 95rpm", 55, 0.93,
         "Langere blokken op exact FTP. Duurvermogen.", "intensiteit"),
        ("2x20 min @ 97%",  "2x\n- 20m 97% 85rpm\n- 5m 55% 95rpm",  65, 0.93,
         "Gelijkmatig — niet te hard starten.", "volume"),
        ("2x10 min @ 105%", "2x\n- 10m 105% 85rpm\n- 5m 55% 95rpm", 50, 0.94,
         "Boven FTP. Kort maar maximaal. FTP-test in vermomming.", "piek"),
        ("3x20 min @ 97%",  "3x\n- 20m 97% 85rpm\n- 5m 55% 95rpm",  85, 0.94,
         "60 min werk. Dit is race-niveau.", "volume"),
        ("1x40 min @ 97%",  "- 40m 97% 85rpm",                       65, 0.95,
         "Ononderbroken threshold. Ultieme duurtest.", "volume"),
    ]
    idx = min(max(step - 1, 0), len(steps) - 1)
    naam, main, duur, if_val, note, _dim = steps[idx]
    t_watts = round(ftp * 0.97)
    return {
        "type": "threshold", "naam": f"Threshold – {naam}",
        "beschrijving": (
            f"Warmup\n- 10m ramp 50-80% 90rpm\n"
            f"3x\n- 30s 105%\n- 1m 55%\n\n"
            f"Main Set\n{main}\n\n\n"
            f"Cooldown\n- 10m ramp 75-50%\n\n"
            f"Threshold = 97% FTP ({t_watts}W). {note}"
            f"{DELAHAIJE_BIKE}"
        ),
        "duur_min": duur, "tss_geschat": _tss_bike(duur, if_val),
        "sport": "VirtualRide", "zone": "Z4 Threshold",
        "intensiteit_factor": if_val, "fun": 3,
    }


def sweetspot(ftp: int, step: int) -> dict:
    """Sweetspot progressie-ladder. Wisselt volume, intensiteit en piek af.

    Drie dimensies:
    - Volume: langer op 88-90% FTP
    - Intensiteit: zelfde duur, hoger vermogen (92-95%)
    - Piek: korter maar harder (95%+, raakt threshold)
    """
    steps = [
        # (naam, main_set, duur_min, IF, note, dimensie)
        ("2x10 min @ 88%",  "2x\n- 10m 88% 88rpm\n- 4m 60% 95rpm",  42, 0.82,
         "Kennismaking. Onderkant sweetspot — comfortabel.", "intro"),
        ("2x10 min @ 93%",  "2x\n- 10m 93% 88rpm\n- 4m 60% 95rpm",  42, 0.84,
         "Zelfde duur, meer vermogen. Bovenkant sweetspot.", "intensiteit"),
        ("2x15 min @ 88%",  "2x\n- 15m 88% 88rpm\n- 5m 60% 95rpm",  55, 0.84,
         "Langer vasthouden op basis-vermogen.", "volume"),
        ("3x10 min @ 90%",  "3x\n- 10m 90% 88rpm\n- 4m 60% 95rpm",  52, 0.84,
         "Meer sets, kortere blokken. Verdeel je energie gelijk.", "volume"),
        ("2x12 min @ 95%",  "2x\n- 12m 95% 88rpm\n- 4m 55% 95rpm",  48, 0.87,
         "Piek: raakt bijna threshold. Kort maar pittig.", "piek"),
        ("3x15 min @ 88%",  "3x\n- 15m 88% 88rpm\n- 5m 60% 95rpm",  70, 0.85,
         "45 min totaal. Pure volume-training.", "volume"),
        ("2x15 min @ 93%",  "2x\n- 15m 93% 88rpm\n- 5m 60% 95rpm",  55, 0.87,
         "Langere blokken op hoog vermogen. Dit bouwt echte kracht.", "intensiteit"),
        ("3x12 min @ 93%",  "3x\n- 12m 93% 88rpm\n- 4m 60% 95rpm",  56, 0.87,
         "Volume + intensiteit. 36 min hoog vermogen.", "intensiteit"),
        ("2x20 min @ 90%",  "2x\n- 20m 90% 88rpm\n- 5m 60% 95rpm",  65, 0.86,
         "Langste blokken. Mentale uitdaging.", "volume"),
        ("2x10 min @ 97%",  "2x\n- 10m 97% 88rpm\n- 5m 55% 95rpm",  45, 0.89,
         "Piek: dit IS threshold. 20 min op FTP. FTP-groei!", "piek"),
        ("3x20 min @ 90%",  "3x\n- 20m 90% 88rpm\n- 5m 60% 95rpm",  85, 0.88,
         "60 min werk. Race-voorbereiding op de fiets.", "volume"),
        ("1x45 min @ 90%",  "- 45m 90% 88rpm",                       65, 0.88,
         "Ononderbroken sweetspot. Ultieme duurtest.", "volume"),
    ]
    idx = min(max(step - 1, 0), len(steps) - 1)
    naam, main, duur, if_val, note, _dim = steps[idx]
    ss_low = round(ftp * 0.88)
    ss_high = round(ftp * 0.93)
    return {
        "type": "sweetspot", "naam": f"Sweetspot – {naam}",
        "beschrijving": (
            f"Warmup\n- 7m ramp 55-80% 90rpm\n"
            f"3x\n- 30s 110%\n- 1m 55%\n\n"
            f"Main Set\n{main}\n\n\n"
            f"Cooldown\n- 10m ramp 75-50%\n\n"
            f"Sweetspot = 88-93% FTP ({ss_low}-{ss_high}W). {note}"
            f"{DELAHAIJE_BIKE}"
        ),
        "duur_min": duur, "tss_geschat": _tss_bike(duur, if_val),
        "sport": "VirtualRide", "zone": "Sweetspot",
        "intensiteit_factor": if_val, "fun": 3,
    }


def over_unders(ftp: int, step: int) -> dict:
    """Over-unders progressie. Wisselt volume, intensiteit en piek af."""
    steps = [
        # (naam, main_set, duur_min, IF, note, dimensie)
        ("3x(3m/2m) @ 105/88",  "3x\n- 3m 105%\n- 2m 88%\n- 2m 55%",  36, 0.87,
         "Intro. Leer het gevoel van boven-onder FTP wisselen.", "intro"),
        ("3x(3m/2m) @ 108/85",  "3x\n- 3m 108%\n- 2m 85%\n- 2m 55%",  36, 0.88,
         "Hogere piek, dieper herstel. Grotere schommelingen.", "intensiteit"),
        ("4x(4m/2m) @ 105/88",  "4x\n- 4m 105%\n- 2m 88%\n- 2m 55%",  52, 0.89,
         "Meer volume: langere 'over' blokken + extra set.", "volume"),
        ("3x(5m/3m) @ 108/85",  "3x\n- 5m 108%\n- 3m 85%\n- 2m 55%",  48, 0.91,
         "Langere pieken op hoog vermogen. Serieus lactaat-management.", "piek"),
        ("4x(5m/3m) @ 105/88",  "4x\n- 5m 105%\n- 3m 88%\n- 2m 55%",  60, 0.91,
         "32 min werk. Volume + complexiteit.", "volume"),
        ("3x(4m/3m/2m)",        "3x\n- 4m 110%\n- 3m 95%\n- 2m 85%\n- 2m 55%",  51, 0.92,
         "Trap-af blokken: hoog → midden → laag. Mentale hardheid.", "piek"),
    ]
    idx = min(max(step - 1, 0), len(steps) - 1)
    naam, main, duur, if_val, note, _dim = steps[idx]
    over_w = round(ftp * 1.05)
    under_w = round(ftp * 0.88)
    return {
        "type": "over_unders", "naam": f"Over-unders – {naam}",
        "beschrijving": (
            f"Warmup\n- 10m ramp 50-80% 90rpm\n"
            f"3x\n- 30s 105%\n- 1m 55%\n\n"
            f"Main Set\n{main}\n\n\n"
            f"Cooldown\n- 10m ramp 75-50%\n\n"
            f"Over = 105% FTP ({over_w}W), under = 88% ({under_w}W). {note}"
            f"{DELAHAIJE_BIKE}"
        ),
        "duur_min": duur, "tss_geschat": _tss_bike(duur, if_val),
        "sport": "VirtualRide", "zone": "Z4 Threshold",
        "intensiteit_factor": if_val, "fun": 4,
    }


def cadence_pyramids(ftp: int) -> dict:
    """Kadanspyramide — neuromusculair werk op de fiets. Leuk en effectief."""
    return {
        "type": "cadence_pyramids", "naam": "Kadanspyramide",
        "beschrijving": (
            "Warmup\n- 10m ramp 50-75% 85rpm\n\n"
            "Main Set\n"
            "- 3m 75% 70rpm\n"
            "- 3m 75% 80rpm\n"
            "- 3m 75% 90rpm\n"
            "- 3m 75% 100rpm\n"
            "- 3m 75% 110rpm\n"
            "- 2m 55% 85rpm\n"
            "- 3m 75% 110rpm\n"
            "- 3m 75% 100rpm\n"
            "- 3m 75% 90rpm\n"
            "- 3m 75% 80rpm\n"
            "- 3m 75% 70rpm\n\n"
            "Cooldown\n- 8m ramp 70-50%\n\n"
            "Neuromusculair: leer je benen op verschillende kadansen te werken.\n"
            "Laag = kracht, hoog = snelheid. Vermogen constant houden!"
            f"{DELAHAIJE_BIKE}"
        ),
        "duur_min": 51, "tss_geschat": _tss_bike(51, 0.78),
        "sport": "VirtualRide", "zone": "Z2-Z3 Cadence",
        "intensiteit_factor": 0.78, "fun": 5,
    }


def microbursts(ftp: int) -> dict:
    """Microbursts — 15s on/15s off. Verrassend leuk, goed voor VO2max."""
    return {
        "type": "microbursts", "naam": "Microbursts 15/15",
        "beschrijving": (
            "Warmup\n- 10m ramp 50-80% 90rpm\n"
            "3x\n- 30s 110%\n- 1m 55%\n\n"
            "Main Set\n"
            "3x\n"
            "- 5m 55%\n"
            "- 15s 150%\n- 15s 55%\n"
            "- 15s 150%\n- 15s 55%\n"
            "- 15s 150%\n- 15s 55%\n"
            "- 15s 150%\n- 15s 55%\n"
            "- 15s 150%\n- 15s 55%\n"
            "- 15s 150%\n- 15s 55%\n"
            "- 15s 150%\n- 15s 55%\n"
            "- 15s 150%\n- 15s 55%\n"
            "- 15s 150%\n- 15s 55%\n"
            "- 15s 150%\n- 15s 55%\n\n"
            "Cooldown\n- 10m ramp 70-50%\n\n"
            "10x 15s aan/15s uit per set, 3 sets. Korte pieken, snel herstel.\n"
            "Voelt als een spel — tel af en ga! Goed voor VO2max zonder lange pijn."
            f"{DELAHAIJE_BIKE}"
        ),
        "duur_min": 50, "tss_geschat": _tss_bike(50, 0.85),
        "sport": "VirtualRide", "zone": "VO2max",
        "intensiteit_factor": 0.85, "fun": 5,
    }


def tempo_blocks(ftp: int) -> dict:
    """Tempo blokken — net onder sweetspot. Goed voor aerobe capaciteit."""
    return {
        "type": "tempo_blocks", "naam": "Tempo blokken 3x12 min",
        "beschrijving": (
            "Warmup\n- 10m ramp 50-78% 90rpm\n\n"
            "Main Set\n"
            "3x\n"
            "- 12m 85% 88rpm\n"
            "- 4m 55% 95rpm\n\n"
            "Cooldown\n- 10m ramp 75-50%\n\n"
            "Tempo = 83-87% FTP. Net onder sweetspot — comfortabel ongemak.\n"
            "Goed voor duurvermogen zonder de vermoeidheid van sweetspot."
            f"{DELAHAIJE_BIKE}"
        ),
        "duur_min": 58, "tss_geschat": _tss_bike(58, 0.83),
        "sport": "VirtualRide", "zone": "Tempo",
        "intensiteit_factor": 0.83, "fun": 3,
    }


def endurance_ride(duration_min: int) -> dict:
    """Duurrit Z2 met terreinwisselingen — simuleer een echte buitenrit."""
    main = duration_min - 15
    if main >= 60:
        # Lange rit: rolling terrain met heuveltjes en dalletjes
        seg = main // 6
        rest = main - seg * 6
        blocks = (
            f"- {seg}m 63% 90rpm\n"
            f"- {seg}m ramp 63-75% 85rpm\n"
            f"- {seg}m 70% 80rpm\n"
            f"- {seg}m 60% 95rpm\n"
            f"- {seg}m ramp 60-73% 85rpm\n"
            f"- {seg + rest}m 65% 90rpm"
        )
    elif main >= 40:
        # Medium rit: drie plateaus met overgangen
        seg = main // 4
        rest = main - seg * 4
        blocks = (
            f"- {seg}m 63% 90rpm\n"
            f"- {seg}m 70% 85rpm\n"
            f"- {seg}m 60% 95rpm\n"
            f"- {seg + rest}m 68% 88rpm"
        )
    else:
        blocks = (
            f"- {main // 2}m 63% 90rpm\n"
            f"- {main - main // 2}m 68% 85rpm"
        )
    return {
        "type": "endurance_ride", "naam": f"Duurrit rolling Z2 – {duration_min} min",
        "beschrijving": (
            f"Warmup\n- 8m ramp 45-63% 85rpm\n\n"
            f"Main Set\n{blocks}\n\n\n"
            f"Cooldown\n- 7m ramp 63-45%\n\n"
            f"Simuleer een buitenrit: wisselend terrein, heuveltjes, "
            f"dalletjes, kopwind-secties. Alles binnen Z2.\n"
            f"Kadans varieert mee: lager in de 'heuvels', hoger in de 'afdaling'."
            f"{DELAHAIJE_BIKE}"
        ),
        "duur_min": duration_min, "tss_geschat": _tss_bike(duration_min, 0.66),
        "sport": "VirtualRide", "zone": "Z2",
        "intensiteit_factor": 0.66, "fun": 3,
    }


def zwift_group_ride(duration_min: int = 60) -> dict:
    """Zwift group ride — ongestructureerd, simuleer het peloton-effect."""
    # Simuleer surges en rustige stukken zoals in een echte group ride
    main = duration_min - 10
    surges = max(3, main // 15)
    cruise = max(5, (main - surges * 3) // surges)
    return {
        "type": "zwift_group", "naam": f"Zwift group ride – {duration_min} min",
        "beschrijving": (
            f"Warmup\n- 5m ramp 45-65%\n\n"
            f"Main Set\n"
            f"{surges}x\n"
            f"- {cruise}m 68% 90rpm\n"
            f"- 1m 85% 95rpm\n"
            f"- 2m 60% 90rpm\n\n\n"
            f"Cooldown\n- 5m ramp 65-45%\n\n"
            f"Simuleer een Zwift group ride: rustig cruisen met af en toe "
            f"een surge als het 'peloton' versnelt. Reageer op de surges "
            f"maar ga niet voluit — houd het speels.\n"
            f"Of join een echte group ride (cat C/D) en rij mee op gevoel.\n"
            f"Sociaal fietsen = plezier = motivatie.\n"
            f"Delahaije: een gelukkige atleet is een snelle atleet."
            f"{DELAHAIJE_BIKE}"
        ),
        "duur_min": duration_min, "tss_geschat": _tss_bike(duration_min, 0.72),
        "sport": "VirtualRide", "zone": "Z2-Z3",
        "intensiteit_factor": 0.72, "fun": 5,
    }


def single_leg_drills(ftp: int) -> dict:
    """Single-leg drills — techniek en balans. Verrassend pittig."""
    return {
        "type": "single_leg_drills", "naam": "Single-leg drills + Z2",
        "beschrijving": (
            "Warmup\n- 10m ramp 50-70% 85rpm\n\n"
            "Main Set\n"
            "4x\n"
            "- 1m 60% left leg only 60rpm\n"
            "- 1m 60% right leg only 60rpm\n"
            "- 3m 65% 90rpm\n\n"
            "- 20m 65% 90rpm\n\n"
            "Cooldown\n- 5m ramp 65-45%\n\n"
            "Eenbeen-drills verbeteren je trap-techniek en balans.\n"
            "Niet hard trappen — focus op ronde, vloeiende beweging.\n"
            "De Z2-blokken ertussen houden het aerobe volume op peil."
            f"{DELAHAIJE_BIKE}"
        ),
        "duur_min": 55, "tss_geschat": _tss_bike(55, 0.68),
        "sport": "VirtualRide", "zone": "Z2 Techniek",
        "intensiteit_factor": 0.68, "fun": 4,
    }


# ═══════════════════════════════════════════════════════════════════════════
# RUN WORKOUTS
# ═══════════════════════════════════════════════════════════════════════════

def z2_standard(duration_min: int) -> dict:
    """Standaard Z2 duurloop — de sleuteltraining (Delahaije)."""
    main = max(10, duration_min - 13)
    return {
        "type": "z2_standard", "naam": f"Z2 duurloop – {duration_min} min",
        "beschrijving": (
            f"Warmup\n- 5m ramp 55-80% Pace\n\n"
            f"Main Set\n- {main}m 75% Pace\n\n"
            f"Cooldown\n- 3m ramp 75-58% Pace\n\n"
            f"DE sleuteltraining (Delahaije): zone 2 bouwt het fundament.\n"
            f"Praten in volzinnen. Train trager dan je denkt.\n"
            f"Kadans 175-180spm. {REHAB_PRE_RUN}"
            f"{DELAHAIJE_RUN}"
        ),
        "duur_min": duration_min, "tss_geschat": _tss_run(duration_min, 0.75),
        "sport": "Run", "zone": "Z2",
        "intensiteit_factor": 0.75, "fun": 3,
    }


def z2_progression(duration_min: int) -> dict:
    """Progressierun: begin rustig, laatste derde iets sneller. Nog steeds Z2."""
    d1 = round(duration_min * 0.15)
    d2 = round(duration_min * 0.45)
    d3 = round(duration_min * 0.30)
    cd = max(3, duration_min - d1 - d2 - d3)
    return {
        "type": "z2_progression", "naam": f"Progressierun – {duration_min} min",
        "beschrijving": (
            f"Warmup\n- {d1}m ramp 55-72% Pace\n\n"
            f"Main Set\n- {d2}m 70% Pace\n- {d3}m 78% Pace\n\n"
            f"Cooldown\n- {cd}m ramp 75-55% Pace\n\n"
            f"'Begin rustiger dan je denkt.' Eerste helft ingehouden, "
            f"tweede helft mag het lichaam iets sneller aanbieden.\n"
            f"Nooit boven Z2. {REHAB_PRE_RUN}"
            f"{DELAHAIJE_RUN}"
        ),
        "duur_min": duration_min, "tss_geschat": _tss_run(duration_min, 0.76),
        "sport": "Run", "zone": "Z2",
        "intensiteit_factor": 0.76, "fun": 4,
    }


def z2_fartlek(duration_min: int) -> dict:
    """Echte fartlek: afwisseling rustig/iets sneller in gestructureerde blokken."""
    main = max(10, duration_min - 13)
    # Maak echte fartlek-blokken: afwisselend 3 min rustig / 2 min iets sneller
    reps = max(2, main // 5)
    remaining = main - reps * 5
    return {
        "type": "z2_fartlek", "naam": f"Fartlek – {duration_min} min",
        "beschrijving": (
            f"Warmup\n- 5m ramp 55-75% Pace\n\n"
            f"Main Set\n"
            f"{reps}x\n"
            f"- 3m 68% Pace\n"
            f"- 2m 80% Pace\n"
            + (f"- {remaining}m 70% Pace\n" if remaining > 2 else "") +
            f"\nCooldown\n- 3m ramp 70-55% Pace\n\n"
            f"Fartlek = 'snelheidsspel'. Wissel tussen rustig en iets sneller.\n"
            f"De snellere stukken zijn Z2-bovenkant, niet Z3! Moet nog praten kunnen.\n"
            f"Delahaije: plezier in de training is een voorwaarde, geen luxe."
            f"{DELAHAIJE_RUN}"
        ),
        "duur_min": duration_min, "tss_geschat": _tss_run(duration_min, 0.77),
        "sport": "Run", "zone": "Z2",
        "intensiteit_factor": 0.77, "fun": 5,
    }


def z2_trail(duration_min: int) -> dict:
    """Trail/bosrun. Zacht terrein, proprioceptie, avontuur."""
    main = max(10, duration_min - 10)
    return {
        "type": "z2_trail", "naam": f"Bosrun – {duration_min} min",
        "beschrijving": (
            f"Warmup\n- 5m ramp 55-75% Pace\n\n"
            f"Main Set\n- {main}m 73% Pace\n\n"
            f"Cooldown\n- 5m ramp 72-55% Pace\n\n"
            f"Bosrun op zacht terrein. Heuvels ok — pas tempo aan (Z2 blijven).\n"
            f"Zachte ondergrond versterkt enkels en voeten.\n"
            f"Kies een mooie route — dit moet de leukste run van de week zijn!\n"
            f"Delahaije: 'Geleidelijke opbouw op zachte ondergrond.'"
            f"{DELAHAIJE_RUN}"
        ),
        "duur_min": duration_min, "tss_geschat": _tss_run(duration_min, 0.75),
        "sport": "Run", "zone": "Z2",
        "intensiteit_factor": 0.75, "fun": 5,
    }


def z2_with_pickups(duration_min: int) -> dict:
    """Z2 met pickups: elke 10 min 30 sec iets sneller. Houdt je scherp."""
    main = max(10, duration_min - 13)
    pickups = max(2, main // 10)
    block = max(5, (main - pickups) // pickups)
    return {
        "type": "z2_pickups", "naam": f"Z2 + pickups – {duration_min} min",
        "beschrijving": (
            f"Warmup\n- 5m ramp 55-78% Pace\n\n"
            f"Main Set\n"
            f"{pickups}x\n"
            f"- {block}m 73% Pace\n"
            f"- 30s 85% Pace\n\n"
            f"Cooldown\n- 3m ramp 73-55% Pace\n\n"
            f"Elke ~10 min een korte 'pickup' van 30 sec iets sneller.\n"
            f"Niet sprinten — vloeiend versnellen, als een surfer op een golf.\n"
            f"Houdt je mentaal scherp tijdens een lange Z2. {REHAB_PRE_RUN}"
            f"{DELAHAIJE_RUN}"
        ),
        "duur_min": duration_min, "tss_geschat": _tss_run(duration_min, 0.76),
        "sport": "Run", "zone": "Z2",
        "intensiteit_factor": 0.76, "fun": 4,
    }


def recovery_run(duration_min: int) -> dict:
    """Herstelrun — bewegen, niet trainen."""
    main = max(10, duration_min - 8)
    return {
        "type": "recovery", "naam": f"Herstelrun – {duration_min} min",
        "beschrijving": (
            f"Warmup\n- 3m ramp 55-68% Pace\n\n"
            f"Main Set\n- {main}m 63% Pace\n\n"
            f"Cooldown\n- 3m ramp 65-55% Pace\n\n"
            f"Herstelrun — het doel is bewegen, niet trainen.\n"
            f"Praten = volledig moeiteloos. Zachte ondergrond.\n"
            f"{REHAB_PRE_RUN}"
            f"{DELAHAIJE_RUN}"
        ),
        "duur_min": duration_min, "tss_geschat": _tss_run(duration_min, 0.65),
        "sport": "Run", "zone": "Z1",
        "intensiteit_factor": 0.65, "fun": 2,
    }


def long_run(km: float) -> dict:
    """Lange duurloop — de belangrijkste training van de week."""
    duration_min = _km_to_min(km, pace=6.0)
    d1 = round(duration_min * 0.12)
    d2 = round(duration_min * 0.45)
    d3 = round(duration_min * 0.35)
    cd = max(5, duration_min - d1 - d2 - d3)
    return {
        "type": "long_run", "naam": f"Lange duurloop – {km:.0f} km",
        "beschrijving": (
            f"Warmup\n- {d1}m ramp 55-75% Pace\n\n"
            f"Main Set\n- {d2}m 68% Pace\n- {d3}m 74% Pace\n\n"
            f"Cooldown\n- {cd}m ramp 73-55% Pace\n\n"
            f"Volume is king (Delahaije). Nooit boven Z2.\n"
            f"Begin bewust rustig. Vlak parcours, zachte ondergrond.\n"
            f"Voeding: drinken elke 20m, gel/fruit na 45m.\n"
            f"Na afloop: 10m stretchen + rehab."
            f"{DELAHAIJE_RUN}"
        ),
        "duur_min": duration_min, "tss_geschat": _tss_run(duration_min, 0.73),
        "sport": "Run", "zone": "Z1/Z2",
        "intensiteit_factor": 0.73, "fun": 4,
    }


def strides(duration_min: int, count: int = 8) -> dict:
    """Z2 met neuromusculaire strides."""
    main = max(10, duration_min - 13)
    return {
        "type": "strides", "naam": f"Z2 + {count}x strides – {duration_min} min",
        "beschrijving": (
            f"Warmup\n- 5m ramp 55-80% Pace\n\n"
            f"Main Set\n- {main}m 75% Pace\n\n"
            f"Neuromusculair\n"
            f"{count}x\n- 20s 95% Pace\n- 1m 60% Pace\n\n"
            f"Cooldown\n- 3m 58% Pace\n\n"
            f"Delahaije: neuromusculaire prikkels verbeteren loopeconomie.\n"
            f"50-100m op ~3km-tempo. Niet sprinten — vloeiend en ontspannen.\n"
            f"Stop direct bij knie- of heupklachten. Gras voor de strides."
            f"{DELAHAIJE_RUN}"
        ),
        "duur_min": duration_min + count + 5,
        "tss_geschat": _tss_run(duration_min, 0.77) + count * 3,
        "sport": "Run", "zone": "Z2 + strides",
        "intensiteit_factor": 0.78, "fun": 4,
    }


def marathon_tempo(tempo_min: int = 25) -> dict:
    """Marathon-specifiek tempowerk."""
    total_min = tempo_min + 30
    return {
        "type": "marathon_tempo", "naam": f"Marathon tempo – {tempo_min} min",
        "beschrijving": (
            f"Warmup\n- 15m ramp 55-78% Pace\n\n"
            f"Main Set\n- {tempo_min}m 82% Pace\n\n"
            f"Cooldown\n- 15m ramp 78-55% Pace\n\n"
            f"'Loop zo hard als je kunt, maar de laatste minuten moeten "
            f"net zo snel zijn als de eerste.' (Delahaije)\n"
            f"Comfortabel hard — praten in korte zinnen."
            f"{DELAHAIJE_RUN}"
        ),
        "duur_min": total_min, "tss_geschat": _tss_run(total_min, 0.82),
        "sport": "Run", "zone": "Z3",
        "intensiteit_factor": 0.82, "fun": 3,
    }


# ═══════════════════════════════════════════════════════════════════════════
# SELECTIE-LOGICA
# ═══════════════════════════════════════════════════════════════════════════

# Z2 run varianten voor rotatie (5 types = elke week anders)
Z2_RUN_VARIANTS = [z2_standard, z2_progression, z2_fartlek, z2_trail, z2_with_pickups]

# Fiets harde sessie varianten voor rotatie (per 3-weken cyclus)
# Elke cyclus-positie (0,1,2) heeft een eigen sessie-type
BIKE_HARD_CYCLE = [
    # (sessie_A, sessie_B) per cycle position
    # cycle 0: threshold + sweetspot
    # cycle 1: over-unders + microbursts of cadence
    # cycle 2: sweetspot + threshold
]


# ═══════════════════════════════════════════════════════════════════════════
# EXTRA FIETS WORKOUTS (meer variatie)
# ═══════════════════════════════════════════════════════════════════════════

def vo2max_short(ftp: int) -> dict:
    """VO2max short-short intervals — 30/30s."""
    return {
        "type": "vo2max", "naam": "VO2max 30/30",
        "beschrijving": (
            "Warm-up\n- 10m 55%\n- 5m ramp 55-75%\n\n"
            "2x\n- 10x\n  - 30s 120%\n  - 30s 50%\n- 5m 50%\n\n"
            "Cool-down\n- 10m 50%"
            f"{DELAHAIJE_BIKE}"
        ),
        "duur_min": 50, "tss_geschat": _tss_bike(50, 0.85),
        "sport": "VirtualRide", "zone": "Z5",
        "intensiteit_factor": 0.85, "fun": 3,
    }


def endurance_tempo_sandwich(ftp: int) -> dict:
    """Endurance met tempo blokken — Z2 met Z3 inserts."""
    return {
        "type": "tempo_sandwich", "naam": "Endurance-Tempo sandwich",
        "beschrijving": (
            "Warm-up\n- 10m 55%\n\n"
            "Main Set\n- 15m 65%\n- 8m 80%\n- 10m 65%\n"
            "- 8m 80%\n- 15m 65%\n\n"
            "Cool-down\n- 10m 50%"
            f"{DELAHAIJE_BIKE}"
        ),
        "duur_min": 76, "tss_geschat": _tss_bike(76, 0.72),
        "sport": "VirtualRide", "zone": "Z2/Z3",
        "intensiteit_factor": 0.72, "fun": 3,
    }


def race_simulation_bike(ftp: int) -> dict:
    """Simulate a race effort — progressive build."""
    return {
        "type": "race_sim", "naam": "Race simulation 40min",
        "beschrijving": (
            "Warm-up\n- 15m ramp 50-70%\n\n"
            "Main Set\n- 10m 85%\n- 10m 90%\n- 10m 95%\n- 10m 100%\n\n"
            "Cool-down\n- 10m 50%"
            f"{DELAHAIJE_BIKE}"
        ),
        "duur_min": 65, "tss_geschat": _tss_bike(65, 0.90),
        "sport": "VirtualRide", "zone": "Z3/Z4",
        "intensiteit_factor": 0.90, "fun": 4,
    }


def tabata_bike(ftp: int) -> dict:
    """Tabata — 20s max effort, 10s rust."""
    return {
        "type": "tabata", "naam": "Tabata 4x",
        "beschrijving": (
            "Warm-up\n- 15m ramp 50-75%\n\n"
            "4x\n- 8x\n  - 20s 170%\n  - 10s 40%\n- 4m 50%\n\n"
            "Cool-down\n- 10m 45%"
            f"{DELAHAIJE_BIKE}"
        ),
        "duur_min": 50, "tss_geschat": _tss_bike(50, 0.88),
        "sport": "VirtualRide", "zone": "Z6",
        "intensiteit_factor": 0.88, "fun": 2,
    }


def recovery_spin(duration_min: int = 30) -> dict:
    """Herstelrit — actief herstel op de fiets."""
    return {
        "type": "recovery_spin", "naam": f"Recovery spin {duration_min}min",
        "beschrijving": (
            f"- {duration_min}m 45-50%\n\n"
            "Geen structuur. Houd het makkelijk. Kadans 85-95."
            f"{DELAHAIJE_BIKE}"
        ),
        "duur_min": duration_min, "tss_geschat": _tss_bike(duration_min, 0.45),
        "sport": "VirtualRide", "zone": "Z1",
        "intensiteit_factor": 0.45, "fun": 2,
    }


# ═══════════════════════════════════════════════════════════════════════════
# EXTRA RUN WORKOUTS (meer variatie)
# ═══════════════════════════════════════════════════════════════════════════

def z2_negative_split(duration_min: int) -> dict:
    """Z2 met bewust negatieve split — tweede helft iets sneller."""
    half = duration_min // 2
    return {
        "type": "z2_negative_split", "naam": f"Z2 negative split – {duration_min}min",
        "beschrijving": (
            f"Warmup\n- 5m ramp 55-68% Pace\n\n"
            f"Main Set\n- {half}m 68% Pace\n- {half - 5}m 73% Pace\n\n"
            f"Cooldown\n- 5m ramp 70-55% Pace\n\n"
            f"Eerste helft bewust rustig. Tweede helft mag iets vlotter.\n"
            f"Niet harder dan Z2 bovengrens."
            f"{DELAHAIJE_RUN}"
        ),
        "duur_min": duration_min, "tss_geschat": _tss_run(duration_min, 0.73),
        "sport": "Run", "zone": "Z2",
        "intensiteit_factor": 0.73, "fun": 3,
    }


def z2_hilly(duration_min: int) -> dict:
    """Z2 met heuvels — zachte stijgingen voor kracht."""
    main = duration_min - 10
    return {
        "type": "z2_hilly", "naam": f"Z2 heuvels – {duration_min}min",
        "beschrijving": (
            f"Warmup\n- 5m ramp 55-68% Pace\n\n"
            f"Main Set\n- {main}m 70% Pace\n\n"
            f"Cooldown\n- 5m ramp 70-55% Pace\n\n"
            f"Kies een heuvelachtig parcours. Loop de heuvels op effort,\n"
            f"niet op pace. Bergaf bewust kort en soepel."
            f"{DELAHAIJE_RUN}"
        ),
        "duur_min": duration_min, "tss_geschat": _tss_run(duration_min, 0.75),
        "sport": "Run", "zone": "Z2",
        "intensiteit_factor": 0.75, "fun": 4,
    }


def z2_treadmill(duration_min: int) -> dict:
    """Z2 op de loopband — voor slecht weer of herstel."""
    main = duration_min - 6
    return {
        "type": "z2_treadmill", "naam": f"Loopband Z2 – {duration_min}min",
        "beschrijving": (
            f"- 3m ramp 55-68% Pace\n"
            f"- {main}m 68% Pace\n"
            f"- 3m ramp 68-55% Pace\n\n"
            f"Loopband: 1% helling voor realistische weerstand.\n"
            f"Serie of podcast erbij."
            f"{DELAHAIJE_RUN}"
        ),
        "duur_min": duration_min, "tss_geschat": _tss_run(duration_min, 0.70),
        "sport": "Run", "zone": "Z2",
        "intensiteit_factor": 0.70, "fun": 2,
    }


def long_run_negative_split(km: float) -> dict:
    """Lange duurloop met bewuste negative split."""
    duration_min = _km_to_min(km, pace=6.0)
    first_half = round(duration_min * 0.55)
    second_half = round(duration_min * 0.35)
    cd = max(5, duration_min - first_half - second_half)
    return {
        "type": "long_run_ns", "naam": f"Lange duurloop negative split – {km:.0f}km",
        "beschrijving": (
            f"Warmup + eerste helft\n- {first_half}m 66% Pace\n\n"
            f"Tweede helft\n- {second_half}m 74% Pace\n\n"
            f"Cooldown\n- {cd}m ramp 73-55% Pace\n\n"
            f"Begin BEWUST te langzaam. Pas na de helft iets opschakelen.\n"
            f"Delahaije: 'Wie de laatste 5km het sterkst loopt, wint.'\n"
            f"Voeding mee."
            f"{DELAHAIJE_RUN}"
        ),
        "duur_min": duration_min, "tss_geschat": _tss_run(duration_min, 0.73),
        "sport": "Run", "zone": "Z1/Z2",
        "intensiteit_factor": 0.73, "fun": 5,
    }


def marathon_pace_segments(duration_min: int = 60) -> dict:
    """Z2 met marathontempo inserts — race-specifiek."""
    return {
        "type": "mp_segments", "naam": f"Z2 + marathontempo – {duration_min}min",
        "beschrijving": (
            f"Warmup\n- 10m ramp 55-68% Pace\n\n"
            f"Main Set\n- 8m 68% Pace\n"
            f"- 5m 80% Pace\n"
            f"- 8m 68% Pace\n"
            f"- 5m 80% Pace\n"
            f"- 8m 68% Pace\n"
            f"- 5m 80% Pace\n\n"
            f"Cooldown\n- 10m ramp 68-55% Pace\n\n"
            f"Marathon pace inserts: moet aanvoelen als 'snel maar duurzaam'.\n"
            f"Als het hijgen is, te hard."
            f"{DELAHAIJE_RUN}"
        ),
        "duur_min": duration_min, "tss_geschat": _tss_run(duration_min, 0.78),
        "sport": "Run", "zone": "Z2/Z3",
        "intensiteit_factor": 0.78, "fun": 4,
    }


def hill_sprints(duration_min: int = 40) -> dict:
    """Korte heuvelsprints — neurommusculair."""
    return {
        "type": "hill_sprints", "naam": f"Heuvelsprints – {duration_min}min",
        "beschrijving": (
            f"Warmup\n- 15m ramp 55-70% Pace\n\n"
            f"Main Set\n"
            f"8x\n- 15s sprint heuvel op\n- 90s easy terug\n\n"
            f"Cooldown\n- 10m 60% Pace\n\n"
            f"Kort en explosief. Geen lactaat, wel kracht en coördinatie.\n"
            f"Steile heuvel (6-10%), focus op kniehef en armzwaai."
            f"{DELAHAIJE_RUN}"
        ),
        "duur_min": duration_min, "tss_geschat": _tss_run(duration_min, 0.75),
        "sport": "Run", "zone": "Z4/Z5",
        "intensiteit_factor": 0.75, "fun": 5,
    }


# ═══════════════════════════════════════════════════════════════════════════
# PARAMETRIC VARIATION FACTORIES — library expansion (2026-04-09)
#
# In plaats van handgeschreven workouts voor elke variant, generators met
# parameters (sets × duur × intensiteit). Elk return een lijst van dicts
# die je direct in get_swap_options kunt pluggen.
#
# Target per type: 25-30 unieke variaties. Samen met de bestaande hand-
# geschreven workouts geeft dat 200+ workouts in de library.
# ═══════════════════════════════════════════════════════════════════════════

def _build_bike_threshold(ftp: int, sets: int, work_min: int, rest_min: int,
                           pct: int, flavor: str = "") -> dict:
    """Bouw één threshold-variant met opgegeven parameters."""
    total_work = sets * work_min
    if_score = (pct / 100) * 0.98  # grofweg: 100% FTP ≈ IF 0.98
    total_dur = 12 + (sets * (work_min + rest_min)) + 8  # WU + main + CD
    naam_extra = f" {flavor}" if flavor else ""
    return {
        "type": "bike_threshold",
        "naam": f"Threshold {sets}x{work_min} min @ {pct}%{naam_extra}",
        "beschrijving": (
            f"Warmup\n- 12m ramp 50-75% 85rpm\n\n"
            f"Main Set\n"
            f"{sets}x\n"
            f"- {work_min}m {pct}% 85rpm\n"
            f"- {rest_min}m 55% 95rpm\n\n"
            f"Cooldown\n- 8m ramp 60-45% 90rpm\n\n"
            f"Threshold variant: {total_work} min totaal werk in {sets} sets van {work_min} min.\n"
            f"Doel FTP-zone (95-105%). Eerste set beheerst, laatste set =\n"
            f"eerste set in tempo. Stop bij fade > 5W tussen intervals."
            f"{DELAHAIJE_BIKE}"
        ),
        "duur_min": total_dur,
        "tss_geschat": _tss_bike(total_dur, if_score),
        "sport": "VirtualRide", "zone": "Z4",
        "intensiteit_factor": if_score, "fun": 3,
    }


def bike_threshold_variants(ftp: int) -> list[dict]:
    """Groot menu van threshold-variaties. ~30 unieke combinaties.

    Alle variaties geldig, met verschillen in volume, intensiteit en
    set-structuur.
    """
    # (sets, work_min, rest_min, pct, flavor)
    combos = [
        # Intro / lage volume
        (2, 8, 3, 95, ""),
        (3, 5, 2, 100, "kort"),
        (3, 6, 2, 98, "kort"),
        (3, 8, 3, 95, ""),
        (3, 8, 3, 97, ""),
        (3, 8, 3, 100, "FTP"),
        (4, 5, 2, 100, "kort"),
        (4, 6, 2, 97, ""),
        (4, 6, 2, 100, "FTP"),
        # Middel volume
        (2, 10, 4, 100, "FTP"),
        (2, 10, 4, 102, "piek"),
        (3, 10, 3, 97, "volume"),
        (3, 10, 3, 100, "FTP"),
        (3, 10, 3, 102, "piek"),
        (4, 8, 3, 98, "volume"),
        (4, 8, 3, 100, "FTP"),
        # Langer volume
        (2, 12, 4, 97, ""),
        (2, 12, 4, 100, "FTP"),
        (2, 12, 4, 102, "piek"),
        (2, 15, 5, 95, "volume"),
        (2, 15, 5, 97, "volume"),
        (3, 12, 4, 95, "groot volume"),
        (3, 12, 4, 97, "groot volume"),
        # Piek / bovengrens
        (3, 6, 3, 105, "piek"),
        (3, 8, 3, 103, "piek"),
        (4, 5, 2, 105, "piek"),
        (5, 4, 2, 105, "piek"),
        (3, 5, 2, 108, "supra"),
        # Extra lange (alleen in opbouw)
        (2, 20, 5, 95, "lang"),
        (3, 15, 5, 95, "lang volume"),
    ]
    return [_build_bike_threshold(ftp, *c) for c in combos]


def _build_bike_sweetspot(ftp: int, sets: int, work_min: int, rest_min: int,
                           pct: int, flavor: str = "") -> dict:
    total_work = sets * work_min
    if_score = (pct / 100) * 0.92
    total_dur = 10 + (sets * (work_min + rest_min)) + 7
    naam_extra = f" {flavor}" if flavor else ""
    return {
        "type": "bike_sweetspot",
        "naam": f"Sweetspot {sets}x{work_min} min @ {pct}%{naam_extra}",
        "beschrijving": (
            f"Warmup\n- 10m ramp 50-75% 90rpm\n\n"
            f"Main Set\n"
            f"{sets}x\n"
            f"- {work_min}m {pct}% 88rpm\n"
            f"- {rest_min}m 60% 95rpm\n\n"
            f"Cooldown\n- 7m ramp 60-45% 90rpm\n\n"
            f"Sweetspot: 'comfortabel oncomfortabel' (88-93% FTP).\n"
            f"{total_work} min totaal. Je moet nog kunnen praten, maar je wilt het niet.\n"
            f"Als ademhaling op 'hijgen' schiet, zit je te hoog."
            f"{DELAHAIJE_BIKE}"
        ),
        "duur_min": total_dur,
        "tss_geschat": _tss_bike(total_dur, if_score),
        "sport": "VirtualRide", "zone": "Z3/Z4",
        "intensiteit_factor": if_score, "fun": 3,
    }


def bike_sweetspot_variants(ftp: int) -> list[dict]:
    """Groot menu van sweetspot-variaties. ~25 combinaties."""
    combos = [
        # Kort, intro
        (2, 10, 3, 88, ""),
        (2, 10, 3, 90, ""),
        (2, 12, 3, 88, ""),
        (2, 12, 3, 90, ""),
        (3, 8, 2, 90, ""),
        (3, 8, 2, 92, ""),
        (3, 10, 3, 88, ""),
        (3, 10, 3, 90, ""),
        (3, 10, 3, 92, ""),
        # Middel
        (2, 15, 4, 88, "standaard"),
        (2, 15, 4, 90, "standaard"),
        (2, 15, 4, 92, "bovengrens"),
        (2, 18, 4, 88, ""),
        (3, 12, 3, 88, ""),
        (3, 12, 3, 90, ""),
        (3, 12, 4, 92, "bovengrens"),
        # Lang volume
        (2, 20, 5, 88, "lang"),
        (2, 20, 5, 90, "lang"),
        (3, 15, 4, 88, "groot volume"),
        (3, 15, 4, 90, "groot volume"),
        (2, 25, 5, 88, "extra lang"),
        (3, 18, 5, 88, "groot volume"),
        # Piramides
        (4, 10, 2, 90, "piramide"),
        (4, 12, 3, 88, "piramide"),
        (5, 8, 2, 90, "piramide"),
    ]
    return [_build_bike_sweetspot(ftp, *c) for c in combos]


def _build_bike_over_unders(ftp: int, sets: int, over_sec: int, under_sec: int,
                              cycles: int, over_pct: int, under_pct: int) -> dict:
    cycle_dur = (over_sec + under_sec) * cycles / 60  # min per set
    rest_min = 4
    total_dur = 12 + sets * (cycle_dur + rest_min) + 8
    if_score = 0.92  # grof
    return {
        "type": "bike_over_unders",
        "naam": f"Over-unders {sets}x{cycles}x({over_sec}s/{under_sec}s)",
        "beschrijving": (
            f"Warmup\n- 12m ramp 50-75% 90rpm\n\n"
            f"Main Set\n"
            f"{sets}x\n"
            + "\n".join([f"- {over_sec}s {over_pct}% 90rpm\n- {under_sec}s {under_pct}% 90rpm" for _ in range(cycles)])
            + f"\n- {rest_min}m 55% 95rpm\n\n"
            f"Cooldown\n- 8m ramp 60-45% 90rpm\n\n"
            f"Over-unders: over-fase = boven FTP ({over_pct}%), under-fase = net onder ({under_pct}%).\n"
            f"Under-fase voelt onaangenaam maar is het trainingsdoel: lactaat opruimen onder belasting.\n"
            f"Als de under-fase te makkelijk voelt, de over-fase te hard."
            f"{DELAHAIJE_BIKE}"
        ),
        "duur_min": round(total_dur),
        "tss_geschat": _tss_bike(round(total_dur), if_score),
        "sport": "VirtualRide", "zone": "Z4",
        "intensiteit_factor": if_score, "fun": 2,
    }


def bike_over_under_variants(ftp: int) -> list[dict]:
    """Over-unders menu. ~15 combinaties."""
    combos = [
        # (sets, over_sec, under_sec, cycles, over_pct, under_pct)
        (2, 30, 30, 6, 105, 88),
        (2, 30, 30, 8, 105, 88),
        (3, 30, 30, 5, 105, 88),
        (3, 30, 30, 6, 105, 88),
        (2, 40, 40, 5, 105, 88),
        (2, 40, 40, 6, 105, 88),
        (3, 40, 40, 5, 105, 88),
        (2, 60, 60, 4, 103, 90),
        (2, 60, 60, 5, 103, 90),
        (3, 60, 60, 4, 103, 90),
        (2, 60, 90, 4, 108, 85),
        (2, 45, 75, 5, 108, 85),
        (3, 30, 60, 5, 110, 85),
        (2, 90, 60, 4, 103, 88),
        (3, 30, 30, 8, 108, 85),
    ]
    return [_build_bike_over_unders(ftp, *c) for c in combos]


def _build_bike_vo2max(ftp: int, sets: int, work_sec: int, rest_sec: int,
                        pct: int) -> dict:
    total_work_min = (sets * work_sec) / 60
    total_dur = 15 + sets * (work_sec + rest_sec) / 60 + 10
    if_score = 0.95
    return {
        "type": "bike_vo2max",
        "naam": f"VO2max {sets}x{work_sec}s @ {pct}%",
        "beschrijving": (
            f"Warmup\n- 15m ramp 50-75% 90rpm\n\n"
            f"Main Set\n"
            f"{sets}x\n"
            f"- {work_sec}s {pct}% 95rpm\n"
            f"- {rest_sec}s 55% 90rpm\n\n"
            f"Cooldown\n- 10m ramp 60-45% 90rpm\n\n"
            f"VO2max intervals. {total_work_min:.1f} min totaal op hoge intensiteit.\n"
            f"Doel: maximale zuurstofopname. Je moet aan het eind echt afhappen.\n"
            f"Niet meer dan 1x/week in deze fase."
            f"{DELAHAIJE_BIKE}"
        ),
        "duur_min": round(total_dur),
        "tss_geschat": _tss_bike(round(total_dur), if_score),
        "sport": "VirtualRide", "zone": "Z5",
        "intensiteit_factor": if_score, "fun": 1,
    }


def bike_vo2max_variants(ftp: int) -> list[dict]:
    """VO2max menu. ~12 combinaties."""
    combos = [
        (4, 30, 30, 120),   # 30/30's
        (5, 30, 30, 120),
        (6, 30, 30, 118),
        (8, 30, 30, 115),
        (10, 30, 30, 115),
        (5, 40, 40, 115),
        (6, 40, 40, 115),
        (4, 60, 60, 115),   # 1/1's
        (5, 60, 60, 115),
        (6, 60, 60, 112),
        (4, 120, 120, 112), # 2/2's
        (5, 180, 180, 108), # 3/3's
        (4, 240, 240, 108), # 4/4's
    ]
    return [_build_bike_vo2max(ftp, *c) for c in combos]


def _build_bike_endurance(duration_min: int, avg_pct: int, pattern: str = "rolling") -> dict:
    main = duration_min - 15
    if pattern == "rolling":
        seg = main // 6
        rest = main - seg * 6
        blocks = (
            f"- {seg}m {avg_pct - 5}% 90rpm\n"
            f"- {seg}m ramp {avg_pct - 5}-{avg_pct + 5}% 85rpm\n"
            f"- {seg}m {avg_pct}% 80rpm\n"
            f"- {seg}m {avg_pct - 10}% 95rpm\n"
            f"- {seg}m ramp {avg_pct - 5}-{avg_pct + 3}% 85rpm\n"
            f"- {seg + rest}m {avg_pct - 2}% 90rpm"
        )
        desc = "Rolling terrain: wisselend terrein alsof je buiten fietst."
    elif pattern == "steady":
        blocks = f"- {main}m {avg_pct}% 90rpm"
        desc = "Steady state — één vermogen, geen wisselingen. Meditatief."
    elif pattern == "progressive":
        seg = main // 3
        rest = main - seg * 3
        blocks = (
            f"- {seg}m {avg_pct - 8}% 88rpm\n"
            f"- {seg}m {avg_pct - 2}% 88rpm\n"
            f"- {seg + rest}m {avg_pct + 4}% 88rpm"
        )
        desc = "Progressief: elke tertsie iets hoger vermogen. Eindigt strak in Z2-bovengrens."
    else:  # negative_split
        half = main // 2
        blocks = (
            f"- {half}m {avg_pct - 6}% 90rpm\n"
            f"- {main - half}m {avg_pct + 4}% 88rpm"
        )
        desc = "Negative split: eerste helft rustig, tweede helft iets actiever."
    if_score = avg_pct / 100
    return {
        "type": "bike_endurance",
        "naam": f"Duurrit {pattern} Z2 – {duration_min} min",
        "beschrijving": (
            f"Warmup\n- 8m ramp 45-{avg_pct - 3}% 85rpm\n\n"
            f"Main Set\n{blocks}\n\n\n"
            f"Cooldown\n- 7m ramp {avg_pct - 8}-45%\n\n"
            f"{desc}\nHoudt alles binnen Z2. Kadans varieert mee."
            f"{DELAHAIJE_BIKE}"
        ),
        "duur_min": duration_min,
        "tss_geschat": _tss_bike(duration_min, if_score),
        "sport": "VirtualRide", "zone": "Z2",
        "intensiteit_factor": if_score, "fun": 3,
    }


def bike_endurance_variants(duration_min: int) -> list[dict]:
    """Endurance bike menu. ~20 combinaties (4 patronen × 5 lengtes)."""
    durations = [duration_min, max(45, duration_min - 15), max(60, duration_min - 5),
                 min(150, duration_min + 15), min(180, duration_min + 30)]
    patterns = ["rolling", "steady", "progressive", "negative_split"]
    avg_pcts = [63, 65, 68, 70]  # verschillende Z2-niveaus
    variants = []
    for d in durations:
        for p in patterns:
            for pct in avg_pcts[:2]:  # niet alle combinaties = te veel
                variants.append(_build_bike_endurance(d, pct, p))
    return variants


# ─── RUN VARIATIONS ─────────────────────────────────────────────────────

def _build_run_tempo(sets: int, work_min: int, rest_min: int, pct: int,
                      flavor: str = "") -> dict:
    total_work = sets * work_min
    total_dur = 12 + sets * (work_min + rest_min) + 10
    if_score = pct / 100 * 0.95
    naam_extra = f" {flavor}" if flavor else ""
    return {
        "type": "run_tempo",
        "naam": f"Tempo {sets}x{work_min} min @ {pct}%{naam_extra}",
        "beschrijving": (
            f"Warmup\n- 12m ramp 55-75% Pace\n\n"
            f"Main Set\n"
            f"{sets}x\n"
            f"- {work_min}m {pct}% Pace\n"
            f"- {rest_min}m 65% Pace\n\n"
            f"Cooldown\n- 10m ramp 70-55% Pace\n\n"
            f"Drempelwerk: {total_work} min totaal op drempel-intensiteit.\n"
            f"Je kunt nog net praten maar je wilt het niet. Stabiel tempo is\n"
            f"belangrijker dan snel tempo. {REHAB_PRE_RUN}"
            f"{DELAHAIJE_RUN}"
        ),
        "duur_min": total_dur,
        "tss_geschat": _tss_run(total_dur, if_score),
        "sport": "Run", "zone": "Z3",
        "intensiteit_factor": if_score, "fun": 3,
    }


def run_tempo_variants() -> list[dict]:
    """Run tempo/threshold menu. ~25 combinaties. Allemaal hele minuten."""
    combos = [
        # (sets, work_min, rest_min, pct, flavor)
        # Cruise intervals (kort, 3-5 min)
        (3, 5, 2, 85, "cruise"),
        (4, 5, 2, 85, "cruise"),
        (5, 5, 2, 85, "cruise"),
        (6, 4, 2, 87, "cruise"),
        (8, 3, 1, 88, "cruise"),
        # Klassieke tempo blokken
        (2, 8, 3, 83, "tempo"),
        (2, 10, 3, 82, "tempo"),
        (2, 12, 4, 82, "tempo"),
        (3, 8, 3, 82, "tempo"),
        (3, 10, 3, 82, "tempo"),
        # Lange tempo
        (1, 20, 1, 82, "lang"),
        (1, 25, 1, 81, "lang"),
        (1, 30, 1, 80, "lang"),
        (2, 15, 5, 82, "lang"),
        # Progressief
        (3, 8, 2, 83, "progressief"),
        (3, 6, 2, 85, "progressief"),
        # Marathon pace
        (2, 15, 5, 80, "marathon pace"),
        (3, 10, 3, 80, "marathon pace"),
        (2, 20, 5, 79, "marathon pace"),
        (1, 30, 1, 79, "marathon pace"),
        # Variaties (piek)
        (4, 6, 2, 85, "variatie"),
        (5, 4, 2, 87, "piek"),
        (6, 3, 1, 88, "piek"),
        (3, 12, 4, 82, "volume"),
        (4, 10, 3, 82, "groot volume"),
    ]
    return [_build_run_tempo(*c) for c in combos]


def _fmt_interval_duration(seconds: int) -> str:
    """Format interval duration: < 60s → '30s', ≥ 60s whole minutes → '2m', else '90s'."""
    if seconds < 60:
        return f"{seconds}s"
    if seconds % 60 == 0:
        return f"{seconds // 60}m"
    return f"{seconds}s"


def _build_run_intervals(count: int, work_sec: int, rest_sec: int, pct: int,
                           flavor: str = "") -> dict:
    total_work_min = (count * work_sec) / 60
    total_dur = 12 + round((count * (work_sec + rest_sec)) / 60) + 10
    if_score = pct / 100 * 0.95
    naam_extra = f" {flavor}" if flavor else ""
    work_str = _fmt_interval_duration(work_sec)
    rest_str = _fmt_interval_duration(rest_sec)
    return {
        "type": "run_intervals",
        "naam": f"Intervals {count}x{work_str} @ {pct}%{naam_extra}",
        "beschrijving": (
            f"Warmup\n- 12m ramp 55-78% Pace\n\n"
            f"Main Set\n"
            f"{count}x\n"
            f"- {work_str} {pct}% Pace\n"
            f"- {rest_str} 60% Pace (jog of wandelen)\n\n"
            f"Cooldown\n- 10m ramp 70-55% Pace\n\n"
            f"Interval training: {total_work_min:.0f} min totaal op hoge intensiteit.\n"
            f"Laatste interval moet even snel zijn als de eerste (Delahaije).\n"
            f"Stop direct bij knieklachten. Zachte ondergrond. {REHAB_PRE_RUN}"
            f"{DELAHAIJE_RUN}"
        ),
        "duur_min": total_dur,
        "tss_geschat": _tss_run(total_dur, if_score),
        "sport": "Run", "zone": "Z4/Z5",
        "intensiteit_factor": if_score, "fun": 3,
    }


def run_interval_variants() -> list[dict]:
    """Run intervals menu. ~20 combinaties. Werkt in SECONDEN."""
    # (count, work_sec, rest_sec, pct, flavor)
    combos = [
        # 10km pace intervals (3-5 min blokken)
        (5, 180, 120, 90, "10km pace"),
        (6, 180, 120, 90, "10km pace"),
        (7, 180, 120, 90, "10km pace"),
        (8, 180, 90, 92, "10km pace"),
        (4, 240, 120, 90, "10km pace"),
        (5, 240, 120, 90, "10km pace"),
        (6, 240, 120, 88, "10km pace"),
        (3, 300, 180, 88, "lange intervals"),
        (4, 300, 180, 88, "lange intervals"),
        (5, 300, 120, 88, "lange intervals"),
        # Korte snelle intervals (5k pace)
        (8, 120, 90, 92, "5km pace"),
        (10, 120, 60, 93, "5km pace"),
        (12, 90, 60, 95, "snelle"),
        (15, 60, 60, 95, "snelle"),
        # 1500m-style
        (6, 90, 90, 95, "1500m"),
        (8, 90, 90, 93, "1500m"),
        # Piramide (samengevat)
        (5, 180, 90, 90, "piramide"),
        (7, 120, 60, 93, "piramide kort"),
        # Yasso 800s (3 min per rep)
        (6, 180, 180, 88, "Yasso"),
        (8, 180, 180, 87, "Yasso"),
        (10, 180, 180, 87, "Yasso"),
    ]
    return [_build_run_intervals(*c) for c in combos]


def _build_run_z2(duration_min: int, avg_pct: int, style: str) -> dict:
    main = duration_min - 8
    if style == "steady":
        blocks = f"- {main}m {avg_pct}% Pace"
        desc = "Steady state: één tempo, geen variatie. Mediteren op ritme."
        fun = 2
    elif style == "rolling":
        seg = max(5, main // 4)
        rest = main - seg * 4
        blocks = (
            f"- {seg}m {avg_pct - 3}% Pace\n"
            f"- {seg}m {avg_pct + 2}% Pace\n"
            f"- {seg}m {avg_pct}% Pace\n"
            f"- {seg + rest}m {avg_pct + 1}% Pace"
        )
        desc = "Rolling: subtiele tempowisselingen binnen Z2."
        fun = 3
    elif style == "fartlek":
        seg = max(5, main // 6)
        rest = main - seg * 6
        blocks = (
            f"6x\n- {seg}m {avg_pct - 3}% Pace\n- 30s {avg_pct + 10}% Pace\n"
            + (f"\n- {rest}m {avg_pct}% Pace" if rest > 0 else "")
        )
        desc = "Fartlek: 6 korte versnellingen tussen Z2-blokken. Speels."
        fun = 5
    elif style == "progression":
        third = main // 3
        rest = main - third * 3
        blocks = (
            f"- {third}m {avg_pct - 5}% Pace\n"
            f"- {third}m {avg_pct}% Pace\n"
            f"- {third + rest}m {avg_pct + 5}% Pace"
        )
        desc = "Progression: elke derde iets sneller. Eindigt bij Z2-top."
        fun = 4
    else:  # negative_split
        half = main // 2
        blocks = (
            f"- {half}m {avg_pct - 4}% Pace\n"
            f"- {main - half}m {avg_pct + 3}% Pace"
        )
        desc = "Negative split: tweede helft iets sneller. Beheersing is key."
        fun = 3
    if_score = avg_pct / 100 * 0.75
    return {
        "type": f"run_z2_{style}",
        "naam": f"Z2 {style} – {duration_min}min",
        "beschrijving": (
            f"Warmup\n- 4m ramp 55-{avg_pct - 2}% Pace\n\n"
            f"Main Set\n{blocks}\n\n"
            f"Cooldown\n- 4m ramp {avg_pct - 5}-55% Pace\n\n"
            f"{desc}\n{REHAB_PRE_RUN}"
            f"{DELAHAIJE_RUN}"
        ),
        "duur_min": duration_min,
        "tss_geschat": _tss_run(duration_min, if_score),
        "sport": "Run", "zone": "Z2",
        "intensiteit_factor": if_score, "fun": fun,
    }


def run_z2_variants(duration_min: int) -> list[dict]:
    """Z2 run menu. ~25 combinaties (5 styles × 5 lengtes × 2 intensiteiten)."""
    durations = [duration_min,
                 max(25, duration_min - 10),
                 max(40, duration_min - 5),
                 duration_min + 10,
                 duration_min + 20]
    styles = ["steady", "rolling", "fartlek", "progression", "negative_split"]
    variants = []
    seen_names = set()
    for d in durations:
        for s in styles:
            # Twee intensiteitsniveaus (onderkant Z2 / bovenkant Z2)
            for pct in [68, 75]:
                v = _build_run_z2(d, pct, s)
                if v["naam"] not in seen_names:
                    seen_names.add(v["naam"])
                    variants.append(v)
    return variants


def run_easy_variants(duration_min: int) -> list[dict]:
    """Easy/recovery run menu. ~10 combinaties."""
    out = []
    for d in [max(20, duration_min - 15), max(25, duration_min - 10),
              max(30, duration_min - 5), duration_min]:
        out.append(recovery_run(d))
        # Easy aerobic (tussen recovery en echte Z2)
        main = d - 8
        out.append({
            "type": "easy_aerobic",
            "naam": f"Easy aerobic – {d}min",
            "beschrijving": (
                f"Warmup\n- 4m ramp 55-66% Pace\n\n"
                f"Main Set\n- {main}m 66% Pace\n\n"
                f"Cooldown\n- 4m ramp 66-55% Pace\n\n"
                f"Onderkant Z2. Moet aanvoelen als 'ik zou dit uren kunnen'.\n"
                f"{REHAB_PRE_RUN}"
                f"{DELAHAIJE_RUN}"
            ),
            "duur_min": d, "tss_geschat": _tss_run(d, 0.68),
            "sport": "Run", "zone": "Z1/Z2",
            "intensiteit_factor": 0.68, "fun": 2,
        })
    return out


# ═══════════════════════════════════════════════════════════════════════════
# SWAP CATEGORIES — voor de smart swap functie
# ═══════════════════════════════════════════════════════════════════════════

SWAP_CATEGORIES = {
    "makkelijker": {
        "label": "Rustiger",
        "description": "Minder intensief, meer herstel",
    },
    "vergelijkbaar": {
        "label": "Zelfde type",
        "description": "Andere variant, zelfde belasting",
    },
    "anders": {
        "label": "Iets anders",
        "description": "Ander type workout, frisse prikkel",
    },
    "harder": {
        "label": "Meer uitdaging",
        "description": "Een tandje zwaarder",
    },
}


def get_swap_options(event: dict, category: str, ftp: int = 290) -> list[dict]:
    """Geef swap-opties voor een event in een bepaalde categorie.

    Args:
        event: Het huidige event
        category: "makkelijker", "vergelijkbaar", "anders", "harder"
        ftp: FTP in watt

    Returns:
        Lijst van workout dicts, automatisch gesorteerd op beste match
    """
    e_type = event.get("type", "")
    e_name = (event.get("name") or "").lower()
    is_bike = e_type in ("Ride", "VirtualRide")
    is_run = e_type == "Run"

    # Detecteer duur
    dur = 45
    for p in e_name.replace("min", " ").split():
        try:
            dur = int(p)
            break
        except ValueError:
            pass

    options = []

    if is_bike:
        if category == "makkelijker":
            # Herstelritten + coffee rides in verschillende lengtes
            options = [
                recovery_spin(20), recovery_spin(30), recovery_spin(40),
                single_leg_drills(ftp),
                cadence_pyramids(ftp),
            ]
            # Plus een paar lichtere endurance rides
            options.extend(bike_endurance_variants(max(45, dur - 15))[:6])
        elif category == "vergelijkbaar":
            if "threshold" in e_name:
                # Grote pool threshold varianten
                options = bike_threshold_variants(ftp)
            elif "sweetspot" in e_name:
                options = bike_sweetspot_variants(ftp)
            elif "over-under" in e_name:
                options = bike_over_under_variants(ftp)
            elif "vo2" in e_name or "tabata" in e_name or "microburst" in e_name:
                options = bike_vo2max_variants(ftp)
            else:
                # Endurance → andere endurance variaties
                options = bike_endurance_variants(dur)
        elif category == "anders":
            # Ander type workout — mix van alles
            options = []
            options.extend(bike_sweetspot_variants(ftp)[:6])
            options.extend(bike_over_under_variants(ftp)[:4])
            options.append(cadence_pyramids(ftp))
            options.append(microbursts(ftp))
            options.append(single_leg_drills(ftp))
            options.append(endurance_tempo_sandwich(ftp))
        elif category == "harder":
            # Zware opties: threshold high-end, VO2max, race sim
            options = []
            options.extend(bike_threshold_variants(ftp)[-10:])  # de zwaarste
            options.extend(bike_vo2max_variants(ftp))
            options.append(race_simulation_bike(ftp))
            options.append(tabata_bike(ftp))

    elif is_run:
        if category == "makkelijker":
            options = run_easy_variants(dur)
            options.append(z2_treadmill(dur))
        elif category == "vergelijkbaar":
            # Classificeer op huidige workout
            if any(k in e_name for k in ["interval", "tempo", "threshold", "cruise", "yasso"]):
                # Zelfde type: tempo/interval varianten
                options = run_tempo_variants() + run_interval_variants()
            elif any(k in e_name for k in ["lange duurloop", "long run"]):
                # Zelfde type: long run varianten
                options = [
                    long_run(15), long_run(16), long_run(18), long_run(20),
                    long_run(22), long_run(24),
                    long_run_negative_split(18), long_run_negative_split(20),
                    long_run_negative_split(22),
                ]
            else:
                # Z2 variant gevraagd
                options = run_z2_variants(dur)
        elif category == "anders":
            # Mix: heuvels, strides, fartlek, pickups
            options = []
            options.extend(run_z2_variants(dur)[:8])
            options.append(hill_sprints(dur))
            options.append(strides(dur, 6))
            options.append(strides(dur, 8))
            options.append(strides(dur, 10))
            options.extend(run_tempo_variants()[:5])
        elif category == "harder":
            options = run_tempo_variants() + run_interval_variants()
            options.append(marathon_pace_segments(dur))
            options.append(marathon_pace_segments(dur + 15))

    # Filter: niet dezelfde als huidige workout
    filtered = [o for o in options if o["naam"].lower() != e_name]
    # Randomiseer volgorde zodat elke swap-klik een frisse selectie geeft
    import random as _rnd
    _rnd.shuffle(filtered)
    return filtered[:15]


def pick_z2_run(duration_min: int, variety_index: int) -> dict:
    """Selecteer een Z2 run-variant op basis van de variatie-index."""
    idx = variety_index % len(Z2_RUN_VARIANTS)
    return Z2_RUN_VARIANTS[idx](duration_min)


def pick_bike_hard(ftp: int, cycle: int, slot: str,
                   t_step: int, ss_step: int, ou_step: int) -> dict:
    """
    Selecteer een harde fietssessie op basis van cyclus en slot.

    cycle: 0, 1, 2 (3-weken rotatie)
    slot: 'A' (eerste harde sessie) of 'B' (tweede harde sessie)
    """
    if cycle == 0:
        return threshold(ftp, t_step) if slot == "A" else sweetspot(ftp, ss_step)
    elif cycle == 1:
        if slot == "A":
            return over_unders(ftp, ou_step)
        else:
            # Afwisselen: oneven weken cadence, even weken microbursts
            return cadence_pyramids(ftp) if t_step % 2 == 1 else microbursts(ftp)
    else:
        return sweetspot(ftp, ss_step) if slot == "A" else threshold(ftp, t_step)


def pick_bike_easy(duration_min: int, variety_index: int) -> dict:
    """Selecteer een makkelijke fietssessie met variatie."""
    idx = variety_index % 4
    if idx == 0:
        return endurance_ride(duration_min)
    elif idx == 1:
        return zwift_group_ride(duration_min)
    elif idx == 2:
        return single_leg_drills(250)  # ftp doesn't matter for this one
    else:
        return endurance_ride(duration_min)
