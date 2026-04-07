"""
Marathon Periodizer — beheerst de langetermijn-fasering voor de Amsterdam Marathon.

Amsterdam Marathon: 18 oktober 2026 (~28 weken vanaf 31 maart 2026)
Atleet: Dylsky (i85836), terugkeer uit gluteus medius blessure.

Fasering gebaseerd op Louis Delahaije filosofie:
- ~80-90% van looptraining in Z1-Z2 (gepolariseerd model)
- Crosstraining (fietsen) als primaire blessurepreventiestrategie
- Eerst aerobe basis bouwen, dan pas specifieke marathonvoorbereiding
- Lichaamsbewustzijn boven schema: pas tempo aan op gevoel
- "Gelukkige atleet = snelle atleet"

Fysio-constraint bij start:
- 3x per week hardlopen, start op 6 km per sessie
- Elke week +1 km per sessie
- 3x per week fietsen
- Uitsluitend Z1-Z2 hardlopen totdat Injury Guard groen licht geeft

6 fases:
  Fase 1 — Herstel & Opbouw I    (wk 1-5)
  Fase 2 — Opbouw II             (wk 6-10)
  Fase 3 — Algemene Basis        (wk 11-15)
  Fase 4 — Specifieke Opbouw     (wk 16-20)
  Fase 5 — Piek & Volume         (wk 21-24)
  Fase 6 — Afbouw & Race         (wk 25-28)
"""

from datetime import date, timedelta

RACE_DATE = date(2026, 10, 18)
PLAN_START = date(2026, 4, 6)  # maandag van week 1 (na deload week)

# ── FASE DEFINITIES ─────────────────────────────────────────────────────────

PHASES = [
    {
        "naam": "herstel_opbouw_I",
        "label": "Herstel & Opbouw I",
        "weken": (1, 5),
        "beschrijving": "Terugkeer uit blessure. Loopfrequentie opbouwen, fiets als aerobe basis.",
        "run_sessies_per_week": 3,
        "fiets_sessies_per_week": 3,
        "run_km_start": 6,       # km per sessie in week 1
        "run_km_increment": 1,   # +1 km per sessie per week (fysio-advies)
        "lange_duurloop": False,
        "intensiteit_run": "geen",
        "intensiteit_fiets": "sweetspot",
        "ctl_doel": (43, 55),
        "tss_doel": (280, 400),
    },
    {
        "naam": "opbouw_II",
        "label": "Opbouw II",
        "weken": (6, 10),
        "beschrijving": "Eerste lange duurloop introduceren. Strides na Injury Guard groen.",
        "run_sessies_per_week": 4,  # 3 kort + 1 lang
        "fiets_sessies_per_week": 3,
        "lange_duurloop": True,
        "long_run_km_start": 14,
        "long_run_km_increment": 1.5,
        "intensiteit_run": "strides",  # alleen als Injury Guard groen + 14 dgn symptoomvrij
        "intensiteit_fiets": "sweetspot",
        "ctl_doel": (55, 65),
        "tss_doel": (400, 520),
    },
    {
        "naam": "algemene_basis",
        "label": "Algemene Basis",
        "weken": (11, 15),
        "beschrijving": "Volume opbouwen naar 65 km/week. Lange duurloop naar 25 km.",
        "run_sessies_per_week": 5,  # 3 kort + 1 medium + 1 lang
        "fiets_sessies_per_week": 2,
        "lange_duurloop": True,
        "long_run_km_start": 20,
        "long_run_km_increment": 1,
        "intensiteit_run": "lichte_tempo",  # alleen Injury Guard groen + 21 dgn symptoomvrij
        "intensiteit_fiets": "sweetspot",
        "ctl_doel": (65, 72),
        "tss_doel": (480, 600),
    },
    {
        "naam": "specifieke_opbouw",
        "label": "Specifieke Opbouw",
        "weken": (16, 20),
        "beschrijving": "Marathon-specifieke tempowerk. Volume naar 80 km/week.",
        "run_sessies_per_week": 5,
        "fiets_sessies_per_week": 2,
        "lange_duurloop": True,
        "long_run_km_start": 25,
        "long_run_km_increment": 1.5,
        "intensiteit_run": "marathon_tempo",
        "intensiteit_fiets": "herstel",
        "ctl_doel": (72, 82),
        "tss_doel": (550, 700),
    },
    {
        "naam": "piek_volume",
        "label": "Piek & Volume",
        "weken": (21, 24),
        "beschrijving": "Piekvolume 85-90 km/week. Langste duurloop 35 km.",
        "run_sessies_per_week": 5,
        "fiets_sessies_per_week": 1,
        "lange_duurloop": True,
        "long_run_km_start": 32,
        "long_run_km_increment": 1,
        "intensiteit_run": "marathon_tempo",
        "intensiteit_fiets": "herstel",
        "ctl_doel": (82, 90),
        "tss_doel": (600, 750),
    },
    {
        "naam": "afbouw_race",
        "label": "Afbouw & Race",
        "weken": (25, 28),
        "beschrijving": "Geleidelijk afbouwen. TSB naar +15 tot +25 op racedag.",
        "run_sessies_per_week": 4,  # afnemend naar 3 in race week
        "fiets_sessies_per_week": 1,
        "lange_duurloop": True,
        "long_run_km_start": 20,  # 3 wk voor race: laatste lange duurloop
        "long_run_km_increment": -5,  # afbouwen
        "intensiteit_run": "lichte_strides",
        "intensiteit_fiets": "herstel",
        "ctl_doel": (85, 90),
        "tss_doel": (350, 500),
    },
]


# ── WEEK-VOOR-WEEK LOOPVOLUME (28 weken) ──────────────────────────────────

def _build_weekly_plan() -> list[dict]:
    """
    Bouwt het volledige 28-weken plan met per week:
    - fase, week_nummer, week_in_fase
    - run_km_totaal, sessies (kort/lang), lange_duurloop_km
    - fiets_sessies, run_intensiteit, fiets_intensiteit
    - tss_doel, ctl_doel
    """
    plan = []

    for phase in PHASES:
        wk_start, wk_end = phase["weken"]
        for wk in range(wk_start, wk_end + 1):
            week_in_fase = wk - wk_start + 1
            monday = PLAN_START + timedelta(weeks=wk - 1)

            # ── Loopvolume berekenen ──
            if phase["naam"] == "herstel_opbouw_I":
                # Fysio: 3x per week, start 6km, +1km/sessie/week
                km_per_sessie = phase["run_km_start"] + (wk - 1) * phase["run_km_increment"]
                run_sessions_count = phase["run_sessies_per_week"]
                run_km_total = round(km_per_sessie * run_sessions_count, 1)
                long_run_km = 0
                short_sessions = run_sessions_count
                medium_sessions = 0

            elif phase["naam"] == "opbouw_II":
                # Transitie: 4e sessie (long run) introduceren, korte sessies terugschroeven
                # Week 5 was 3x 10km = 30km. Max +10% per week.
                # Week 6: 3x 8km + 10km long = 34km (+13%)
                # Week 7: 3x 8km + 12km long = 36km (+6%)
                # Week 8: 3x 9km + 14km long = 41km (+14% — grenswaarde)
                # Week 9: 3x 9km + 16km long = 43km (+5%)
                # Week 10: 3x 10km + 18km long = 48km (+12%)
                prev_week_km = 30  # week 5 eindvolume
                short_km_schedule = [8, 8, 9, 9, 10]  # per korte sessie per week-in-fase
                long_km_schedule = [10, 12, 14, 16, 18]  # lange duurloop per week-in-fase
                idx = min(week_in_fase - 1, len(short_km_schedule) - 1)
                short_km = short_km_schedule[idx]
                long_run_km = long_km_schedule[idx]
                run_km_total = round(short_km * 3 + long_run_km, 1)
                short_sessions = 3
                medium_sessions = 0
                run_sessions_count = 4

            elif phase["naam"] == "algemene_basis":
                # Transitie van fase 2 (48km, 4 sessies) naar 5 sessies.
                # 5e sessie (medium) introduceren, geleidelijk opbouwen.
                # Wk 10 was ~48km. Wk 11 moet ~53km zijn (+10%).
                # Wk 11: 3x 8km + 1x 10km medium + 19km long = 53km
                # Wk 12: 3x 8km + 1x 11km + 20km = 55km
                # Wk 13: 3x 9km + 1x 12km + 22km = 61km
                # Wk 14: 3x 9km + 1x 13km + 23km = 63km
                # Wk 15: 3x 10km + 1x 13km + 24km = 67km
                short_schedule = [8, 8, 9, 9, 10]
                medium_schedule = [10, 11, 12, 13, 13]
                long_schedule = [19, 20, 22, 23, 24]
                idx = min(week_in_fase - 1, 4)
                short_km = short_schedule[idx]
                medium_km = medium_schedule[idx]
                long_run_km = long_schedule[idx]
                run_km_total = round(short_km * 3 + medium_km + long_run_km, 1)
                short_sessions = 3
                medium_sessions = 1
                run_sessions_count = 5

            elif phase["naam"] == "specifieke_opbouw":
                # Wk 15 was ~67km. Geleidelijk naar 80km.
                # Wk 16: 2x 10km + 14km med + 12km easy + 25km long = 71km
                # Wk 17: 2x 10km + 14km + 12km + 27km = 73km
                # Wk 18: 2x 10km + 15km + 13km + 28km = 76km
                # Wk 19: 2x 10km + 15km + 13km + 30km = 78km
                # Wk 20: 2x 10km + 16km + 13km + 31km = 80km
                short_schedule = [10, 10, 10, 10, 10]
                medium_schedule = [14, 14, 15, 15, 16]
                easy_schedule = [12, 12, 13, 13, 13]
                long_schedule = [25, 27, 28, 30, 31]
                idx = min(week_in_fase - 1, 4)
                short_km = short_schedule[idx]
                medium_km = medium_schedule[idx]
                easy_km = easy_schedule[idx]
                long_run_km = long_schedule[idx]
                run_km_total = round(short_km * 2 + medium_km + easy_km + long_run_km, 1)
                short_sessions = 2
                medium_sessions = 1
                run_sessions_count = 5

            elif phase["naam"] == "piek_volume":
                # Wk 20 was ~80km. Piek naar 85km, deload wk 23 (-20%).
                # Wk 21: 2x 10km + 16km + 14km + 32km = 82km
                # Wk 22: 2x 10km + 16km + 14km + 33km = 83km
                # Wk 23 (deload): 2x 8km + 14km + 12km + 24km = 66km (-20%)
                # Wk 24: 2x 10km + 16km + 14km + 32km = 82km (terug naar pre-deload)
                if week_in_fase == 3:  # deload
                    short_km = 8
                    medium_km = 14
                    easy_km = 12
                    long_run_km = 24
                else:
                    long_schedule = [32, 33, 24, 32]
                    idx = min(week_in_fase - 1, 3)
                    short_km = 10
                    medium_km = 16
                    easy_km = 14
                    long_run_km = long_schedule[idx]
                run_km_total = round(short_km * 2 + medium_km + easy_km + long_run_km, 1)
                short_sessions = 2
                medium_sessions = 1
                run_sessions_count = 5

            elif phase["naam"] == "afbouw_race":
                # Geleidelijke afbouw
                if week_in_fase == 1:
                    long_run_km = 20
                    run_km_total = round(8 * 3 + long_run_km, 1)
                    run_sessions_count = 4
                elif week_in_fase == 2:
                    long_run_km = 15
                    run_km_total = round(8 * 2 + 6 + long_run_km, 1)
                    run_sessions_count = 4
                elif week_in_fase == 3:
                    long_run_km = 10
                    run_km_total = round(6 * 2 + long_run_km, 1)
                    run_sessions_count = 3
                else:
                    # Race week
                    long_run_km = 0  # race = 42.2 km
                    run_km_total = round(5 + 4 + 3, 1)  # shakeout runs
                    run_sessions_count = 3
                short_sessions = run_sessions_count - (1 if long_run_km > 0 else 0)
                medium_sessions = 0

            else:
                run_km_total = 0
                long_run_km = 0
                short_sessions = 0
                medium_sessions = 0
                run_sessions_count = 0

            # ── TSS schatting ──
            # Run TSS: ~1 TSS per km bij Z2 tempo (conservatief)
            run_tss = round(run_km_total * 5.5)  # ~5.5 TSS/km bij Z2 voor 85kg loper
            # Fiets TSS: afhankelijk van intensiteit
            fiets_sessies = phase["fiets_sessies_per_week"]
            if phase["intensiteit_fiets"] == "sweetspot":
                fiets_tss_per_sessie = 65  # gemiddeld sweetspot sessie
            elif phase["intensiteit_fiets"] == "herstel":
                fiets_tss_per_sessie = 40
            else:
                fiets_tss_per_sessie = 50
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
                "run_intensiteit": phase["intensiteit_run"],
                "fiets_intensiteit": phase["intensiteit_fiets"],
                "ctl_doel_min": phase["ctl_doel"][0],
                "ctl_doel_max": phase["ctl_doel"][1],
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
    """
    Geeft de huidige fase terug met alle context.

    Returns:
        dict met: fase_naam, fase_label, week_nummer, week_in_fase,
        beschrijving, en alle fase-constraints
    """
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

    # Voorbij het plan
    return {
        "fase_naam": "afbouw_race",
        "fase_label": "Race Week",
        "week_nummer": 28,
        "week_in_fase": 4,
        "beschrijving": "Race week!",
        "run_sessies_per_week": 3,
        "fiets_sessies_per_week": 0,
        "lange_duurloop": False,
        "intensiteit_run": "geen",
        "intensiteit_fiets": "geen",
        "ctl_doel": (85, 90),
        "tss_doel": (150, 200),
        "weeks_to_race": 0,
    }


def calculate_weekly_run_volume(week_number: int) -> dict:
    """
    Berekent het loopvolume voor een specifieke week.

    Returns:
        dict met: run_km_totaal, korte_sessies_km, lange_duurloop_km,
        run_sessies, intensiteit_toegestaan
    """
    if week_number < 1:
        week_number = 1
    if week_number > 28:
        week_number = 28

    week_plan = WEEKLY_PLAN[week_number - 1]

    # Bereken km per korte sessie
    total_km = week_plan["run_km_totaal"]
    long_km = week_plan["lange_duurloop_km"]
    korte_sessies = week_plan["korte_sessies"]
    medium_sessies = week_plan.get("medium_sessies", 0)

    if korte_sessies + medium_sessies > 0:
        # Verdeel resterende km over korte en medium sessies
        rest_km = total_km - long_km
        if medium_sessies > 0 and korte_sessies > 0:
            medium_km = rest_km * 0.35  # medium krijgt ~35% van de rest
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
    print("  AMSTERDAM MARATHON 2026 — 28-WEKEN PERIODISERINGSPLAN")
    print("  Race: 18 oktober 2026 | Atleet: Dylsky (i85836)")
    print("  Filosofie: Louis Delahaije — gepolariseerd, luister naar je lichaam")
    print("=" * 100)

    current_phase = ""
    for wp in WEEKLY_PLAN:
        if wp["fase_label"] != current_phase:
            current_phase = wp["fase_label"]
            phase_info = next(p for p in PHASES if p["naam"] == wp["fase"])
            print(f"\n  {'─' * 96}")
            print(f"  FASE: {current_phase.upper()} (wk {phase_info['weken'][0]}-{phase_info['weken'][1]})")
            print(f"  {phase_info['beschrijving']}")
            print(f"  CTL-doel: {phase_info['ctl_doel'][0]}-{phase_info['ctl_doel'][1]}")
            print(f"  {'─' * 96}")
            print(f"  {'Wk':>3} | {'Maandag':>10} | {'Run km':>7} | {'Sessies':>7} | {'Lang km':>7} | "
                  f"{'Fiets':>5} | {'Run TSS':>7} | {'Fiets TSS':>9} | {'Tot TSS':>7} | {'Intensiteit'}")
            print(f"  {'---':>3} | {'----------':>10} | {'------':>7} | {'-------':>7} | {'------':>7} | "
                  f"{'-----':>5} | {'-------':>7} | {'---------':>9} | {'-------':>7} | {'----------'}")

        long_str = f"{wp['lange_duurloop_km']:.0f}" if wp["lange_duurloop_km"] > 0 else "-"
        print(f"  {wp['week']:3d} | {wp['monday']:>10} | {wp['run_km_totaal']:6.1f} | "
              f"{wp['run_sessies']:7d} | {long_str:>7} | {wp['fiets_sessies']:5d} | "
              f"{wp['run_tss']:7d} | {wp['fiets_tss']:9d} | {wp['totaal_tss']:7d} | "
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
