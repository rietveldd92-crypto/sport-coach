"""
evaluate_week.py — Wekelijkse evaluatie en herplanning.

De kern van het adaptieve systeem. Elke maandag draaien:
1. Terugblik op afgelopen week (activiteiten, CTL, wellness)
2. Beoordelen op 4 assen (blessure, belasting, faseprogressie, gevoel)
3. Komende week plannen op basis van het totaalplaatje

Gebruik:
    python evaluate_week.py                          # Volledig: evalueer + plan volgende week
    python evaluate_week.py --dry-run                # Alleen rapport, niet inplannen
    python evaluate_week.py --status                 # Huidige status zonder evaluatie
    python evaluate_week.py --feedback "kniepijn"    # Met feedback meegeven
"""

import sys
import json
import argparse
from datetime import date, timedelta
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import intervals_client as api
from agents import injury_guard, load_manager, marathon_periodizer

STATE_PATH = Path(__file__).parent / "state.json"


def _load_state() -> dict:
    with open(STATE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save_state(state: dict) -> None:
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def _last_monday() -> date:
    """Maandag van de afgelopen week."""
    today = date.today()
    return today - timedelta(days=today.weekday() + 7)


def _this_monday() -> date:
    """Maandag van deze week."""
    today = date.today()
    return today - timedelta(days=today.weekday())


def _next_monday() -> date:
    """Maandag van de komende week."""
    today = date.today()
    days_ahead = 7 - today.weekday()
    if days_ahead == 7:
        days_ahead = 0
    return today + timedelta(days=days_ahead)


# ── STAP 1: TERUGBLIK ──────────────────────────────────────────────────────

def fetch_review_data() -> dict:
    """Haal alle data op voor de terugblik van afgelopen week."""
    last_mon = _last_monday()
    last_sun = last_mon + timedelta(days=6)

    # Activiteiten afgelopen week
    try:
        week_activities = api.get_activities(start=last_mon, end=last_sun)
    except Exception as e:
        print(f"  Kan activiteiten niet ophalen: {e}")
        week_activities = []

    # Activiteiten 42 dagen voor CTL/ATL
    try:
        all_activities = api.get_activities(
            start=date.today() - timedelta(days=42), end=date.today()
        )
    except Exception:
        all_activities = []

    # Wellness afgelopen 14 dagen
    try:
        wellness = api.get_wellness(
            start=date.today() - timedelta(days=14), end=date.today()
        )
    except Exception:
        wellness = []

    # Bereken weekstatistieken
    week_tss = 0
    week_run_km = 0
    week_ride_km = 0
    run_count = 0
    ride_count = 0
    signal_words = []

    for act in week_activities:
        tss = act.get("icu_training_load") or act.get("training_load") or 0
        dist = (act.get("distance") or 0) / 1000
        act_type = act.get("type", "")
        name = (act.get("name") or "").lower()
        week_tss += tss

        if act_type == "Run":
            week_run_km += dist
            run_count += 1
        elif act_type in ("Ride", "VirtualRide"):
            week_ride_km += dist
            ride_count += 1

        # Zoek signaalwoorden in activiteitnamen
        for word in ["pijn", "gestopt", "knie", "rug", "heup", "afgebroken"]:
            if word in name:
                signal_words.append(f"{act.get('start_date_local', '')[:10]}: {act.get('name', '')}")

    # HRV trend
    hrv_values = [w.get("hrvRMSSD") or w.get("hrv") for w in wellness if w.get("hrvRMSSD") or w.get("hrv")]
    hrv_trend = "stabiel"
    if len(hrv_values) >= 6:
        recent = sum(hrv_values[-3:]) / 3
        older = sum(hrv_values[:3]) / 3
        if recent < older * 0.90:
            hrv_trend = "dalend"
        elif recent > older * 1.10:
            hrv_trend = "stijgend"

    return {
        "week_start": last_mon,
        "week_end": last_sun,
        "week_activities": week_activities,
        "all_activities": all_activities,
        "wellness": wellness,
        "week_tss": round(week_tss),
        "week_run_km": round(week_run_km, 1),
        "week_ride_km": round(week_ride_km, 1),
        "run_count": run_count,
        "ride_count": ride_count,
        "hrv_trend": hrv_trend,
        "hrv_values": hrv_values,
        "signal_words": signal_words,
    }


# ── STAP 2: BEOORDELING ────────────────────────────────────────────────────

def assess(review: dict, feedback: str = None) -> dict:
    """
    Beoordeel de afgelopen week op 4 assen.

    Returns:
        dict met blessure_status, belasting_beoordeling, fase_progressie,
        modus (PROGRESSIE/CONSOLIDATIE/TERUGSCHAKELEN), coaching_note
    """
    state = _load_state()

    # ── As 1: Blessuresignalen ──
    ig_result = injury_guard.analyze(
        wellness_data=review["wellness"],
        activities=review["all_activities"],
        feedback_signals=_parse_feedback_signals(feedback) if feedback else None,
    )

    # Check signaalwoorden in activiteiten
    activity_signals = review["signal_words"]
    if activity_signals and not ig_result.get("active_signals"):
        # Signaalwoorden in activiteiten maar geen expliciete feedback — waarschuwing
        ig_result["flags"].append("signaalwoorden_in_activiteiten")

    # ── As 2: Trainingsbelasting ──
    lm_result = load_manager.analyze(
        activities=review["all_activities"],
        injury_guard_output=ig_result,
    )

    ctl_now = lm_result["ctl"]
    ctl_prev = state["load"].get("ctl_estimate", ctl_now)
    ctl_growth = round(ctl_now - ctl_prev, 1)
    tsb = lm_result["tsb"]

    # Geplande vs werkelijke TSS
    planned_tss = 0
    if state["weekly_log"]:
        last_log = state["weekly_log"][-1]
        planned_tss = last_log.get("planned_tss") or last_log.get("geschat_tss") or 0
    execution_rate = round(review["week_tss"] / planned_tss * 100) if planned_tss > 0 else 100

    belasting = {
        "ctl_growth": ctl_growth,
        "ctl_too_fast": ctl_growth > 5,
        "ctl_too_slow": ctl_growth < 1 and review["week_tss"] > 0,
        "tsb_too_negative": tsb < -25,
        "execution_rate": execution_rate,
        "execution_low": execution_rate < 70,
    }

    # ── As 3: Faseprogressie ──
    phase_info = marathon_periodizer.get_current_phase()
    target_vol = marathon_periodizer.calculate_weekly_run_volume(phase_info["week_nummer"])
    km_target = target_vol["run_km_totaal"]
    km_actual = review["week_run_km"]
    km_achieved = round(km_actual / km_target * 100) if km_target > 0 else 100

    progressie = {
        "km_target": km_target,
        "km_actual": km_actual,
        "km_achieved_pct": km_achieved,
        "on_schedule": km_achieved >= 80,
        "strides_unlocked": ig_result.get("strides_allowed", False),
        "tempo_unlocked": ig_result.get("tempo_allowed", False),
    }

    # ── As 4: Gevoel & uitvoering (Delahaije) ──
    # Check of Z2 runs in de juiste zone waren (hartslag check)
    coaching_notes = []
    for act in review["week_activities"]:
        if act.get("type") == "Run":
            avg_hr = act.get("average_heartrate") or act.get("icu_average_hr")
            max_hr = act.get("max_heartrate") or act.get("icu_hr_max") or 190
            if avg_hr and max_hr:
                hr_pct = avg_hr / max_hr * 100
                if hr_pct > 82:  # boven Z2 bovengrens
                    coaching_notes.append(
                        f"Run op {act.get('start_date_local', '')[:10]} had gem. HR {avg_hr} bpm "
                        f"({hr_pct:.0f}% HRmax) — dit is boven Z2. Volgende keer rustiger."
                    )

    if review["hrv_trend"] == "dalend":
        coaching_notes.append("HRV is dalend de afgelopen week. Extra herstel overwegen.")

    # ── MODUS BEPALEN ──
    injury_status = ig_result["status"]
    if injury_status == "rood" or (feedback and _has_injury_keywords(feedback)):
        modus = "TERUGSCHAKELEN"
        modus_reden = "Blessuresignaal gedetecteerd — volume verlagen, alleen Z1."
    elif (belasting["tsb_too_negative"] or belasting["ctl_too_fast"]
          or belasting["execution_low"] or injury_status == "geel"):
        modus = "CONSOLIDATIE"
        reasons = []
        if belasting["tsb_too_negative"]:
            reasons.append(f"TSB te negatief ({tsb:+.0f})")
        if belasting["ctl_too_fast"]:
            reasons.append(f"CTL groeit te snel (+{ctl_growth}/week)")
        if belasting["execution_low"]:
            reasons.append(f"Uitvoeringsgraad laag ({execution_rate}%)")
        if injury_status == "geel":
            reasons.append("Injury Guard GEEL")
        modus_reden = "Consolidatie: " + ", ".join(reasons) + ". Zelfde volume als vorige week."
    else:
        modus = "PROGRESSIE"
        modus_reden = "Alles op schema. Volgende stap uit het periodiseringsplan."

    return {
        "injury_guard": ig_result,
        "load_manager": lm_result,
        "belasting": belasting,
        "progressie": progressie,
        "modus": modus,
        "modus_reden": modus_reden,
        "coaching_notes": coaching_notes,
        "ctl_growth": ctl_growth,
        "execution_rate": execution_rate,
        "planned_tss": planned_tss,
    }


def _parse_feedback_signals(feedback: str) -> list:
    """Extraheer injury signals uit feedback tekst."""
    if not feedback:
        return []
    fb = feedback.lower()
    signals = []
    if any(w in fb for w in ["kniepijn", "knie pijn", "knie doet pijn"]):
        signals.append("knie_pijn")
    elif any(w in fb for w in ["knie", "knie voelt", "knie trekt"]):
        signals.append("knie_twinge")
    if any(w in fb for w in ["rugpijn", "rug pijn", "onderrug", "stuitje"]):
        signals.append("rug_trekkend")
    if any(w in fb for w in ["heuppijn", "heup pijn", "heup instabiel"]):
        signals.append("heup_instabiel")
    return signals


def _has_injury_keywords(feedback: str) -> bool:
    """Check of feedback tekst injury-gerelateerde woorden bevat."""
    fb = feedback.lower()
    return any(w in fb for w in ["pijn", "knie", "gestopt", "afgebroken", "blessure"])


# ── STAP 3: RAPPORT & HERPLANNING ──────────────────────────────────────────

def print_report(review: dict, assessment: dict):
    """Print het wekelijkse evaluatierapport."""
    ig = assessment["injury_guard"]
    lm = assessment["load_manager"]
    bel = assessment["belasting"]
    prog = assessment["progressie"]
    phase = marathon_periodizer.get_current_phase()
    next_vol = marathon_periodizer.calculate_weekly_run_volume(
        min(28, phase["week_nummer"] + 1)
    )

    print("\n" + "=" * 55)
    print(f"  WEEK {phase['week_nummer']} EVALUATIE — {date.today()}")
    print("=" * 55)

    print("  TERUGBLIK")
    print("  " + "-" * 50)
    print(f"  Geplande TSS:     {assessment['planned_tss']}")
    print(f"  Werkelijke TSS:   {review['week_tss']}  "
          f"({assessment['execution_rate']}%"
          f"{' — goed' if assessment['execution_rate'] >= 80 else ' — laag'})")
    print(f"  CTL vorige week:  {lm['ctl'] - bel['ctl_growth']:.1f}")
    print(f"  CTL nu:           {lm['ctl']}  "
          f"({bel['ctl_growth']:+.1f}"
          f"{' — op schema' if 1 <= bel['ctl_growth'] <= 5 else ''})")
    print(f"  TSB nu:           {lm['tsb']:+.1f}")
    print(f"  Loop km:          {review['week_run_km']:.1f} km "
          f"({review['run_count']} runs)")
    print(f"  Fiets km:         {review['week_ride_km']:.1f} km "
          f"({review['ride_count']} rides)")
    print(f"  HRV trend:        {review['hrv_trend']}")
    if review['signal_words']:
        print(f"  Signaalwoorden:   {len(review['signal_words'])} gevonden")
        for s in review['signal_words']:
            print(f"    - {s}")
    else:
        print(f"  Blessuresignalen: geen")

    print(f"\n  BEOORDELING")
    print("  " + "-" * 50)
    print(f"  Injury Guard:     {ig['status'].upper()}")
    print(f"  Symptoomvrij:     {ig['days_symptom_free']} dagen")
    print(f"  Strides:          {'JA' if ig.get('strides_allowed') else 'NEE'}")
    print(f"  Tempolopen:       {'JA' if ig.get('tempo_allowed') else 'NEE'}")
    print(f"  Fase:             {phase['fase_label']} "
          f"(week {phase['week_in_fase']} van {phase['fase_label']})")
    print(f"  Volume bereikt:   {prog['km_actual']:.1f} / {prog['km_target']:.1f} km "
          f"({prog['km_achieved_pct']}%)")
    print(f"  Overtraining:     {lm['overtraining_risk']}")
    print(f"  Modus:            {assessment['modus']}")
    print(f"                    {assessment['modus_reden']}")

    print(f"\n  KOMENDE WEEK (wk {min(28, phase['week_nummer'] + 1)})")
    print("  " + "-" * 50)
    print(f"  Loopsessies:      {next_vol['run_sessies']}x "
          f"({next_vol['run_km_totaal']:.1f} km totaal)")
    if next_vol['km_per_korte_sessie'] > 0:
        print(f"  Korte runs:       {next_vol['korte_sessies']}x "
              f"{next_vol['km_per_korte_sessie']:.1f} km Z2")
    if next_vol['lange_duurloop_km'] > 0:
        print(f"  Lange duurloop:   {next_vol['lange_duurloop_km']:.0f} km")
    print(f"  Fietssessies:     {next_vol['fiets_sessies']}x "
          f"({next_vol['fiets_intensiteit']})")
    print(f"  TSS-doel:         ~{next_vol['totaal_tss']}")

    # Coaching note (Delahaije)
    if assessment["coaching_notes"]:
        print(f"\n  COACHING NOTES (Delahaije):")
        for note in assessment["coaching_notes"]:
            print(f"  - {note}")
    else:
        print(f"\n  COACHING NOTE (Delahaije):")
        print(f'  "Loop de Z2-sessies op gevoel. Als je hartslag stijgt door')
        print(f'   warmte of vermoeidheid, verlaag dan je tempo. De zone is')
        print(f'   leidend, niet de GPS-snelheid."')

    print("\n" + "=" * 55)


def plan_next_week(assessment: dict, dry_run: bool = True):
    """Plan de komende week in op basis van de beoordeling."""
    from plan_week import run as plan_week_run

    phase = marathon_periodizer.get_current_phase()
    next_week_num = min(28, phase["week_nummer"] + 1)
    next_monday = _next_monday()

    # Pas volume aan op basis van modus
    modus = assessment["modus"]
    skip_run_days = []

    if modus == "TERUGSCHAKELEN":
        # Volume -30%, extra rustdag
        print("\n  TERUGSCHAKELEN: Volume -30%, alleen Z1 hardlopen.")
        print("  Extra rustdag op zaterdag.")
        skip_run_days = ["zaterdag"]
    elif modus == "CONSOLIDATIE":
        print("\n  CONSOLIDATIE: Zelfde volume als vorige week herhalen.")

    print(f"\n  Planning week {next_week_num} ({next_monday})...")
    plan_week_run(next_monday, dry_run=dry_run, skip_run_days=skip_run_days)


# ── MAIN ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Sport Coach — wekelijkse evaluatie")
    parser.add_argument("--dry-run", action="store_true",
                        help="Alleen rapport, niet inplannen")
    parser.add_argument("--status", action="store_true",
                        help="Huidige status zonder evaluatie")
    parser.add_argument("--feedback", type=str, default=None,
                        help="Feedback meegeven (bijv. 'kniepijn bij km 5')")
    args = parser.parse_args()

    if args.status:
        from plan_week import print_status
        print_status()
        return

    print("\n  Data ophalen voor weekelijkse evaluatie...")
    review = fetch_review_data()
    assessment = assess(review, feedback=args.feedback)

    print_report(review, assessment)

    if args.dry_run:
        print("  [DRY RUN] Geen events geschreven naar intervals.icu.\n")
        return

    # Bevestiging vragen
    try:
        answer = input("  Schrijf komende week naar intervals.icu? (j/n): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = "n"

    if answer in ("j", "ja", "y", "yes"):
        plan_next_week(assessment, dry_run=False)
    else:
        print("  Geen wijzigingen. Herplan met: python evaluate_week.py")
        # Toon dry run van komende week
        plan_next_week(assessment, dry_run=True)


if __name__ == "__main__":
    main()
