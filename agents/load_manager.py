"""
Load Manager — berekent CTL/ATL/TSB en bepaalt trainingsbelasting voor de komende week.

CTL (Chronic Training Load) = fitheid (42-daags gemiddelde van dagelijkse TSS)
ATL (Acute Training Load) = vermoeidheid (7-daags gemiddelde)
TSB (Training Stress Balance) = vorm = CTL - ATL

Gebaseerd op de principes van Coggan/Allen en toegepast in de stijl van
Guido Hartensveld en Michael Butter: opbouwen met hoofd, TSB piekt op racedag.

Race: sub 40 min 10km Leiden 16 juni 2026
"""

import json
import math
from datetime import date, timedelta
from pathlib import Path

STATE_PATH = Path(__file__).parent.parent / "state.json"

RACE_DATE = date(2026, 10, 18)

# Wekelijkse TSS targets per fase (bij volle belasting, Injury Guard GROEN)
# Marathon-fasering (28 weken)
PHASE_TSS_TARGETS = {
    "herstel_opbouw_I":  (280, 400),
    "opbouw_II":         (400, 520),
    "algemene_basis":    (480, 600),
    "specifieke_opbouw": (550, 700),
    "piek_volume":       (600, 750),
    "afbouw_race":       (350, 500),
    # Legacy fases (backwards compatible)
    "basis_I":    (330, 420),
    "basis_II":   (380, 470),
    "opbouw_I":   (430, 530),
    "specifiek":  (530, 640),
    "afbouw":     (320, 400),
    "race_week":  (130, 200),
}

# CTL streefwaarden per fase
PHASE_CTL_TARGETS = {
    "herstel_opbouw_I":  (43, 55),
    "opbouw_II":         (55, 65),
    "algemene_basis":    (65, 72),
    "specifieke_opbouw": (72, 82),
    "piek_volume":       (82, 90),
    "afbouw_race":       (85, 90),
    # Legacy
    "basis_I":   (42, 52),
    "basis_II":  (52, 62),
    "opbouw_I":  (60, 68),
    "opbouw_II": (66, 72),
    "specifiek": (70, 80),
    "afbouw":    (72, 80),
    "race_week": (70, 80),
}

# TSB streefbereik per fase (positief = fris, negatief = vermoeid/adaptatie)
PHASE_TSB_RANGE = {
    "herstel_opbouw_I":  (-12, -4),
    "opbouw_II":         (-15, -6),
    "algemene_basis":    (-18, -8),
    "specifieke_opbouw": (-20, -10),
    "piek_volume":       (-22, -12),
    "afbouw_race":       (-5, +25),
    # Legacy
    "basis_I":   (-12, -4),
    "basis_II":  (-15, -6),
    "opbouw_I":  (-18, -8),
    "specifiek": (-22, -12),
    "afbouw":    (-5, +5),
    "race_week": (+12, +25),
}


def _load_state() -> dict:
    with open(STATE_PATH) as f:
        return json.load(f)


def _save_state(state: dict) -> None:
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=4, ensure_ascii=False)


def _weeks_to_race() -> int:
    return max(0, (RACE_DATE - date.today()).days // 7)


def _determine_phase(weeks_to_race: int) -> str:
    """Bepaal fase via marathon_periodizer als beschikbaar, anders legacy logica."""
    try:
        from agents import marathon_periodizer
        phase_info = marathon_periodizer.get_current_phase()
        return phase_info["fase_naam"]
    except (ImportError, Exception):
        pass
    # Legacy fallback (10km plan)
    if weeks_to_race >= 11:
        return "basis_I"
    elif weeks_to_race >= 9:
        return "basis_II"
    elif weeks_to_race >= 7:
        return "opbouw_I"
    elif weeks_to_race >= 5:
        return "opbouw_II"
    elif weeks_to_race >= 2:
        return "specifiek"
    elif weeks_to_race == 1:
        return "afbouw"
    else:
        return "race_week"


def _calculate_ctl_atl(activities: list, stored_ctl: float, stored_atl: float) -> tuple[float, float]:
    """
    Bereken CTL en ATL op basis van activiteiten.
    Vult ontbrekende dagen aan met 0 TSS.
    """
    if not activities:
        return stored_ctl, stored_atl

    # Groepeer TSS per dag
    tss_by_day: dict[date, float] = {}
    for act in activities:
        # intervals.icu kan 'icu_training_load' of 'training_load' gebruiken
        tss = act.get("icu_training_load") or act.get("training_load") or 0
        if not tss:
            continue
        act_date_str = act.get("start_date_local", "")[:10]
        if not act_date_str:
            continue
        try:
            act_date = date.fromisoformat(act_date_str)
            tss_by_day[act_date] = tss_by_day.get(act_date, 0) + tss
        except ValueError:
            continue

    if not tss_by_day:
        return stored_ctl, stored_atl

    # Loop door de dagen en pas exponentieel gemiddelde toe
    start = min(tss_by_day.keys())
    end = date.today()
    ctl = stored_ctl
    atl = stored_atl

    current = start
    while current <= end:
        tss = tss_by_day.get(current, 0)
        ctl = ctl + (tss - ctl) / 42
        atl = atl + (tss - atl) / 7
        current += timedelta(days=1)

    return round(ctl, 1), round(atl, 1)


def analyze(activities: list = None, injury_guard_output: dict = None) -> dict:
    """
    Analyseer trainingsbelasting en geef weekdoel terug.

    Args:
        activities: Activiteiten van afgelopen 42 dagen
        injury_guard_output: Output van Injury Guard (voor volume_modifier)

    Returns:
        dict met CTL/ATL/TSB, fase, weekdoel en aanbevelingen
    """
    state = _load_state()
    load = state["load"]

    stored_ctl = load.get("ctl_estimate", 45.0)
    stored_atl = load.get("atl_estimate", 48.0)

    # Herbereken CTL/ATL als we activiteitendata hebben
    if activities:
        ctl, atl = _calculate_ctl_atl(activities, stored_ctl, stored_atl)
    else:
        ctl = stored_ctl
        atl = stored_atl

    tsb = round(ctl - atl, 1)

    weeks_to_race = _weeks_to_race()
    phase = _determine_phase(weeks_to_race)

    # Update phase in state
    state["current_phase"] = phase
    state["week_number"] = max(1, 13 - weeks_to_race + 1)

    # Bepaal wekelijkse TSS target — gebaseerd op CTL, niet op statische fase-ranges.
    # CTL * 7 = TSS nodig om huidige fitheid te BEHOUDEN.
    # Build week: 5-10% boven CTL-onderhoud om fitheid op te bouwen.
    # Fase-ranges zijn guardrails, niet het doel.
    maintain_tss = round(ctl * 7)  # TSS om CTL te behouden
    ctl_min, ctl_max = PHASE_CTL_TARGETS.get(phase, (50, 65))

    if ctl < ctl_min:
        # Onder fase-doel: bouw op met +8%
        target_tss = round(maintain_tss * 1.08)
    elif ctl > ctl_max:
        # Boven fase-doel: consolideer
        target_tss = maintain_tss
    else:
        # In de zone: lichte opbouw +5%
        target_tss = round(maintain_tss * 1.05)

    # TSB correctie: als je te moe bent, minder. Te fris, iets meer.
    tsb_min, tsb_max = PHASE_TSB_RANGE.get(phase, (-15, -5))
    if tsb < tsb_min:
        target_tss = round(target_tss * 0.90)
    elif tsb > tsb_max + 5:
        target_tss = round(target_tss * 1.05)

    # Build/Deload cyclus: 3 build weken + 1 deload, flexibel
    bd = state.get("build_deload", {})
    consecutive_build = bd.get("consecutive_build_weeks", 0)
    target_build = bd.get("target_build_weeks", 3)
    deload_mod = bd.get("deload_modifier", 0.70)

    # Bepaal of dit een deload week is
    is_deload_week = consecutive_build >= target_build
    # Of als TSB te negatief is → geforceerde deload
    if tsb < -25:
        is_deload_week = True

    if is_deload_week:
        target_tss = round(target_tss * deload_mod)

    # Injury Guard modifier
    volume_modifier = 1.0
    if injury_guard_output:
        volume_modifier = injury_guard_output.get("volume_modifier", 1.0)
    target_tss = round(target_tss * volume_modifier)

    # Max TSS per sessie (voorkomt te grote pieken)
    max_session_tss = round(target_tss * 0.28)

    # Overtraining risico
    if atl > ctl * 1.25:
        overtraining_risk = "hoog"
    elif atl > ctl * 1.12:
        overtraining_risk = "matig"
    else:
        overtraining_risk = "laag"

    # CTL doel voor deze fase
    ctl_min, ctl_max = PHASE_CTL_TARGETS.get(phase, (50, 65))
    ctl_message = ""
    if ctl < ctl_min:
        ctl_message = f" CTL ({ctl}) onder streef ({ctl_min}–{ctl_max}) — iets meer volume gewenst."
    elif ctl > ctl_max:
        ctl_message = f" CTL ({ctl}) boven fase-streef — pas op voor overbelasting."

    deload_str = " [DELOAD WEEK]" if is_deload_week else ""
    message = (
        f"Fase: {phase.replace('_', ' ').title()}{deload_str} | "
        f"CTL {ctl} | ATL {atl} | TSB {tsb:+.0f} | "
        f"Weekdoel: {target_tss} TSS | "
        f"Nog {weeks_to_race} weken tot de race."
        + ctl_message
    )

    # Update build/deload state
    if is_deload_week:
        bd["consecutive_build_weeks"] = 0
        bd["last_deload_week"] = date.today().isoformat()
        bd["is_deload_week"] = True
    else:
        bd["consecutive_build_weeks"] = consecutive_build + 1
        bd["is_deload_week"] = False
    state["build_deload"] = bd

    # Progression: schuif stappen op na een build week (niet bij deload)
    prog = state.get("progression", {})
    if not is_deload_week:
        prog["threshold_step"] = prog.get("threshold_step", 1) + 1
        prog["sweetspot_step"] = prog.get("sweetspot_step", 1) + 1
        prog["over_unders_step"] = prog.get("over_unders_step", 1) + 1
        # Duurrit en easy spin worden elke 2 weken 5 min langer
        if (consecutive_build + 1) % 2 == 0:
            prog["endurance_spin_min"] = min(120, prog.get("endurance_spin_min", 60) + 5)
            prog["long_ride_min"] = min(150, prog.get("long_ride_min", 80) + 5)
        # Z2 run en long run variatie-index rotert
        prog["z2_run_variety_index"] = (prog.get("z2_run_variety_index", 0) + 1) % 4
        prog["long_run_variety_index"] = (prog.get("long_run_variety_index", 0) + 1) % 3
    state["progression"] = prog

    # Sla bijgewerkte waarden op
    load["ctl_estimate"] = ctl
    load["atl_estimate"] = atl
    load["tsb_estimate"] = tsb
    load["last_calculated"] = date.today().isoformat()
    load["weekly_tss_target"] = target_tss
    state["load"] = load
    _save_state(state)

    return {
        "ctl": ctl,
        "atl": atl,
        "tsb": tsb,
        "recommended_weekly_tss": target_tss,
        "max_single_session_tss": max_session_tss,
        "current_phase": phase,
        "week_number": state["week_number"],
        "weeks_to_race": weeks_to_race,
        "overtraining_risk": overtraining_risk,
        "is_deload_week": is_deload_week,
        "build_week": consecutive_build + 1 if not is_deload_week else 0,
        "volume_modifier": volume_modifier,
        "message": message,
    }


if __name__ == "__main__":
    result = analyze()
    print("\n=== Load Manager ===")
    print(f"CTL (fitheid):       {result['ctl']}")
    print(f"ATL (vermoeidheid):  {result['atl']}")
    print(f"TSB (vorm):          {result['tsb']:+.1f}")
    print(f"Fase:                {result['current_phase']}")
    print(f"Weken tot race:      {result['weeks_to_race']}")
    print(f"Weekdoel TSS:        {result['recommended_weekly_tss']}")
    print(f"Max sessie TSS:      {result['max_single_session_tss']}")
    print(f"Overtraining risico: {result['overtraining_risk']}")
    print(f"\n{result['message']}")
