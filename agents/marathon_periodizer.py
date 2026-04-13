"""
Marathon Periodizer — beheerst de langetermijn-fasering voor de Amsterdam Marathon.

Amsterdam Marathon: 18 oktober 2026 (~28 weken vanaf 6 april 2026)
Atleet: Dylsky (i85836), terugkeer uit gluteus medius blessure.

Fasering gebaseerd op Louis Delahaije's blokperiodisering (Issurin):
  Accumulatie → Transformatie → Realisatie, cyclisch herhaald.

Delahaije kernprincipes:
- Accumulatie = 100% Zone 1. Geen intervallen, geen drempelwerk.
  Tempoduurloop (85% HRmax) valt NOG STEEDS onder Z1 (onder aerobe drempel).
- "Volume triumphs quality all the time!" — uren, niet kilometers.
- 90/10 verdeling (alleen in transformatie): 90% Z1, 10% Z3.
  Het grijze middengebied (Z2 tussen aerobe en anaerobe drempel) vermijden.
- Fiets = strategisch voordeel, niet concessie. Match tijd + hartslagzone.
- Microritme: 3:1:2:1 (3 belasting, 1 licht, 2 belasting, 1 rust).
- Mesostructuur: 2:1 (blessureherstel) → 3:1 (later).
- Herstelblokken: 3-4 dagen, niet een volle week.

Fysio-constraint bij start:
- 3x per week hardlopen, start op 6 km per sessie
- Elke week +1 km per sessie
- Uitsluitend Z1 hardlopen totdat Injury Guard groen licht geeft
"""

from datetime import date, timedelta

RACE_DATE = date(2026, 10, 18)
PLAN_START = date(2026, 4, 6)  # maandag van week 1 (na deload week)

# ── FASE DEFINITIES (Delahaije blokperiodisering) ─────────────────────────

# ── RUN-PROGRESSIE TABEL (wk 1–12) ────────────────────────────────────────
# Onderhandelde tabel met Dylsky: reflecteert werkelijke status (21 km/wk baseline).
# Vorm: (run_km_totaal, run_sessies, lange_duurloop_km, is_recovery)
RUN_PROGRESSION_TABLE = {
    # Long run is nu structureel ~40% van week zodat 'long' ook écht lang is
    # (was bug: long == korte sessie). Korte runs schalen mee.
    1:  (21, 3,  9, False),    # 6 + 6 + 9
    2:  (24, 3, 10, False),    # 7 + 7 + 10
    3:  (27, 3, 12, False),    # benchmark: vanaf hier +15% cap | 7.5 + 7.5 + 12
    4:  (19, 3,  8, True),     # deload | 5.5 + 5.5 + 8
    5:  (31, 3, 14, False),    # 8.5 + 8.5 + 14
    6:  (36, 3, 16, False),    # 10 + 10 + 16
    7:  (41, 3, 18, False),    # crosses 40 km → 4e run trigger | 11.5 + 11.5 + 18
    8:  (29, 3, 12, True),     # deload | 8.5 + 8.5 + 12
    9:  (47, 4, 20, False),    # 4e run ingevoerd | 9 + 9 + 9 + 20
    10: (54, 4, 22, False),    # 10.5 + 10.5 + 10.5 + 22
    11: (58, 4, 24, False),    # 11 + 11 + 11 + 24 (long ~41%)
    12: (40, 4, 16, True),     # deload | 8 + 8 + 8 + 16
}

# ── RUN-INTENSITEIT GATING (per week, voor endurance_coach) ───────────────
# "geen"      = puur Z1
# "strides"   = Z1 + 4–6× 80m strides
# "tempoduur" = Z1 + tempoduurloop (85% HRmax, nog onder aerobe drempel)
# "drempel"   = vanaf wk 13+ drempelwerk @ 4:20/km startpace
RUN_INTENSITEIT_GATING = {
    1:  "geen",
    2:  "geen",
    3:  "geen",
    4:  "geen",
    5:  "strides",
    6:  "strides",
    7:  "tempoduur",
    8:  "strides",
    9:  "tempoduur",
    10: "tempoduur",
    11: "tempoduur",
    12: "strides",
    # wk 13+ → drempel (start @ 4:20/km) — ingevuld in PHASES.run_intensiteit_gating
}

# ── BIKE-TOOLKIT CATALOGUS ─────────────────────────────────────────────────
# Threshold = vast anker in ELKE week, ALLE fases. 2e/3e slot rouleert.
# TSS-waarden gebumped na bike_coach high-Z2 fatmax + cadens-variatie long_slow.
BIKE_TOOLKIT_TSS = {
    "threshold":       95,   # 75–90 min @ FTP (2×20 of 3×15)
    "fatmax_medium":   75,   # 80 min high Z2 (70–78% FTP, IF 0.74)
    "fatmax_lang":    115,   # 135 min high Z2 met blokken (IF 0.72)
    "long_slow":      120,   # 165 min Z1-dominant met cadens-variatie (IF 0.66)
    "cp_intervals":    90,   # critical-power, start 5×3 @ 115% FTP
    "easy_spin":       55,   # 60–75 min Z1 herstel
}

# ── WEEKLY TSS PROGRESSIE TABEL (wk 1–12) ─────────────────────────────────
# Onderhandelde tabel met Dylsky: TSS-doel per week, drijft load_manager.
# Build-target: CTL +1–2/week zonder fatigue-spike. Reflecteert echte bike-volume
# (~7:30u/wk in build) + run-progressie + 3:1 meso-ritme.
WEEKLY_TSS_TABLE = {
    1:  475,   # 21 km run + 7:30u bike toolkit
    2:  510,   # 24 km + threshold + fatmax_medium + fatmax_lang
    3:  660,   # 27 km + threshold + fatmax_lang + cp_intro + long_slow
    4:  290,   # deload −40%
    5:  680,   # 31 km + cp_intervals + fatmax_medium
    6:  720,   # 36 km + fatmax_lang
    7:  750,   # 41 km + cp_intervals (piek pre-deload)
    8:  340,   # deload
    9:  760,   # 47 km / 4 runs + cp_intervals
    10: 800,
    11: 810,
    12: 530,   # deload
}


PHASES = [
    # ── ACCUMULATIE CYCLUS 1: herstel + aerobe basis ──
    {
        "naam": "accumulatie_I",
        "label": "Accumulatie I — Herstel & Basis",
        "weken": (1, 7),
        "beschrijving": (
            "Terugkeer uit blessure, 21 → 41 km/wk in 3 runs. Threshold-anker op "
            "de fiets + fatmax/long_slow roulerend. Strides vanaf wk 5, tempoduur "
            "vanaf wk 7."
        ),
        "run_sessies_per_week": 3,
        "fiets_sessies_per_week": 3,
        "lange_duurloop": True,      # al vanaf wk 1 (7 km)
        "intensiteit_run": "geen",   # gating per week — zie RUN_INTENSITEIT_GATING
        "intensiteit_fiets": "toolkit",
        "bike_toolkit": ["threshold", "fatmax_medium", "fatmax_lang",
                          "threshold", "cp_intervals", "long_slow", "threshold"],
        "ctl_doel": (43, 55),
        "tss_doel": (400, 550),
        "meso_ritme": "2:1",
        "micro_ritme": "3:1:2:1",
    },
    # ── ACCUMULATIE CYCLUS 2: volume opbouwen ──
    {
        "naam": "accumulatie_II",
        "label": "Accumulatie II — Volume",
        "weken": (8, 14),
        "beschrijving": (
            "4e run vanaf wk 9 (47 km). Lange duurloop naar 17 km. Threshold-anker "
            "blijft, CP-intervallen 1×/2–3 wk. Tempoduur sleutelsessie."
        ),
        "run_sessies_per_week": 4,
        "fiets_sessies_per_week": 3,
        "lange_duurloop": True,
        "long_run_km_start": 14,
        "long_run_km_increment": 1.5,
        "intensiteit_run": "tempoduur_strides",
        "intensiteit_fiets": "toolkit",
        "bike_toolkit": ["threshold", "fatmax_lang", "cp_intervals",
                          "threshold", "long_slow", "fatmax_medium", "threshold"],
        "ctl_doel": (55, 68),
        "tss_doel": (475, 625),
        "meso_ritme": "3:1",
        "micro_ritme": "3:1:2:1",
    },
    # ── TRANSFORMATIE CYCLUS 1: intensiteit introduceren ──
    {
        "naam": "transformatie_I",
        "label": "Transformatie I — Scherpte",
        "weken": (15, 18),
        "beschrijving": (
            "Drempelwerk op de loop vanaf wk 13+ (@ 4:20/km). 90/10 verdeling. "
            "Op de fiets: threshold + CP + marathon-pace blokken."
        ),
        "run_sessies_per_week": 5,
        "fiets_sessies_per_week": 2,
        "lange_duurloop": True,
        "long_run_km_start": 25,
        "long_run_km_increment": 1,
        "intensiteit_run": "marathon_tempo",
        "intensiteit_fiets": "toolkit",
        "bike_toolkit": ["threshold", "cp_intervals", "fatmax_medium", "threshold"],
        "ctl_doel": (68, 78),
        "tss_doel": (550, 700),
        "meso_ritme": "3:1",
        "micro_ritme": "3:1:2:1",
    },
    # ── ACCUMULATIE CYCLUS 3: piekvolume ──
    {
        "naam": "accumulatie_III",
        "label": "Accumulatie III — Piekvolume",
        "weken": (19, 22),
        "beschrijving": (
            "Terug naar Z1-dominantie, maar hoger volume. Langste duurlopen. "
            "Threshold-anker blijft, CP-intervallen elke 2 weken."
        ),
        "run_sessies_per_week": 5,
        "fiets_sessies_per_week": 2,
        "lange_duurloop": True,
        "long_run_km_start": 30,
        "long_run_km_increment": 1,
        "intensiteit_run": "tempoduur_strides",
        "intensiteit_fiets": "toolkit",
        "bike_toolkit": ["threshold", "long_slow", "threshold", "fatmax_lang"],
        "ctl_doel": (78, 88),
        "tss_doel": (600, 750),
        "meso_ritme": "3:1",
        "micro_ritme": "3:1:2:1",
    },
    # ── TRANSFORMATIE CYCLUS 2: race-specifiek ──
    {
        "naam": "transformatie_II",
        "label": "Transformatie II — Race-specifiek",
        "weken": (23, 26),
        "beschrijving": (
            "Delahaije: 'Vanuit die algemene fitheid moet het mogelijk zijn "
            "om binnen 4-5 weken naar een piek toe te werken.' "
            "8x1000m, 5x2000m, marathon-tempo blokken."
        ),
        "run_sessies_per_week": 5,
        "fiets_sessies_per_week": 1,
        "lange_duurloop": True,
        "long_run_km_start": 28,
        "long_run_km_increment": -2,
        "intensiteit_run": "marathon_tempo",
        "intensiteit_fiets": "herstel",
        "ctl_doel": (85, 92),
        "tss_doel": (550, 700),
        "meso_ritme": "3:1",
        "micro_ritme": "3:1:2:1",
    },
    # ── REALISATIE (taper) ──
    {
        "naam": "realisatie",
        "label": "Realisatie — Taper & Race",
        "weken": (27, 28),
        "beschrijving": (
            "Delahaije: 'If it feels good and happy, it will work.' "
            "Volumereductie met behoud van anaerobe prikkels. "
            "TSB naar +15 tot +25 op racedag."
        ),
        "run_sessies_per_week": 3,
        "fiets_sessies_per_week": 0,
        "lange_duurloop": True,
        "long_run_km_start": 15,
        "long_run_km_increment": -5,
        "intensiteit_run": "lichte_strides",
        "intensiteit_fiets": "geen",
        "ctl_doel": (85, 92),
        "tss_doel": (250, 400),
        "meso_ritme": "1:1",
        "micro_ritme": "3:1:2:1",
    },
]


# ── WEEK-VOOR-WEEK PLAN ──────────────────────────────────────────────────

def _build_weekly_plan() -> list[dict]:
    """Bouwt het volledige 28-weken plan."""
    plan = []

    for phase in PHASES:
        wk_start, wk_end = phase["weken"]
        for wk in range(wk_start, wk_end + 1):
            week_in_fase = wk - wk_start + 1
            monday = PLAN_START + timedelta(weeks=wk - 1)

            # ── Bepaal of het een herstelweek is (mesostructuur) ──
            meso = phase.get("meso_ritme", "3:1")
            if meso == "2:1":
                is_recovery = (week_in_fase % 3 == 0)
            elif meso == "3:1":
                is_recovery = (week_in_fase % 4 == 0)
            else:
                is_recovery = (week_in_fase % 2 == 0)

            # Delahaije: herstelblokken 3-4 dagen, niet volle week.
            # We modelleren dit als -30% volume (niet -50%).
            recovery_mod = 0.70 if is_recovery else 1.0

            # ── Loopvolume uit tabel (wk 1–12) of formule (wk 13+) ──
            if wk in RUN_PROGRESSION_TABLE:
                run_km_total, run_sessions_count, long_run_km, is_recovery = RUN_PROGRESSION_TABLE[wk]
                intensiteit = RUN_INTENSITEIT_GATING.get(wk, "geen")
                short_sessions = run_sessions_count - 1
                medium_sessions = 0
                recovery_mod = 0.70 if is_recovery else 1.0

            elif phase["naam"] == "accumulatie_II":
                # Wk 13–14: val terug op formule (tabel dekt 8–12)
                short_km_schedule = [8, 8, 9, 9, 10, 10, 10]
                long_km_schedule = [14, 16, 18, 20, 22, 23, 24]
                idx = min(week_in_fase - 1, len(short_km_schedule) - 1)
                short_km = short_km_schedule[idx]
                long_run_km = long_km_schedule[idx]
                run_km_total = round((short_km * 3 + long_run_km) * recovery_mod, 1)
                short_sessions = 3
                medium_sessions = 0
                run_sessions_count = 4
                intensiteit = "drempel"  # wk 13+ drempelwerk @ 4:20/km

            elif phase["naam"] == "transformatie_I":
                short_schedule = [9, 9, 10, 10]
                medium_schedule = [12, 13, 14, 14]
                long_schedule = [25, 26, 27, 28]
                idx = min(week_in_fase - 1, 3)
                short_km = short_schedule[idx]
                medium_km = medium_schedule[idx]
                long_run_km = long_schedule[idx]
                run_km_total = round((short_km * 3 + medium_km + long_run_km) * recovery_mod, 1)
                short_sessions = 3
                medium_sessions = 1
                run_sessions_count = 5
                intensiteit = "marathon_tempo"

            elif phase["naam"] == "accumulatie_III":
                short_schedule = [10, 10, 10, 10]
                long_schedule = [30, 32, 33, 34]
                idx = min(week_in_fase - 1, 3)
                short_km = short_schedule[idx]
                long_run_km = long_schedule[idx]
                medium_km = 14
                run_km_total = round((short_km * 2 + medium_km + 12 + long_run_km) * recovery_mod, 1)
                short_sessions = 2
                medium_sessions = 1
                run_sessions_count = 5
                intensiteit = "tempoduur_strides"

            elif phase["naam"] == "transformatie_II":
                short_schedule = [10, 10, 10, 10]
                long_schedule = [28, 26, 24, 22]
                idx = min(week_in_fase - 1, 3)
                short_km = short_schedule[idx]
                long_run_km = long_schedule[idx]
                medium_km = 14
                run_km_total = round((short_km * 2 + medium_km + 12 + long_run_km) * recovery_mod, 1)
                short_sessions = 2
                medium_sessions = 1
                run_sessions_count = 5
                intensiteit = "marathon_tempo"

            elif phase["naam"] == "realisatie":
                if week_in_fase == 1:
                    long_run_km = 15
                    run_km_total = round(8 * 2 + long_run_km, 1)
                    run_sessions_count = 3
                else:
                    long_run_km = 0
                    run_km_total = round(5 + 4 + 3, 1)
                    run_sessions_count = 3
                short_sessions = run_sessions_count - (1 if long_run_km > 0 else 0)
                medium_sessions = 0
                intensiteit = "lichte_strides"

            else:
                run_km_total = 0
                long_run_km = 0
                short_sessions = 0
                medium_sessions = 0
                run_sessions_count = 0
                intensiteit = "geen"

            # ── TSS schatting ──
            run_tss = round(run_km_total * 5.5)
            fiets_sessies = phase["fiets_sessies_per_week"]
            fiets_int = phase["intensiteit_fiets"]

            # Toolkit-fases: bereken per geplande sessie-type (threshold + rotatie)
            if fiets_int == "toolkit":
                toolkit = phase.get("bike_toolkit", ["threshold"])
                week_in_fase_idx = min(week_in_fase - 1, len(toolkit) - 1)
                # Threshold = vast anker + roulerend 2e/3e slot
                slot2 = toolkit[week_in_fase_idx]
                # Bij deload: threshold_light + easy_spin
                if is_recovery:
                    fiets_tss = (BIKE_TOOLKIT_TSS["threshold"] * 0.65) + BIKE_TOOLKIT_TSS["easy_spin"]
                    fiets_tss = round(fiets_tss)
                    fiets_sessies = 2
                else:
                    # 3 sessies in accumulatie_I/II, 2 in transformatie/accumulatie_III
                    fiets_tss = BIKE_TOOLKIT_TSS["threshold"] + BIKE_TOOLKIT_TSS.get(slot2, 70)
                    if fiets_sessies >= 3:
                        # 3e slot: altijd fatmax_medium of easy_spin invullen
                        fiets_tss += BIKE_TOOLKIT_TSS["fatmax_medium"]
            elif fiets_int == "sweetspot":
                if is_recovery:
                    fiets_sessies = max(0, fiets_sessies - 1)
                fiets_tss = fiets_sessies * 65
            elif fiets_int == "z1":
                if is_recovery:
                    fiets_sessies = max(0, fiets_sessies - 1)
                fiets_tss = fiets_sessies * 45
            elif fiets_int == "herstel":
                if is_recovery:
                    fiets_sessies = max(0, fiets_sessies - 1)
                fiets_tss = fiets_sessies * 35
            else:
                fiets_tss = 0
            total_tss = run_tss + fiets_tss

            # Bepaal welk type slot2 deze week krijgt (voor print/inspectie)
            bike_slot2 = ""
            if fiets_int == "toolkit":
                toolkit = phase.get("bike_toolkit", ["threshold"])
                bike_slot2 = toolkit[min(week_in_fase - 1, len(toolkit) - 1)]

            plan.append({
                "week": wk,
                "week_in_fase": week_in_fase,
                "monday": monday.isoformat(),
                "fase": phase["naam"],
                "fase_label": phase["label"],
                "run_km_totaal": run_km_total,
                "run_sessies": run_sessions_count,
                "korte_sessies": short_sessions,
                "medium_sessies": medium_sessions,
                "lange_duurloop_km": long_run_km,
                "fiets_sessies": fiets_sessies,
                "run_tss": run_tss,
                "fiets_tss": fiets_tss,
                "totaal_tss": total_tss,
                "run_intensiteit": intensiteit,
                "fiets_intensiteit": fiets_int,
                "bike_slot2": bike_slot2,
                "ctl_doel_min": phase["ctl_doel"][0],
                "ctl_doel_max": phase["ctl_doel"][1],
                "is_recovery": is_recovery,
            })

    return plan


# Bouw het plan eenmalig bij import
WEEKLY_PLAN = _build_weekly_plan()


def get_week_number(today: date = None) -> int:
    """Bepaal het weeknummer (1-28) op basis van de datum."""
    if today is None:
        today = date.today()
    days = (today - PLAN_START).days
    week = days // 7 + 1
    return max(1, min(28, week))


def get_current_phase(today: date = None) -> dict:
    """Geeft de huidige fase terug met alle context."""
    if today is None:
        today = date.today()
    wk = get_week_number(today)

    for phase in PHASES:
        wk_start, wk_end = phase["weken"]
        if wk_start <= wk <= wk_end:
            # Week-specifieke gating overstijgt de fase-default
            week_gating = RUN_INTENSITEIT_GATING.get(wk, phase["intensiteit_run"])
            if wk >= 13 and wk not in RUN_INTENSITEIT_GATING:
                week_gating = "drempel"
            return {
                "fase_naam": phase["naam"],
                "fase_label": phase["label"],
                "week_nummer": wk,
                "week_in_fase": wk - wk_start + 1,
                "beschrijving": phase["beschrijving"],
                "run_sessies_per_week": phase["run_sessies_per_week"],
                "fiets_sessies_per_week": phase["fiets_sessies_per_week"],
                "lange_duurloop": phase["lange_duurloop"],
                "intensiteit_run": phase["intensiteit_run"],
                "intensiteit_fiets": phase["intensiteit_fiets"],
                "run_intensiteit_gating": week_gating,
                "bike_toolkit": phase.get("bike_toolkit", []),
                "ctl_doel": phase["ctl_doel"],
                "tss_doel": phase["tss_doel"],
                "weeks_to_race": max(0, (RACE_DATE - today).days // 7),
            }

    return {
        "fase_naam": "realisatie",
        "fase_label": "Race Week",
        "week_nummer": 28,
        "week_in_fase": 2,
        "beschrijving": "Race week!",
        "run_sessies_per_week": 3,
        "fiets_sessies_per_week": 0,
        "lange_duurloop": False,
        "intensiteit_run": "geen",
        "intensiteit_fiets": "geen",
        "ctl_doel": (85, 92),
        "tss_doel": (150, 200),
        "weeks_to_race": 0,
    }


def calculate_weekly_run_volume(week_number: int) -> dict:
    """Berekent het loopvolume voor een specifieke week."""
    if week_number < 1:
        week_number = 1
    if week_number > 28:
        week_number = 28

    week_plan = WEEKLY_PLAN[week_number - 1]

    total_km = week_plan["run_km_totaal"]
    long_km = week_plan["lange_duurloop_km"]
    korte_sessies = week_plan["korte_sessies"]
    medium_sessies = week_plan.get("medium_sessies", 0)

    if korte_sessies + medium_sessies > 0:
        rest_km = total_km - long_km
        if medium_sessies > 0 and korte_sessies > 0:
            medium_km = rest_km * 0.35
            kort_km = rest_km - medium_km
            km_per_korte = round(kort_km / korte_sessies, 1)
            km_per_medium = round(medium_km / medium_sessies, 1)
        elif korte_sessies > 0:
            km_per_korte = round(rest_km / korte_sessies, 1)
            km_per_medium = 0
        else:
            km_per_korte = 0
            km_per_medium = 0
    else:
        km_per_korte = 0
        km_per_medium = 0

    return {
        "week": week_number,
        "fase": week_plan["fase"],
        "fase_label": week_plan["fase_label"],
        "run_km_totaal": total_km,
        "run_sessies": week_plan["run_sessies"],
        "korte_sessies": korte_sessies,
        "km_per_korte_sessie": km_per_korte,
        "medium_sessies": medium_sessies,
        "km_per_medium_sessie": km_per_medium,
        "lange_duurloop_km": long_km,
        "fiets_sessies": week_plan["fiets_sessies"],
        "run_intensiteit": week_plan["run_intensiteit"],
        "fiets_intensiteit": week_plan["fiets_intensiteit"],
        "run_tss": week_plan["run_tss"],
        "fiets_tss": week_plan["fiets_tss"],
        "totaal_tss": week_plan["totaal_tss"],
    }


def print_full_plan():
    """Print het volledige 28-weken periodiseringsplan."""
    print("\n" + "=" * 100)
    print("  AMSTERDAM MARATHON 2026 — DELAHAIJE BLOKPERIODISERING")
    print("  Race: 18 oktober 2026 | Atleet: Dylsky (i85836)")
    print("  Accumulatie → Transformatie → Realisatie (cyclisch)")
    print("=" * 100)

    current_phase = ""
    for wp in WEEKLY_PLAN:
        if wp["fase_label"] != current_phase:
            current_phase = wp["fase_label"]
            phase_info = next(p for p in PHASES if p["naam"] == wp["fase"])
            print(f"\n  {'─' * 96}")
            print(f"  {current_phase.upper()} (wk {phase_info['weken'][0]}-{phase_info['weken'][1]})")
            print(f"  {phase_info['beschrijving']}")
            toolkit_str = ",".join(phase_info.get('bike_toolkit', [])) or phase_info['intensiteit_fiets']
            print(f"  Meso: {phase_info.get('meso_ritme', '3:1')} | Fiets-toolkit: {toolkit_str}")
            print(f"  {'─' * 96}")
            print(f"  {'Wk':>3} | {'Maandag':>10} | {'Run km':>7} | {'Sessies':>7} | {'Lang km':>7} | "
                  f"{'Fiets':>5} | {'Tot TSS':>7} | {'Herstel':>7} | {'Gating':>10} | {'Slot2'}")

        long_str = f"{wp['lange_duurloop_km']:.0f}" if wp["lange_duurloop_km"] > 0 else "-"
        rec_str = "ja" if wp.get("is_recovery") else ""
        gating = RUN_INTENSITEIT_GATING.get(wp['week'], "drempel" if wp['week'] >= 13 else wp['run_intensiteit'])
        slot2 = wp.get("bike_slot2", "")
        print(f"  {wp['week']:3d} | {wp['monday']:>10} | {wp['run_km_totaal']:6.1f} | "
              f"{wp['run_sessies']:7d} | {long_str:>7} | {wp['fiets_sessies']:5d} | "
              f"{wp['totaal_tss']:7d} | {rec_str:>7} | {gating:>10} | {slot2}")

    print(f"\n  {'─' * 96}")
    total_run_km = sum(wp["run_km_totaal"] for wp in WEEKLY_PLAN)
    total_tss = sum(wp["totaal_tss"] for wp in WEEKLY_PLAN)
    print(f"  TOTAAL: {total_run_km:.0f} km hardlopen | {total_tss} TSS over 28 weken")
    print("=" * 100 + "\n")


if __name__ == "__main__":
    print_full_plan()

    print("\n=== Huidige fase ===")
    phase = get_current_phase()
    for k, v in phase.items():
        print(f"  {k}: {v}")

    print("\n=== Volume deze week ===")
    vol = calculate_weekly_run_volume(phase["week_nummer"])
    for k, v in vol.items():
        print(f"  {k}: {v}")
