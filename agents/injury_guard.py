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

# Signalen die DIRECT ingrijpen vereisen (gewrichtsklachten, potentiële blessure)
# Geen tolerantie-buffer, direct stoplicht aanpassen.
DIRECT_SIGNALS = {"knie_pijn", "heup_pijn", "rug_pijn"}

# Signalen die door de tolerantie-buffer gaan (vermoeidheid, normaal trainingsgevoel)
# Pas escaleren na 3x binnen 7 dagen.
BUFFERED_SIGNALS = {
    "knie_twinge", "knie_ongemak", "rug_trekkend", "heup_instabiel",
    "been_uitdraaien", "soreness_hoog", "hrv_dalend",
    "sessie_te_zwaar", "hr_te_hoog", "energie_laag",
}

BUFFER_THRESHOLD = 3   # aantal signalen binnen het window
BUFFER_WINDOW_DAYS = 7  # rolling window in dagen

# Signalen die loopintensiteit verbieden (na buffer of direct)
INTENSITY_BLOCKERS = {"knie_pijn", "knie_twinge", "rug_pijn", "heup_pijn"}

# Signalen die kracht verbieden
STRENGTH_BLOCKERS = {"rug_pijn", "heup_pijn"}


def _load_state() -> dict:
    with open(STATE_PATH) as f:
        return json.load(f)


def _save_state(state: dict) -> None:
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def _days_since(date_str: str | None) -> int:
    """Bereken hoeveel dagen geleden een datum was."""
    if not date_str:
        return 999
    d = date.fromisoformat(date_str)
    return (date.today() - d).days


def _get_buffer(state: dict) -> dict:
    """Haal de signal_buffer op uit state, initialiseer als die niet bestaat."""
    if "signal_buffer" not in state:
        state["signal_buffer"] = {}
    return state["signal_buffer"]


def _add_to_buffer(buffer: dict, signal: str, signal_date: str = None) -> None:
    """Voeg een signaal toe aan de buffer. Eén entry per dag per signaal."""
    if signal_date is None:
        signal_date = date.today().isoformat()
    if signal not in buffer:
        buffer[signal] = []
    if signal_date not in buffer[signal]:
        buffer[signal].append(signal_date)


def _buffer_exceeded(buffer: dict, signal: str) -> bool:
    """Check of een buffered signaal de drempel heeft bereikt (3 unieke dagen in 7 dagen)."""
    if signal not in buffer:
        return False
    cutoff = (date.today() - timedelta(days=BUFFER_WINDOW_DAYS)).isoformat()
    recent = sorted(set(d for d in buffer[signal] if d >= cutoff))
    buffer[signal] = recent  # cleanup oude entries
    return len(recent) >= BUFFER_THRESHOLD


def _any_buffer_exceeded(buffer: dict) -> list[str]:
    """Geef alle buffered signalen terug die de drempel hebben bereikt."""
    return [sig for sig in buffer if _buffer_exceeded(buffer, sig)]


def analyze(wellness_data: list = None, activities: list = None, feedback_signals: list = None) -> dict:
    """
    Analyseer injury-status en geef stoplicht terug.

    Twee sporen:
    - DIRECT signalen (knie_pijn, heup_pijn, rug_pijn): onmiddellijk stoplicht
    - BUFFERED signalen (vermoeidheid, stijfheid, etc.): pas na 3x in 7 dagen

    Args:
        wellness_data: Wellness records van afgelopen 14 dagen
        activities: Activiteiten van afgelopen 7 dagen
        feedback_signals: Lijst van signalen uit feedback (bijv. ["knie_pijn", "rug_trekkend"])

    Returns:
        dict met status, flags en aanbevelingen
    """
    state = _load_state()
    injury = state["injury"]
    buffer = _get_buffer(state)

    active_signals = list(injury.get("active_signals", []))
    last_signal_date = injury.get("last_signal_date")
    days_symptom_free = injury.get("days_symptom_free", 0)

    flags = []
    volume_modifier = 1.0
    direct_triggered = []
    buffered_noted = []

    # Verwerk nieuwe feedback-signalen via twee sporen
    if feedback_signals:
        for sig in feedback_signals:
            if sig in DIRECT_SIGNALS:
                # Pad 1: direct ingrijpen
                if sig not in active_signals:
                    active_signals.append(sig)
                direct_triggered.append(sig)
                last_signal_date = date.today().isoformat()
                days_symptom_free = 0
            elif sig in BUFFERED_SIGNALS:
                # Pad 2: in de buffer, pas escaleren na drempel
                _add_to_buffer(buffer, sig)
                buffered_noted.append(sig)
            else:
                # Onbekend signaal → buffer
                _add_to_buffer(buffer, sig)
                buffered_noted.append(sig)

        # Sla directe signalen op
        if direct_triggered:
            injury["active_signals"] = active_signals
            injury["last_signal_date"] = last_signal_date
            injury["days_symptom_free"] = 0
            injury["history"].append({
                "date": date.today().isoformat(),
                "signals": direct_triggered,
                "type": "direct"
            })

        if buffered_noted:
            injury["history"].append({
                "date": date.today().isoformat(),
                "signals": buffered_noted,
                "type": "buffered"
            })

    # Verwerk wellness data — soreness en HRV trend (buffered)
    if wellness_data:
        soreness_values = [w.get("soreness") for w in wellness_data if w.get("soreness") is not None]
        hrv_values = [w.get("hrv_rmssd") for w in wellness_data if w.get("hrv_rmssd") is not None]

        if soreness_values:
            avg_soreness = sum(soreness_values) / len(soreness_values)
            if avg_soreness >= 4:
                _add_to_buffer(buffer, "soreness_hoog")

        if len(hrv_values) >= 5:
            recent_hrv = sum(hrv_values[-3:]) / 3
            older_hrv = sum(hrv_values[:3]) / 3
            if recent_hrv < older_hrv * 0.92:
                _add_to_buffer(buffer, "hrv_dalend")

    # Check welke buffered signalen de drempel hebben bereikt
    escalated = _any_buffer_exceeded(buffer)
    if escalated:
        flags.extend(escalated)
        # Buffered signalen die escaleren → behandelen als semi-actief
        for sig in escalated:
            if sig not in active_signals:
                active_signals.append(sig)
        last_signal_date = last_signal_date or date.today().isoformat()
        injury["active_signals"] = active_signals

    # Wellness signalen die NIET geëscaleerd zijn: noteer maar grijp niet in
    non_escalated_buffer = [sig for sig in buffer if not _buffer_exceeded(buffer, sig) and buffer[sig]]
    if non_escalated_buffer:
        cutoff = (date.today() - timedelta(days=BUFFER_WINDOW_DAYS)).isoformat()
        for sig in non_escalated_buffer:
            count = len([d for d in buffer[sig] if d >= cutoff])
            if count > 0:
                flags.append(f"{sig}_noted_{count}x")

    # Sla buffer op
    state["signal_buffer"] = buffer

    # Bepaal hoe oud de laatste klacht is
    days_since_signal = _days_since(last_signal_date)

    # Verwijder verlopen signalen (ouder dan 14 dagen zonder nieuwe melding)
    if days_since_signal > 14:
        active_signals = []
        injury["active_signals"] = []

    # Combineer signalen voor stoplicht beslissing
    all_signals = set(active_signals) | set(s for s in flags if not s.endswith("x"))

    # Bereken dagen symptoomvrij (update dagelijks)
    if not active_signals and not any(s in INTENSITY_BLOCKERS for s in flags):
        if last_signal_date:
            days_symptom_free = max(days_since_signal, days_symptom_free)
        else:
            days_symptom_free = days_symptom_free + 1
        injury["days_symptom_free"] = days_symptom_free

    # STOPLICHT BEPALEN
    has_direct_blocker = any(s in DIRECT_SIGNALS for s in all_signals)
    has_intensity_blocker = any(s in INTENSITY_BLOCKERS for s in all_signals)
    has_strength_blocker = any(s in STRENGTH_BLOCKERS for s in all_signals)
    recent_signal = days_since_signal <= 3
    semi_recent_signal = days_since_signal <= 7
    has_escalated_buffer = bool(escalated)

    if has_direct_blocker and recent_signal:
        status = "rood"
        run_intensity_allowed = False
        bike_intensity_allowed = False
        strength_allowed = not has_strength_blocker
        volume_modifier = min(volume_modifier, 0.70)
        message = (
            f"ROOD: Gewrichtsklacht gemeld {days_since_signal} dag(en) geleden. "
            "Geen intensiteit, volume -30%. Alleen Z1 lopen. Fokus op rehab."
        )
    elif has_direct_blocker and semi_recent_signal:
        status = "geel"
        run_intensity_allowed = False
        bike_intensity_allowed = True
        strength_allowed = not has_strength_blocker
        volume_modifier = min(volume_modifier, 0.85)
        message = (
            f"GEEL: Gewrichtsklacht {days_since_signal} dag(en) geleden. "
            "Geen loopintensiteit, fiets-intensiteit OK."
        )
    elif has_escalated_buffer:
        status = "geel"
        run_intensity_allowed = False
        bike_intensity_allowed = True
        strength_allowed = True
        volume_modifier = min(volume_modifier, 0.90)
        message = (
            f"GEEL: Patroon gedetecteerd — {', '.join(escalated)} "
            f"({BUFFER_THRESHOLD}x in {BUFFER_WINDOW_DAYS} dagen). "
            "Tijd voor een rustiger week."
        )
    elif has_intensity_blocker and semi_recent_signal:
        status = "geel"
        run_intensity_allowed = False
        bike_intensity_allowed = True
        strength_allowed = True
        volume_modifier = min(volume_modifier, 0.90)
        message = (
            f"GEEL: Lichte signalen {days_since_signal} dag(en) geleden. "
            "Voorzichtig opbouwen."
        )
    else:
        status = "groen"
        run_intensity_allowed = False
        bike_intensity_allowed = True
        strength_allowed = True
        buffer_notes = [s for s in flags if s.endswith("x")]
        if buffer_notes:
            message = f"GROEN: {days_symptom_free} symptoomvrije dag(en). Enkele notities gelogd, geen actie nodig."
        else:
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
