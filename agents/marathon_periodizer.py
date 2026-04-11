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

PHASES = [
    # ── ACCUMULATIE CYCLUS 1: herstel + aerobe basis ──
    {
        "naam": "accumulatie_I",
        "label": "Accumulatie I — Herstel & Basis",
        "weken": (1, 7),
        "beschrijving": (
            "Terugkeer uit blessure. 100% Zone 1. Fiets als aerobe vulling. "
            "Tempoduurloop introduceren in week 3-4 (net onder aerobe drempel, "
            "dit is nog steeds Z1 in Delahaije's model)."
        ),
        "run_sessies_per_week": 3,   # fysio: start 3x, groeit naar 4-5
        "fiets_sessies_per_week": 2,
        "run_km_start": 6,
        "run_km_increment": 1,
        "lange_duurloop": False,     # komt in week 3-4
        "intensiteit_run": "geen",   # week 1-2: puur Z1; week 3+: tempoduur
        "intensiteit_fiets": "z1",   # Delahaije: accumulatie = 100% Z1
        "ctl_doel": (43, 55),
        "tss_doel": (280, 400),
        "meso_ritme": "2:1",         # 2 build, 1 herstel (blessureherstel)
        "micro_ritme": "3:1:2:1",    # Delahaije dagritme
    },
    # ── ACCUMULATIE CYCLUS 2: volume opbouwen ──
    {
        "naam": "accumulatie_II",
        "label": "Accumulatie II — Volume",
        "weken": (8, 14),
        "beschrijving": (
            "Volume opbouwen naar 8-10 uur/week. Lange duurloop groeit. "
            "Tempoduurloop wordt sleutelsessie (4-6x 8min @ 85% HRmax). "
            "Strides (4-6x 80m) in 2-3 sessies/week. Nog steeds 100% Z1."
        ),
        "run_sessies_per_week": 4,
        "fiets_sessies_per_week": 2,
        "lange_duurloop": True,
        "long_run_km_start": 14,
        "long_run_km_increment": 1.5,
        "intensiteit_run": "tempoduur_strides",
        "intensiteit_fiets": "z1",
        "ctl_doel": (55, 68),
        "tss_doel": (400, 550),
        "meso_ritme": "3:1",
        "micro_ritme": "3:1:2:1",
    },
    # ── TRANSFORMATIE CYCLUS 1: intensiteit introduceren ──
    {
        "naam": "transformatie_I",
        "label": "Transformatie I — Scherpte",
        "weken": (15, 18),
        "beschrijving": (
            "Delahaije transformatiefase: Z1 volume blijft hoog, Z3 intervallen "
            "erbij. 90/10 verdeling. Op de fiets: sweetspot/threshold mag weer. "
            "'De intensieve trainingen gaan tot het gaatje.'"
        ),
        "run_sessies_per_week": 5,
        "fiets_sessies_per_week": 2,
        "lange_duurloop": True,
        "long_run_km_start": 25,
        "long_run_km_increment": 1,
        "intensiteit_run": "marathon_tempo",
        "intensiteit_fiets": "sweetspot",
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
            "Terug naar 100% Z1 maar op hoger volume. Langste duurlopen. "
            "Aerobe residuele effecten houden 30-35 dagen aan — hier wordt "
            "het fundament gelegd voor de laatste transformatie."
        ),
        "run_sessies_per_week": 5,
        "fiets_sessies_per_week": 1,
        "lange_duurloop": True,
        "long_run_km_start": 30,
        "long_run_km_increment": 1,
        "intensiteit_run": "tempoduur_strides",
        "intensiteit_fiets": "z1",
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

            # ── Loopvolume berekenen ──
            if phase["naam"] == "accumulatie_I":
                # Fysio: 3x per week, start 6km, +1km/sessie/week
                km_per_sessie = phase["run_km_start"] + (wk - 1) * phase["run_km_increment"]
                run_sessions_count = phase["run_sessies_per_week"]
                # Vanaf week 3: 4e sessie (korte herstelrun) toevoegen als knie ok
                if wk >= 3:
                    run_sessions_count = 4
                # Vanaf week 5: tempoduurloop als sleutelsessie
                intensiteit = "geen" if wk <= 4 else "tempoduur"
                # Lange duurloop vanaf week 4
                if wk >= 4:
                    long_run_km = km_per_sessie + 2
                    run_km_total = round((km_per_sessie * (run_sessions_count - 1) + long_run_km) * recovery_mod, 1)
                else:
                    long_run_km = 0
                    run_km_total = round(km_per_sessie * run_sessions_count * recovery_mod, 1)
                short_sessions = run_sessions_count - (1 if long_run_km > 0 else 0)
                medium_sessions = 0

            elif phase["naam"] == "accumulatie_II":
                # Volume opbouwen: 4 sessies + lange duurloop
                short_km_schedule = [8, 8, 9, 9, 10, 10, 10]
                long_km_schedule = [14, 16, 18, 20, 22, 23, 24]
                idx = min(week_in_fase - 1, len(short_km_schedule) - 1)
                short_km = short_km_schedule[idx]
                long_run_km = long_km_schedule[idx]
                run_km_total = round((short_km * 3 + long_run_km) * recovery_mod, 1)
                short_sessions = 3
                medium_sessions = 0
                run_sessions_count = 4
                intensiteit = "tempoduur_strides"

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
            if is_recovery:
                fiets_sessies = max(0, fiets_sessies - 1)
            fiets_int = phase["intensiteit_fiets"]
            if fiets_int == "sweetspot":
                fiets_tss_per_sessie = 65
            elif fiets_int == "z1":
                fiets_tss_per_sessie = 45  # Z1 duurrit: langer maar lager IF
            elif fiets_int == "herstel":
                fiets_tss_per_sessie = 35
            else:
                fiets_tss_per_sessie = 0
            fiets_tss = fiets_sessies * fiets_tss_per_sessie
            total_tss = run_tss + fiets_tss

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
            print(f"  Meso: {phase_info.get('meso_ritme', '3:1')} | Fiets: {phase_info['intensiteit_fiets']}")
            print(f"  {'─' * 96}")
            print(f"  {'Wk':>3} | {'Maandag':>10} | {'Run km':>7} | {'Sessies':>7} | {'Lang km':>7} | "
                  f"{'Fiets':>5} | {'Tot TSS':>7} | {'Herstel':>7} | {'Intensiteit'}")

        long_str = f"{wp['lange_duurloop_km']:.0f}" if wp["lange_duurloop_km"] > 0 else "-"
        rec_str = "ja" if wp.get("is_recovery") else ""
        print(f"  {wp['week']:3d} | {wp['monday']:>10} | {wp['run_km_totaal']:6.1f} | "
              f"{wp['run_sessies']:7d} | {long_str:>7} | {wp['fiets_sessies']:5d} | "
              f"{wp['totaal_tss']:7d} | {rec_str:>7} | "
              f"{wp['run_intensiteit']}")

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
