"""
Injury Guard — bewaakt blessure-signalen en geeft rood/geel/groen stoplicht.

Alle andere agents RESPECTEREN dit stoplicht. Geen enkele agent plant intensiteit
in als de Injury Guard rood of geel is (voor loopintensiteit).

Blessure context Dennis:
- Gluteus medius zwakte links → heupinstabiliteit
- Knie reageert op loopintensiteit (bewezen: 10×1min → directe kniereactie)
- Lage rugpijn richting stuitje bij tempo-inspanning
- Hip mobiliteit beperkt → been draait naar buiten
"""

import json
from datetime import date, timedelta
from pathlib import Path

STATE_PATH = Path(__file__).parent.parent / "state.json"

# Bekende injury-signalen en hun gewicht
SIGNAL_WEIGHTS = {
    "knie_pijn": 10,
    "knie_twinge": 5,
    "knie_ongemak": 3,
    "rug_pijn": 8,
    "rug_trekkend": 5,
    "heup_instabiel": 6,
    "heup_pijn": 7,
    "been_uitdraaien": 4,
    "soreness_hoog": 3,
    "hrv_dalend": 2,
}

# Signalen die direct loopintensiteit verbieden
INTENSITY_BLOCKERS = {"knie_pijn", "knie_twinge", "rug_pijn", "heup_pijn"}

# Signalen die kracht verbieden
STRENGTH_BLOCKERS = {"rug_pijn", "heup_pijn"}


def _load_state() -> dict:
    with open(STATE_PATH) as f:
        return json.load(f)


def _save_state(state: dict) -> None:
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=4, ensure_ascii=False)


def _days_since(date_str: str | None) -> int:
    """Bereken hoeveel dagen geleden een datum was."""
    if not date_str:
        return 999
    d = date.fromisoformat(date_str)
    return (date.today() - d).days


def analyze(wellness_data: list = None, activities: list = None, feedback_signals: list = None) -> dict:
    """
    Analyseer injury-status en geef stoplicht terug.

    Args:
        wellness_data: Wellness records van afgelopen 14 dagen
        activities: Activiteiten van afgelopen 7 dagen
        feedback_signals: Lijst van signalen uit feedback (bijv. ["knie_pijn", "rug_trekkend"])

    Returns:
        dict met status, flags en aanbevelingen
    """
    state = _load_state()
    injury = state["injury"]

    active_signals = list(injury.get("active_signals", []))
    last_signal_date = injury.get("last_signal_date")
    days_symptom_free = injury.get("days_symptom_free", 0)

    flags = []
    volume_modifier = 1.0

    # Verwerk nieuwe feedback-signalen
    if feedback_signals:
        for sig in feedback_signals:
            if sig not in active_signals:
                active_signals.append(sig)
        last_signal_date = date.today().isoformat()
        days_symptom_free = 0
        injury["active_signals"] = active_signals
        injury["last_signal_date"] = last_signal_date
        injury["days_symptom_free"] = 0
        # Sla op in history
        injury["history"].append({
            "date": date.today().isoformat(),
            "signals": feedback_signals
        })

    # Verwerk wellness data — soreness en HRV trend
    if wellness_data:
        soreness_values = [w.get("soreness") for w in wellness_data if w.get("soreness") is not None]
        hrv_values = [w.get("hrv_rmssd") for w in wellness_data if w.get("hrv_rmssd") is not None]

        if soreness_values:
            avg_soreness = sum(soreness_values) / len(soreness_values)
            if avg_soreness >= 4:
                flags.append("soreness_hoog")
                volume_modifier = min(volume_modifier, 0.85)

        if len(hrv_values) >= 5:
            recent_hrv = sum(hrv_values[-3:]) / 3
            older_hrv = sum(hrv_values[:3]) / 3
            if recent_hrv < older_hrv * 0.92:
                flags.append("hrv_dalend")
                volume_modifier = min(volume_modifier, 0.90)

    # Bepaal hoe oud de laatste klacht is
    days_since_signal = _days_since(last_signal_date)

    # Verwijder verlopen signalen (ouder dan 14 dagen zonder nieuwe melding)
    if days_since_signal > 14:
        active_signals = []
        injury["active_signals"] = []

    # Combineer signalen voor stoplicht beslissing
    all_signals = set(active_signals) | set(flags)

    # Bereken dagen symptoomvrij (update dagelijks)
    if not active_signals and not any(s in INTENSITY_BLOCKERS for s in flags):
        if last_signal_date:
            days_symptom_free = max(days_since_signal, days_symptom_free)
        else:
            days_symptom_free = days_symptom_free + 1
        injury["days_symptom_free"] = days_symptom_free

    # STOPLICHT BEPALEN
    has_intensity_blocker = any(s in INTENSITY_BLOCKERS for s in all_signals)
    has_strength_blocker = any(s in STRENGTH_BLOCKERS for s in all_signals)
    recent_signal = days_since_signal <= 3
    semi_recent_signal = days_since_signal <= 7

    if has_intensity_blocker and recent_signal:
        status = "rood"
        run_intensity_allowed = False
        bike_intensity_allowed = False
        strength_allowed = not has_strength_blocker
        volume_modifier = min(volume_modifier, 0.70)
        message = (
            f"ROOD: Actieve klacht gemeld {days_since_signal} dag(en) geleden. "
            "Geen intensiteit, volume -30%. Alleen Z1 lopen. Fokus op rehab."
        )
    elif has_intensity_blocker and semi_recent_signal:
        status = "geel"
        run_intensity_allowed = False
        bike_intensity_allowed = True
        strength_allowed = not has_strength_blocker
        volume_modifier = min(volume_modifier, 0.85)
        message = (
            f"GEEL: Klacht {days_since_signal} dag(en) geleden. "
            "Geen loopintensiteit, fiets-intensiteit OK. Volume licht verlaagd."
        )
    elif semi_recent_signal and not has_intensity_blocker:
        status = "geel"
        run_intensity_allowed = False
        bike_intensity_allowed = True
        strength_allowed = True
        volume_modifier = min(volume_modifier, 0.90)
        message = (
            f"GEEL: Lichte signalen {days_since_signal} dag(en) geleden. "
            "Voorzichtig opbouwen, geen loopintensiteit."
        )
    else:
        status = "groen"
        run_intensity_allowed = False  # Standaard: intensiteit pas na ontgrendeling
        bike_intensity_allowed = True
        strength_allowed = True
        message = f"GROEN: {days_symptom_free} symptoomvrije dag(en)."

    # Intensiteitsontgrendeling
    strides_unlocked = days_symptom_free >= 14
    tempo_unlocked = days_symptom_free >= 21

    if status == "groen":
        if strides_unlocked:
            run_intensity_allowed = True  # Strides toegestaan
            message += " Strides mogen."
        if tempo_unlocked:
            message += " Tempolopen mogen."
        if not strides_unlocked:
            message += f" Strides na {14 - days_symptom_free} symptoomvrije dag(en)."

    # Update state
    injury["strides_unlocked"] = strides_unlocked
    injury["tempo_unlocked"] = tempo_unlocked
    injury["run_intensity_unlocked"] = run_intensity_allowed
    state["injury"] = injury
    _save_state(state)

    return {
        "status": status,
        "run_intensity_allowed": run_intensity_allowed,
        "strides_allowed": strides_unlocked and status == "groen",
        "tempo_allowed": tempo_unlocked and status == "groen",
        "bike_intensity_allowed": bike_intensity_allowed,
        "strength_allowed": strength_allowed,
        "volume_modifier": volume_modifier,
        "days_symptom_free": days_symptom_free,
        "days_since_last_signal": days_since_signal,
        "active_signals": active_signals,
        "flags": flags,
        "message": message,
    }


if __name__ == "__main__":
    result = analyze()
    print("\n=== Injury Guard ===")
    print(f"Status:             {result['status'].upper()}")
    print(f"Loopintensiteit:    {'✅' if result['run_intensity_allowed'] else '❌'}")
    print(f"Strides:            {'✅' if result['strides_allowed'] else '❌'}")
    print(f"Tempolopen:         {'✅' if result['tempo_allowed'] else '❌'}")
    print(f"Fiets intensiteit:  {'✅' if result['bike_intensity_allowed'] else '❌'}")
    print(f"Krachttraining:     {'✅' if result['strength_allowed'] else '❌'}")
    print(f"Volume modifier:    {result['volume_modifier']:.0%}")
    print(f"Symptoomvrij:       {result['days_symptom_free']} dagen")
    print(f"\n{result['message']}")
