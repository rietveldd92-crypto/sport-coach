"""aerobic_efficiency — pace bij vaste hartslag als progressiemarker.

Waarom niet gewoon efficiency factor: EF middelt over de hele run. Een lange
duurloop met een hard eindblok trekt zijn eigen gemiddelde hartslag omhoog, dus
de EF zakt terwijl de aerobe motor juist beter werd. Op 2 augustus 2026 leverde
dat precies de verkeerde conclusie op — EF stond drie duurlopen lang stil op
2,50-2,55, terwijl de pace bij 145 bpm in twee weken 19 s/km verbeterde.

Wat deze module doet: uit de seconde-voor-seconde streams de gemiddelde
snelheid pakken over álle momenten waarop de hartslag in een smalle band zat.
Dat is intensiteitsonafhankelijk — het maakt niet uit hoe de rest van de run
eruitzag, want die tellen we niet mee.

Drie voorwaarden waar de meting op staat of valt:
  * De eerste minuten gaan eraf. Hartslag loopt achter op inspanning, dus
    tijdens het inlopen zit je in de band bij een pace die niets zegt.
  * Kwaliteitssessies doen niet mee. Hun dribbelpauzes vallen ook in de band,
    maar op een pace die niets met aerobe efficiëntie te maken heeft.
  * Onder een minimum aan seconden in de band rapporteren we niets. Naarmate
    hij fitter wordt zakt de tijd in de band vanzelf (bij Dennis van 1974s in
    mei naar 540s in augustus) — dat is zelf een signaal, maar het maakt de
    meting ook dunner.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

# Standaardband rond het easy-plafond van 145 bpm. Smal genoeg om
# intensiteitsverschillen buiten te sluiten, breed genoeg om data te vangen.
HR_LOW = 142
HR_HIGH = 150

# De eerste 10 minuten tellen niet mee: hartslag loopt achter op inspanning.
WARMUP_SKIP_SEC = 600

# Minimum aantal seconden in de band voor een bruikbare meting.
MIN_SAMPLES_SEC = 180

# Runs korter dan dit zijn te kort om een stabiele aerobe fase te hebben.
MIN_DURATION_SEC = 40 * 60

# Onder deze snelheid sta je stil (verkeerslicht, drinken) — dat zou de
# gemiddelde pace kunstmatig omlaag trekken.
MIN_SPEED_MS = 1.5

# Kwaliteitssessies uitsluiten: hun dribbelpauzes zitten ook in de HR-band.
_QUALITY_WORDS = (
    "drempel", "threshold", "vo2max", "interval", "tempo", "cruise",
    "marathon-specifiek", "over-under", "strides", "speed economy", "yasso",
)


def is_quality_run(activity: dict) -> bool:
    naam = (activity.get("name") or "").lower()
    return any(w in naam for w in _QUALITY_WORDS)


def _streams(activity_id: str) -> dict:
    """Streams als dict per type. De API geeft een lijst van {type, data}.

    Alleen de twee streams die we nodig hebben opvragen: zonder `types` stuurt
    intervals.icu alle vijftien terug (watts, latlng, respiration, stance_time,
    …), en dat is bij een rit van twee uur zo'n 100.000 waarden die we
    weggooien. Zelfde patroon als workout_analysis._hr_per_rep.
    """
    import intervals_client as api

    raw = api.get_activity_streams(
        activity_id, types=["velocity_smooth", "heartrate"])
    if isinstance(raw, dict):
        return raw
    return {s.get("type"): (s.get("data") or []) for s in raw or []}


def measure(activity: dict, hr_low: int = HR_LOW, hr_high: int = HR_HIGH,
            use_cache: bool = True) -> Optional[dict]:
    """Meet pace bij vaste hartslag voor één activiteit.

    Returns ``{"date", "pace_sec", "samples_sec", "distance_km", "usable"}``,
    of None als de activiteit sowieso niet in aanmerking komt (geen run, te
    kort, kwaliteitssessie).
    """
    if (activity.get("type") or "") != "Run":
        return None
    if (activity.get("moving_time") or 0) < MIN_DURATION_SEC:
        return None
    if is_quality_run(activity):
        return None

    act_id = str(activity.get("id") or "")
    act_date = (activity.get("start_date_local") or "")[:10]
    if not act_id or not act_date:
        return None

    if use_cache:
        try:
            import history_db

            cached = history_db.get_aerobic_efficiency(act_id, hr_low, hr_high)
            if cached:
                return {
                    "date": cached["activity_date"],
                    "pace_sec": cached["pace_sec"],
                    "samples_sec": cached["samples_sec"],
                    "distance_km": cached["distance_km"],
                    "usable": cached["pace_sec"] is not None,
                }
        except Exception:
            pass  # cache is een optimalisatie, nooit een blokkade

    try:
        st = _streams(act_id)
    except Exception:
        return None

    hr = st.get("heartrate") or []
    vel = st.get("velocity_smooth") or []
    n = min(len(hr), len(vel))
    if n <= WARMUP_SKIP_SEC:
        return None

    speeds = [
        vel[i] for i in range(WARMUP_SKIP_SEC, n)
        if hr[i] and hr_low <= hr[i] <= hr_high
        and vel[i] and vel[i] > MIN_SPEED_MS
    ]

    samples = len(speeds)
    pace_sec = None
    if samples >= MIN_SAMPLES_SEC:
        pace_sec = int(round(1000 / (sum(speeds) / samples)))

    km = round((activity.get("distance") or 0) / 1000, 2) or None
    try:
        import history_db

        history_db.record_aerobic_efficiency(
            act_id, activity_date=act_date, hr_low=hr_low, hr_high=hr_high,
            pace_sec=pace_sec, samples_sec=samples, distance_km=km,
        )
    except Exception:
        pass

    return {"date": act_date, "pace_sec": pace_sec, "samples_sec": samples,
            "distance_km": km, "usable": pace_sec is not None}


def build_trend(activities: list[dict], hr_low: int = HR_LOW,
                hr_high: int = HR_HIGH) -> list[dict]:
    """Bruikbare metingen uit een lijst activiteiten, oplopend op datum."""
    metingen = []
    for act in activities or []:
        m = measure(act, hr_low, hr_high)
        if m and m["usable"]:
            metingen.append(m)
    return sorted(metingen, key=lambda m: m["date"])


def _slope_sec_per_week(metingen: list[dict]) -> Optional[float]:
    """Kleinste-kwadraten helling in seconden/km per week. Negatief = sneller."""
    if len(metingen) < 3:
        return None
    dagen, paces = [], []
    d0 = date.fromisoformat(metingen[0]["date"])
    for m in metingen:
        dagen.append((date.fromisoformat(m["date"]) - d0).days)
        paces.append(float(m["pace_sec"]))

    n = len(dagen)
    mean_x = sum(dagen) / n
    mean_y = sum(paces) / n
    noemer = sum((x - mean_x) ** 2 for x in dagen)
    if noemer == 0:
        return None
    teller = sum((x - mean_x) * (y - mean_y) for x, y in zip(dagen, paces))
    return (teller / noemer) * 7


def fmt_pace(sec: float | int | None) -> str:
    if not sec:
        return "-"
    m, s = divmod(int(round(sec)), 60)
    return f"{m}:{s:02d}/km"


def analyze(activities: list[dict], hr_low: int = HR_LOW,
            hr_high: int = HR_HIGH) -> dict:
    """Volledige analyse: metingen, trend en oordeel.

    Returns een dict met ``metingen``, ``huidig``, ``vorige``, ``delta_sec``,
    ``slope_sec_per_week``, ``richting`` en ``samenvatting``.
    """
    metingen = build_trend(activities, hr_low, hr_high)
    result = {
        "hr_band": (hr_low, hr_high),
        "metingen": metingen,
        "huidig": None,
        "vorige": None,
        "delta_sec": None,
        "slope_sec_per_week": None,
        "richting": "onbekend",
        "samenvatting": "",
    }

    if not metingen:
        result["samenvatting"] = (
            f"Nog geen bruikbare meting in de band {hr_low}-{hr_high} bpm "
            f"(minimaal {MIN_SAMPLES_SEC}s nodig, kwaliteitssessies tellen niet mee)."
        )
        return result

    result["huidig"] = metingen[-1]
    if len(metingen) >= 2:
        result["vorige"] = metingen[-2]
        result["delta_sec"] = metingen[-1]["pace_sec"] - metingen[-2]["pace_sec"]

    slope = _slope_sec_per_week(metingen)
    result["slope_sec_per_week"] = round(slope, 1) if slope is not None else None

    huidig = fmt_pace(metingen[-1]["pace_sec"])
    band = f"{hr_low}-{hr_high} bpm"

    if slope is None:
        result["richting"] = "te weinig data"
        result["samenvatting"] = (
            f"Pace @ {band}: {huidig} ({len(metingen)} meting(en) — "
            "vanaf 3 kan ik een trend berekenen)."
        )
        return result

    per4 = slope * 4
    if slope < -1.0:
        result["richting"] = "vooruit"
        oordeel = (f"aerobe motor gaat vooruit: {abs(per4):.0f} s/km sneller "
                   "per 4 weken bij dezelfde hartslag")
    elif slope > 1.0:
        result["richting"] = "achteruit"
        oordeel = (f"let op: {per4:.0f} s/km trager per 4 weken bij dezelfde "
                   "hartslag — vermoeidheid, hitte of te weinig aerobe prikkel")
    else:
        result["richting"] = "stabiel"
        oordeel = "vlak — geen meetbare aerobe winst of verlies"

    result["samenvatting"] = (
        f"Pace @ {band}: {huidig} over {len(metingen)} metingen. {oordeel}."
    )
    return result


def format_block(analysis: dict, breedte: int = 60) -> str:
    """Tekstblok voor coach.py en evaluate_week.py."""
    lo, hi = analysis["hr_band"]
    regels = [
        "─" * breedte,
        f"  AEROBE EFFICIENTIE — pace bij {lo}-{hi} bpm",
        "─" * breedte,
    ]
    metingen = analysis["metingen"]
    if not metingen:
        regels.append(f"  {analysis['samenvatting']}")
        return "\n".join(regels)

    TOON = 6
    if len(metingen) > TOON:
        regels.append(f"  ({len(metingen) - TOON} oudere meting(en) niet getoond)")
    for m in metingen[-TOON:]:
        km = f"{m['distance_km']:.1f} km" if m.get("distance_km") else ""
        regels.append(
            f"  {m['date']}  {fmt_pace(m['pace_sec']):>9}  "
            f"{km:>9}  ({m['samples_sec']}s in band)"
        )

    delta = analysis.get("delta_sec")
    if delta is not None:
        teken = "sneller" if delta < 0 else "trager" if delta > 0 else "gelijk"
        regels.append(f"\n  T.o.v. vorige meting: {abs(delta)}s/km {teken}.")

    regels.append(f"  {analysis['samenvatting']}")
    return "\n".join(regels)
