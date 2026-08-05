"""Gewichtstrend — massa als prestatievariabele, niet als losse meting.

Loopprestatie schaalt bijna lineair met lichaamsmassa: de energiekost per
km is grotendeels het optillen van je eigen gewicht. De vuistregel uit de
duurloopliteratuur is dat 1% minder massa ongeveer 0,7-1% tijdwinst geeft
op de 10 km, mits het vet is en geen spier.

Eén weging zegt niets — dagvariatie van 1-2 kg (vocht, glycogeen, darm) is
groter dan de wekelijkse verandering die je wilt zien. Daarom rekent deze
module uitsluitend met voortschrijdende gemiddelden en een helling over
meerdere weken.
"""
from __future__ import annotations

from datetime import date, timedelta

# 1% massa -> dit percentage tijdwinst. Conservatief uit de bandbreedte
# 0,7-1,0 gekozen: liever een doel dat meevalt dan een dat tegenvalt.
PERF_GAIN_PER_PCT_MASS = 0.8

# Bovengrens voor verantwoord afvallen tijdens een trainingsblok. Sneller
# kost spiermassa en trainingskwaliteit — dan lever je op de klok in wat je
# op de weegschaal wint.
MAX_SAFE_LOSS_KG_PER_WEEK = 0.5

WINDOW_DAYS = 7


def _weights(days: int) -> list[tuple[date, float]]:
    import intervals_client as api
    end = date.today()
    rows = api.get_wellness(end - timedelta(days=days), end)
    out = []
    for row in rows or []:
        kg = row.get("weight")
        stamp = row.get("id") or row.get("date")
        if not kg or not stamp:
            continue
        try:
            out.append((date.fromisoformat(str(stamp)[:10]), float(kg)))
        except ValueError:
            continue
    return sorted(out)


def analyze(days: int = 56) -> dict:
    """Gewichtstrend over `days` dagen.

    Returns dict met ``latest``, ``avg_recent`` (7-daags), ``avg_prior``
    (de 7 dagen daarvóór), ``kg_per_week`` en ``n_measurements``. Zonder
    metingen zijn alle waardes None — de coach hoort dan te zwijgen over
    gewicht in plaats van te gokken.
    """
    series = _weights(days)
    if not series:
        return {"latest": None, "avg_recent": None, "avg_prior": None,
                "kg_per_week": None, "n_measurements": 0,
                "message": "Geen gewichtsmetingen — trend niet te bepalen."}

    today = date.today()
    recent = [kg for d, kg in series if (today - d).days < WINDOW_DAYS]
    prior = [kg for d, kg in series
             if WINDOW_DAYS <= (today - d).days < 2 * WINDOW_DAYS]

    avg_recent = round(sum(recent) / len(recent), 1) if recent else None
    avg_prior = round(sum(prior) / len(prior), 1) if prior else None
    kg_per_week = (round(avg_recent - avg_prior, 2)
                   if avg_recent is not None and avg_prior is not None
                   else None)

    return {
        "latest": series[-1][1],
        "latest_date": series[-1][0].isoformat(),
        "avg_recent": avg_recent,
        "avg_prior": avg_prior,
        "kg_per_week": kg_per_week,
        "n_measurements": len(series),
        "message": _message(avg_recent, kg_per_week, len(series)),
    }


def seconds_per_km_from_loss(current_kg: float, target_kg: float,
                             current_pace_sec: float) -> float:
    """Hoeveel sneller per km wordt een pace bij `target_kg`?

    Positief = winst. Geen belofte, een schatting: massa is één van de
    variabelen, en alleen als de rest gelijk blijft.
    """
    if current_kg <= 0 or current_pace_sec <= 0 or target_kg >= current_kg:
        return 0.0
    pct_mass = (current_kg - target_kg) / current_kg * 100
    return round(current_pace_sec * (pct_mass * PERF_GAIN_PER_PCT_MASS) / 100, 1)


def target_kg_for_pace(current_kg: float, current_pace_sec: float,
                       goal_pace_sec: float) -> float | None:
    """Welk gewicht hoort bij `goal_pace_sec`, als de vorm gelijk blijft?

    Bewust de pessimistische lezing: alles uit massa halen. In de praktijk
    levert het trainingsblok een deel, dus dit is de bovengrens van wat je
    zou moeten afvallen — niet het advies.
    """
    if goal_pace_sec >= current_pace_sec or current_pace_sec <= 0:
        return None
    pct_gain = (current_pace_sec - goal_pace_sec) / current_pace_sec * 100
    pct_mass = pct_gain / PERF_GAIN_PER_PCT_MASS
    return round(current_kg * (1 - pct_mass / 100), 1)


def _message(avg_recent, kg_per_week, n) -> str:
    if avg_recent is None:
        return (f"{n} meting(en), nog geen volledige week — trend volgt "
                f"zodra er 7 dagen staan.")
    if kg_per_week is None:
        return f"7-daags gemiddelde {avg_recent} kg. Trend na twee volle weken."
    if kg_per_week < -MAX_SAFE_LOSS_KG_PER_WEEK:
        return (f"{avg_recent} kg, {abs(kg_per_week)} kg/week eraf — sneller "
                f"dan {MAX_SAFE_LOSS_KG_PER_WEEK} kg/week kost spiermassa en "
                f"trainingskwaliteit.")
    if kg_per_week < -0.05:
        return f"{avg_recent} kg, {abs(kg_per_week)} kg/week eraf — verantwoord tempo."
    if kg_per_week > 0.05:
        return f"{avg_recent} kg, {kg_per_week} kg/week erbij."
    return f"{avg_recent} kg, stabiel."
