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

# Boven deze temperatuur is pace bij vaste hartslag niet vergelijkbaar: je
# hart pompt dan mede voor de koeling en niet alleen voor de spieren. We
# gooien zulke runs niet weg — ze staan wél in de reeks — maar ze tellen niet
# mee in de trend. Alleen toepasbaar als intervals.icu weerdata levert.
MAX_TEMP_C = 22.0

# De trend mag pas een trainingsbeslissing sturen als hij over een echt venster
# loopt. Een warme veertien dagen kan de pace tijdelijk drukken; drie weken en
# vijf metingen niet meer zomaar.
TREND_MIN_METINGEN = 5
TREND_MIN_SPAN_DAGEN = 21

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


def _activity_temp(activity: dict) -> Optional[float]:
    """Gemiddelde temperatuur, of None als intervals.icu er geen levert."""
    for key in ("average_weather_temp", "average_temp", "average_feels_like"):
        val = activity.get(key)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                continue
    return None


def _row(date_str, pace_sec, samples, km, temp) -> dict:
    return {
        "date": date_str,
        "pace_sec": pace_sec,
        "samples_sec": samples,
        "distance_km": km,
        "temp_c": temp,
        "usable": pace_sec is not None,
        "te_warm": temp is not None and temp > MAX_TEMP_C,
    }


def measure(activity: dict, hr_low: int = HR_LOW, hr_high: int = HR_HIGH,
            use_cache: bool = True, errors: Optional[list] = None) -> Optional[dict]:
    """Meet pace bij vaste hartslag voor één activiteit.

    Returns een rij (zie ``_row``) of None als de activiteit niet in aanmerking
    komt: geen run, te kort, of een kwaliteitssessie.

    ``errors`` verzamelt, als je een lijst meegeeft, de activiteiten waarvan de
    streams niet op te halen waren. Zonder die lijst verdwijnt een API-storing
    stil en meldt de coach "geen bruikbare meting" terwijl er niets mis is met
    de training.
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

    temp = _activity_temp(activity)

    if use_cache:
        try:
            import history_db

            cached = history_db.get_aerobic_efficiency(act_id, hr_low, hr_high)
            if cached:
                return _row(cached["activity_date"], cached["pace_sec"],
                            cached["samples_sec"], cached["distance_km"],
                            cached["temp_c"] if cached["temp_c"] is not None else temp)
        except Exception as exc:
            if errors is not None:
                errors.append(f"{act_date}: cache niet leesbaar ({exc})")

    try:
        st = _streams(act_id)
    except Exception as exc:
        if errors is not None:
            errors.append(f"{act_date}: streams niet op te halen ({exc})")
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
            temp_c=temp,
        )
    except Exception as exc:
        if errors is not None:
            errors.append(f"{act_date}: meting niet op te slaan ({exc})")

    return _row(act_date, pace_sec, samples, km, temp)


def build_trend(activities: list[dict], hr_low: int = HR_LOW,
                hr_high: int = HR_HIGH,
                errors: Optional[list] = None) -> list[dict]:
    """Bruikbare metingen uit een lijst activiteiten, oplopend op datum."""
    metingen = []
    for act in activities or []:
        m = measure(act, hr_low, hr_high, errors=errors)
        if m and m["usable"]:
            metingen.append(m)
    return sorted(metingen, key=lambda m: m["date"])


def _trend_metingen(metingen: list[dict]) -> list[dict]:
    """De metingen die de trend mogen sturen: warme dagen tellen niet mee.

    Boven MAX_TEMP_C pompt je hart mede voor de koeling, dus pace bij vaste
    hartslag zakt zonder dat er iets met je conditie gebeurt. Onbekende
    temperatuur laten we staan — anders houdt niemand zonder weerkoppeling ooit
    een trend over.
    """
    return [m for m in metingen if not m.get("te_warm")]


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

    ``betrouwbaar_voor_besluit`` zegt of de trend zwaar genoeg weegt om een
    trainingsbeslissing te sturen. Dat vraagt meer dan een helling: genoeg
    metingen over een lang genoeg venster, zodat een warme veertien dagen of
    één rare run de week niet naar CONSOLIDATIE duwt.
    """
    fouten: list[str] = []
    metingen = build_trend(activities, hr_low, hr_high, errors=fouten)
    result = {
        "hr_band": (hr_low, hr_high),
        "metingen": metingen,
        "huidig": None,
        "vorige": None,
        "delta_sec": None,
        "slope_sec_per_week": None,
        "richting": "onbekend",
        "samenvatting": "",
        "fouten": fouten,
        "temp_bekend": False,
        "warme_metingen": 0,
        "betrouwbaar_voor_besluit": False,
    }

    if not metingen:
        basis = (f"Nog geen bruikbare meting in de band {hr_low}-{hr_high} bpm "
                 f"(minimaal {MIN_SAMPLES_SEC}s nodig, kwaliteitssessies tellen "
                 "niet mee).")
        if fouten:
            basis += (f" Let op: {len(fouten)} activiteit(en) konden niet "
                      "opgehaald worden — dit zegt dus niets over je training.")
        result["samenvatting"] = basis
        return result

    result["huidig"] = metingen[-1]
    if len(metingen) >= 2:
        result["vorige"] = metingen[-2]
        result["delta_sec"] = metingen[-1]["pace_sec"] - metingen[-2]["pace_sec"]

    # Warme dagen tellen niet mee in de trend: pace bij vaste hartslag zakt in
    # de hitte zonder dat je conditie verandert.
    trend_set = _trend_metingen(metingen)
    result["temp_bekend"] = any(m.get("temp_c") is not None for m in metingen)
    result["warme_metingen"] = len(metingen) - len(trend_set)

    slope = _slope_sec_per_week(trend_set)
    result["slope_sec_per_week"] = round(slope, 1) if slope is not None else None

    if slope is not None and len(trend_set) >= TREND_MIN_METINGEN:
        span = (date.fromisoformat(trend_set[-1]["date"])
                - date.fromisoformat(trend_set[0]["date"])).days
        result["betrouwbaar_voor_besluit"] = span >= TREND_MIN_SPAN_DAGEN

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

    delen = [f"Pace @ {band}: {huidig} over {len(metingen)} metingen. {oordeel}."]
    if result["warme_metingen"]:
        delen.append(f"{result['warme_metingen']} meting(en) boven "
                     f"{MAX_TEMP_C:.0f}°C niet meegeteld in de trend.")
    elif not result["temp_bekend"]:
        delen.append("Temperatuur onbekend (weerdata staat uit in intervals.icu) "
                     "— een warme periode kan de trend drukken.")
    if fouten:
        delen.append(f"{len(fouten)} activiteit(en) niet op te halen.")
    result["samenvatting"] = " ".join(delen)
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
