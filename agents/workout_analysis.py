"""
Workout Analysis — workout-type specifieke analyse van voltooide trainingen.

Elke workout-type krijgt z'n eigen analyse die kijkt naar wat er echt toe doet:
- Threshold/Sweetspot: power consistency, HR drift, coupling
- Z2 runs: was het echt Z2? Klaar.
- Long run: pacing, cardiac decoupling, fueling
- Interval runs: pace consistency, recovery HR
"""

from datetime import date
import intervals_client as api

FTP = 290
HR_MAX = 190
HR_Z2_MAX = round(HR_MAX * 0.80)  # 152 bpm
HR_Z2_MIN = round(HR_MAX * 0.68)  # 129 bpm


def classify_workout(event: dict) -> str:
    """Bepaal het workout-type op basis van event naam en sport."""
    name = (event.get("name") or "").lower()
    sport = event.get("type", "")

    if sport in ("Ride", "VirtualRide"):
        if "over-under" in name or "over_under" in name:
            return "bike_over_unders"
        if "threshold" in name:
            return "bike_threshold"
        if "sweetspot" in name:
            return "bike_sweetspot"
        if "cadence" in name or "pyramids" in name:
            return "bike_cadence"
        if "single leg" in name:
            return "bike_drills"
        if "tempo" in name:
            return "bike_tempo"
        if "group ride" in name or "zwift" in name:
            return "bike_group"
        return "bike_endurance"

    if sport == "Run":
        if "lange duurloop" in name or "long run" in name:
            return "run_long"
        if "fartlek" in name:
            return "run_fartlek"
        if "progressie" in name or "progression" in name:
            return "run_progression"
        if "pickup" in name or "versnelling" in name:
            return "run_pickups"
        if "trail" in name or "bos" in name:
            return "run_trail"
        if "herstel" in name or "recovery" in name or "easy" in name:
            return "run_recovery"
        if "tempo" in name or "threshold" in name:
            return "run_tempo"
        if "interval" in name:
            return "run_intervals"
        return "run_z2"

    if sport == "WeightTraining":
        return "strength"

    return "unknown"


def analyze(event: dict, activity: dict) -> dict:
    """Analyseer een workout. Haalt extra data op als nodig.

    Returns een dict met:
    - workout_type: str
    - metrics: dict met type-specifieke metrieken
    - insights: list[str] met concrete observaties
    - prompt_focus: str met de specifieke vraag voor de AI coach
    """
    wtype = classify_workout(event)
    act_id = str(activity.get("id", ""))
    sport = event.get("type", "")

    # Basis metrieken die altijd beschikbaar zijn
    hr_avg = activity.get("average_heartrate") or activity.get("icu_average_hr") or 0
    hr_max_act = activity.get("max_heartrate") or activity.get("icu_hr_max") or 0
    hr_pct = round(hr_avg / HR_MAX * 100) if hr_avg else 0
    distance = round((activity.get("distance") or 0) / 1000, 1)
    duration = round((activity.get("moving_time") or activity.get("elapsed_time") or 0) / 60)
    tss = activity.get("icu_training_load") or 0
    avg_power = activity.get("average_watts") or activity.get("icu_average_watts")
    np_power = activity.get("icu_normalized_watts")
    cadence = activity.get("average_cadence") or activity.get("icu_average_cadence")
    hr_zones = activity.get("icu_hr_zone_times") or []  # seconden per zone
    target_tss = event.get("load_target") or 0

    # Variability Index
    vi = round(np_power / avg_power, 2) if np_power and avg_power else None

    base = {
        "hr_avg": hr_avg, "hr_pct": hr_pct, "hr_max_act": hr_max_act,
        "distance": distance, "duration": duration, "tss": tss,
        "avg_power": avg_power, "np_power": np_power, "vi": vi,
        "cadence": cadence, "hr_zones": hr_zones, "target_tss": target_tss,
    }

    # Dispatch per type
    if wtype.startswith("bike_threshold") or wtype.startswith("bike_sweetspot") or wtype == "bike_over_unders":
        return _analyze_bike_intensity(wtype, event, activity, act_id, base)
    elif wtype == "bike_endurance" or wtype == "bike_group":
        return _analyze_bike_endurance(wtype, event, activity, act_id, base)
    elif wtype == "bike_cadence" or wtype == "bike_drills":
        return _analyze_bike_drills(wtype, event, activity, act_id, base)
    elif wtype == "run_long":
        return _analyze_run_long(wtype, event, activity, act_id, base)
    elif wtype == "run_z2" or wtype == "run_recovery" or wtype == "run_trail":
        return _analyze_run_easy(wtype, event, activity, act_id, base)
    elif wtype == "run_fartlek" or wtype == "run_pickups" or wtype == "run_progression":
        return _analyze_run_varied(wtype, event, activity, act_id, base)
    elif wtype == "run_tempo" or wtype == "run_intervals":
        return _analyze_run_hard(wtype, event, activity, act_id, base)
    elif wtype == "strength":
        return _analyze_strength(wtype, event, activity, act_id, base)
    else:
        return {"workout_type": wtype, "metrics": base, "insights": [], "prompt_focus": ""}


# ── BIKE INTENSITY (threshold, sweetspot, over-unders) ─────────────────────

def _analyze_bike_intensity(wtype, event, activity, act_id, base):
    insights = []
    intervals_data = []
    hr_drift_pct = None

    # Haal intervals op voor power consistency
    try:
        detail = api.get_activity_detail(act_id)
        raw_intervals = detail.get("icu_intervals") or detail.get("intervals") or []
        # Filter op work intervals (niet warmup/cooldown)
        work_intervals = [iv for iv in raw_intervals
                          if iv.get("type") == "WORK"
                          or (iv.get("average_watts", 0) > FTP * 0.80
                              and iv.get("moving_time", 0) > 120)]
        for iv in work_intervals:
            intervals_data.append({
                "power": iv.get("average_watts") or iv.get("weighted_average_watts", 0),
                "hr": iv.get("average_heartrate", 0),
                "duration_s": iv.get("moving_time", 0),
                "max_hr": iv.get("max_heartrate", 0),
            })
    except Exception:
        pass

    # Power consistency: zijn alle intervals even hard?
    if len(intervals_data) >= 2:
        powers = [iv["power"] for iv in intervals_data if iv["power"] > 0]
        if powers:
            avg_p = sum(powers) / len(powers)
            pct_ftp = round(avg_p / FTP * 100)
            spread = max(powers) - min(powers)
            spread_pct = round(spread / avg_p * 100) if avg_p else 0

            base["interval_powers"] = powers
            base["interval_avg_power"] = round(avg_p)
            base["interval_power_spread_pct"] = spread_pct
            base["interval_pct_ftp"] = pct_ftp

            if spread_pct <= 3:
                insights.append(f"Power extreem consistent: {spread_pct}% verschil tussen intervals — metronomisch.")
            elif spread_pct <= 8:
                insights.append(f"Power consistent: {spread_pct}% spread ({min(powers)}-{max(powers)}W).")
            else:
                insights.append(f"Power inconsistent: {spread_pct}% spread ({min(powers)}-{max(powers)}W). Eerste interval te hard of fade aan het eind.")

            # Target zone check
            if "threshold" in wtype:
                if pct_ftp < 90:
                    insights.append(f"Gem. {pct_ftp}% FTP — onder threshold zone (95-105%). Te makkelijk of slechte dag?")
                elif pct_ftp > 105:
                    insights.append(f"Gem. {pct_ftp}% FTP — boven threshold. Sterk, maar pas op voor te veel vermoeidheid.")
                else:
                    insights.append(f"Gem. {pct_ftp}% FTP — precies in de threshold zone.")
            elif "sweetspot" in wtype:
                if pct_ftp < 85:
                    insights.append(f"Gem. {pct_ftp}% FTP — onder sweetspot (88-93%). Meer tempo of endurance geweest.")
                elif pct_ftp > 95:
                    insights.append(f"Gem. {pct_ftp}% FTP — boven sweetspot, richting threshold. Bewuste keuze?")
                else:
                    insights.append(f"Gem. {pct_ftp}% FTP — in de sweetspot zone. Maximale stimulus, minimale vermoeidheid.")

        # HR drift: stijgt HR bij gelijk vermogen?
        hrs = [iv["hr"] for iv in intervals_data if iv["hr"] > 0]
        if len(hrs) >= 2:
            first_half_hr = sum(hrs[:len(hrs)//2]) / (len(hrs)//2)
            second_half_hr = sum(hrs[len(hrs)//2:]) / (len(hrs) - len(hrs)//2)
            hr_drift_pct = round((second_half_hr - first_half_hr) / first_half_hr * 100, 1)
            base["hr_drift_pct"] = hr_drift_pct

            if hr_drift_pct > 8:
                insights.append(f"HR drift {hr_drift_pct}% — significant. Vermoeidheid bouwde op, mogelijk ondergehydrateerd of onvoldoende hersteld.")
            elif hr_drift_pct > 4:
                insights.append(f"HR drift {hr_drift_pct}% — normaal voor deze duur. Lichaam reageerde gezond.")
            elif hr_drift_pct <= 1:
                insights.append(f"Nauwelijks HR drift ({hr_drift_pct}%) — sterke aerobe basis of intensiteit was laag genoeg.")

    # Variability Index
    if base["vi"]:
        if base["vi"] > 1.10:
            insights.append(f"VI {base['vi']} — hoog. Veel wisselingen in vermogen, minder efficient.")
        elif base["vi"] < 1.03:
            insights.append(f"VI {base['vi']} — zeer stabiel. Clean pacing.")

    # Prompt focus
    if "threshold" in wtype:
        focus = ("Focus op: power consistency per interval, HR drift als teken van vermoeidheid, "
                 "of het vermogen in de threshold zone zat (95-105% FTP), en of de atleet faded of juist sterk afsloot.")
    elif "sweetspot" in wtype:
        focus = ("Focus op: zat het vermogen in de sweetspot (88-93% FTP)? HR drift is hier minder belangrijk. "
                 "Vraag: kon de atleet praten? Zo nee, dan was het te hard.")
    else:  # over-unders
        focus = ("Focus op: herstelde de atleet snel genoeg in de under-fases? "
                 "Power contrast tussen over (105%) en under (85-90%) — werd het contrast kleiner?")

    return {"workout_type": wtype, "metrics": base, "insights": insights, "prompt_focus": focus}


# ── BIKE ENDURANCE / GROUP ────────────────────────────────────────────────

def _analyze_bike_endurance(wtype, event, activity, act_id, base):
    insights = []

    # Hier is het simpel: was het echt easy?
    if base["avg_power"] and base["avg_power"] > FTP * 0.78:
        insights.append(f"Gem. {round(base['avg_power']/FTP*100)}% FTP — dat is boven endurance zone. Zwift race drift?")
    elif base["avg_power"]:
        insights.append(f"Gem. {round(base['avg_power']/FTP*100)}% FTP — lekker in de endurance zone.")

    if base["hr_pct"] > 78:
        insights.append(f"HR {base['hr_pct']}% HRmax — aan de hoge kant voor een endurance rit.")

    focus = "Kort en bondig: was het echt een rustige rit? Zo ja, prima — meer is niet nodig."
    return {"workout_type": wtype, "metrics": base, "insights": insights, "prompt_focus": focus}


# ── BIKE DRILLS (cadence, single leg) ─────────────────────────────────────

def _analyze_bike_drills(wtype, event, activity, act_id, base):
    insights = []

    if base["cadence"]:
        if base["cadence"] > 95:
            insights.append(f"Gem. kadans {base['cadence']} rpm — goed voor drills.")
        elif base["cadence"] < 80:
            insights.append(f"Gem. kadans {base['cadence']} rpm — laag. Bij kadansdrills verwacht je hoger.")

    focus = "Focus op techniek-aspecten: was de kadans hoog genoeg? Voelde het soepel?"
    return {"workout_type": wtype, "metrics": base, "insights": insights, "prompt_focus": focus}


# ── RUN LONG ──────────────────────────────────────────────────────────────

def _analyze_run_long(wtype, event, activity, act_id, base):
    insights = []
    splits = []

    # Haal streams voor pacing en HR drift
    try:
        detail = api.get_activity_detail(act_id)
        raw_intervals = detail.get("icu_intervals") or detail.get("intervals") or []
        # Gebruik km-splits als laps
        laps = [iv for iv in raw_intervals if iv.get("type") == "LAP" or iv.get("distance", 0) > 500]
        if not laps:
            laps = raw_intervals
        for lap in laps:
            d = (lap.get("distance") or 0)
            t = (lap.get("moving_time") or 0)
            if d > 0 and t > 0:
                pace = (t / 60) / (d / 1000)  # min/km
                splits.append({
                    "pace": round(pace, 2),
                    "hr": lap.get("average_heartrate", 0),
                    "distance_km": round(d / 1000, 1),
                })
    except Exception:
        pass

    if splits and len(splits) >= 3:
        paces = [s["pace"] for s in splits]
        first_third = paces[:len(paces)//3]
        last_third = paces[-len(paces)//3:]
        avg_first = sum(first_third) / len(first_third)
        avg_last = sum(last_third) / len(last_third)
        base["splits"] = splits
        base["avg_pace_first_third"] = round(avg_first, 2)
        base["avg_pace_last_third"] = round(avg_last, 2)

        if avg_last < avg_first - 0.05:
            insights.append(f"Negative split! Laatste derde {avg_last:.2f}/km vs eerste {avg_first:.2f}/km. Precies wat je wilt bij de lange duurloop.")
        elif avg_last > avg_first + 0.15:
            insights.append(f"Positive split: vertraagd van {avg_first:.2f}/km naar {avg_last:.2f}/km. Te snel begonnen of glycogeen op?")
        else:
            insights.append(f"Even pacing: {avg_first:.2f} → {avg_last:.2f}/km. Stabiel en gedisciplineerd.")

        # HR cardiac decoupling
        hrs = [s["hr"] for s in splits if s["hr"] > 0]
        if len(hrs) >= 4:
            first_half_hr = sum(hrs[:len(hrs)//2]) / (len(hrs)//2)
            second_half_hr = sum(hrs[len(hrs)//2:]) / (len(hrs) - len(hrs)//2)
            decoupling = round((second_half_hr - first_half_hr) / first_half_hr * 100, 1)
            base["cardiac_decoupling_pct"] = decoupling

            if decoupling > 5:
                insights.append(f"Cardiac decoupling {decoupling}% — aerobe basis nog in ontwikkeling. HR steeg terwijl pace gelijk bleef.")
            elif decoupling > 2:
                insights.append(f"Cardiac decoupling {decoupling}% — normaal voor deze duur.")
            else:
                insights.append(f"Cardiac decoupling {decoupling}% — uitstekend. Aerobe machine draait goed.")

    # Zone check
    if base["hr_pct"] > 82:
        insights.append(f"HR {base['hr_pct']}% HRmax — boven Z2 voor een lange duurloop. Risico: te veel vermoeidheid voor rest van de week.")
    elif base["hr_pct"] < 65:
        insights.append(f"HR {base['hr_pct']}% HRmax — erg rustig, meer herstelrun dan duurloop tempo.")

    # Fueling reminder
    if base["duration"] > 75:
        insights.append(f"Duur {base['duration']}min — hopelijk gevoed onderweg (gel/drank na 60min).")

    focus = ("Focus op: pacing strategie (negative split is goud), cardiac decoupling als aerobe indicator, "
             "en of de lange duurloop echt in Z2 bleef. Bij marathon: dit is DE training van de week.")
    return {"workout_type": wtype, "metrics": base, "insights": insights, "prompt_focus": focus}


# ── RUN EASY (Z2, recovery, trail) ────────────────────────────────────────

def _analyze_run_easy(wtype, event, activity, act_id, base):
    insights = []

    # Dit is simpel: was het Z2 of niet?
    if base["hr_pct"] > 82:
        insights.append(f"HR {base['hr_pct']}% HRmax — boven Z2. Dit was geen easy run. Langzamer lopen of heuvel vermijden.")
    elif base["hr_pct"] > 78:
        insights.append(f"HR {base['hr_pct']}% HRmax — net op de bovengrens van Z2. Op warme dagen te hoog.")
    elif base["hr_pct"] > 0:
        insights.append(f"HR {base['hr_pct']}% HRmax — in Z2. Prima.")

    # Pace context
    if base["distance"] > 0 and base["duration"] > 0:
        pace = round(base["duration"] / base["distance"], 2)
        base["avg_pace"] = pace
        if pace < 5.0 and base["hr_pct"] > 75:
            insights.append(f"Pace {pace:.2f}/km bij HR {base['hr_pct']}% — makkelijk lopen is makkelijk lopen. Langzamer.")

    if base["cadence"] and base["cadence"] < 170:
        insights.append(f"Kadans {base['cadence']} spm — probeer 175+ aan te houden, bespaart je benen.")

    if wtype == "run_trail":
        focus = "Kort. Trail run — genoten? Enkels en voeten gewerkt? Dat is het enige dat telt."
    elif wtype == "run_recovery":
        focus = "Heel kort. Recovery run: was het makkelijk? Zo ja, goed. Klaar."
    else:
        focus = "Kort en direct: was de hartslag in Z2? Zo ja: goed. Zo nee: waarschuw. Meer is niet nodig bij Z2 runs."

    return {"workout_type": wtype, "metrics": base, "insights": insights, "prompt_focus": focus}


# ── RUN VARIED (fartlek, progression, pickups) ────────────────────────────

def _analyze_run_varied(wtype, event, activity, act_id, base):
    insights = []

    # HR zone distributie
    if base["hr_zones"] and len(base["hr_zones"]) >= 3:
        total_s = sum(base["hr_zones"])
        if total_s > 0:
            z1z2_pct = round((base["hr_zones"][0] + base["hr_zones"][1]) / total_s * 100)
            z3plus_pct = 100 - z1z2_pct
            base["z1z2_pct"] = z1z2_pct
            base["z3plus_pct"] = z3plus_pct

            if z3plus_pct > 30:
                insights.append(f"{z3plus_pct}% boven Z2 — veel intensiteit. Dit was een stevige sessie.")
            elif z3plus_pct > 15:
                insights.append(f"{z3plus_pct}% boven Z2 — goede mix van makkelijk en hard.")
            else:
                insights.append(f"{z3plus_pct}% boven Z2 — vrij rustig voor een {wtype.replace('run_', '')}. Meer pit volgende keer?")

    if base["hr_pct"] > 85:
        insights.append(f"Gem. HR {base['hr_pct']}% HRmax — hoog voor een gevarieerde sessie. Herstel de dag erna nodig.")

    if wtype == "run_fartlek":
        focus = "Focus op: was er genoeg contrast tussen snel en rustig? Bij fartlek moet het leuk zijn, niet uitputtend."
    elif wtype == "run_progression":
        focus = "Focus op: werd het progressief sneller? Laatste km's moeten de snelste zijn, niet de eerste."
    else:
        focus = "Focus op: waren de versnellingen kort en explosief? Niet te lang doortrekken — neurommusculaire prikkel, geen interval."

    return {"workout_type": wtype, "metrics": base, "insights": insights, "prompt_focus": focus}


# ── RUN HARD (tempo, intervals) ───────────────────────────────────────────

def _analyze_run_hard(wtype, event, activity, act_id, base):
    insights = []
    intervals_data = []

    try:
        detail = api.get_activity_detail(act_id)
        raw_intervals = detail.get("icu_intervals") or detail.get("intervals") or []
        work_intervals = [iv for iv in raw_intervals
                          if iv.get("type") == "WORK"
                          or (iv.get("average_heartrate", 0) > HR_Z2_MAX
                              and iv.get("moving_time", 0) > 60)]
        for iv in work_intervals:
            d = iv.get("distance", 0)
            t = iv.get("moving_time", 0)
            pace = (t / 60) / (d / 1000) if d > 0 and t > 0 else 0
            intervals_data.append({
                "pace": round(pace, 2),
                "hr": iv.get("average_heartrate", 0),
                "max_hr": iv.get("max_heartrate", 0),
                "duration_s": t,
            })
    except Exception:
        pass

    if intervals_data:
        paces = [iv["pace"] for iv in intervals_data if iv["pace"] > 0]
        hrs = [iv["hr"] for iv in intervals_data if iv["hr"] > 0]
        base["interval_paces"] = paces
        base["interval_hrs"] = hrs

        if paces:
            spread = max(paces) - min(paces)
            base["pace_spread"] = round(spread, 2)

            if spread <= 0.05:
                insights.append(f"Pace extreem consistent: {min(paces):.2f}-{max(paces):.2f}/km. Machine-achtig.")
            elif spread <= 0.15:
                insights.append(f"Pace consistent: {min(paces):.2f}-{max(paces):.2f}/km ({round(spread*60)}s verschil).")
            else:
                insights.append(f"Pace inconsistent: {min(paces):.2f}-{max(paces):.2f}/km. Eerste interval te snel of fade?")

            avg_pace = sum(paces) / len(paces)
            if avg_pace < 4.10 and avg_pace > 3.50:
                insights.append(f"Gem. intervalpace {avg_pace:.2f}/km — in de buurt van 10km racepace. Marathon-specifiek: ~4:15-4:25/km interval pace passender.")
            elif avg_pace < 5.0:
                insights.append(f"Gem. intervalpace {avg_pace:.2f}/km.")

        # HR response: hoeveel steeg HR per interval?
        if len(hrs) >= 2:
            hr_rise = hrs[-1] - hrs[0]
            if hr_rise > 10:
                insights.append(f"HR steeg {hr_rise} bpm van eerste naar laatste interval — accumulerende vermoeidheid.")
            elif hr_rise < 3:
                insights.append(f"HR stabiel over intervals ({hr_rise} bpm verschil) — goed herstelvermogen.")

    focus = ("Focus op: pace consistency per interval (Delahaije: 'de laatste moet net zo snel zijn als de eerste'), "
             "HR response per interval, en of het volume en intensiteit past bij de fase. "
             "Bij tempo: was het drempelpace (4:05-4:15/km voor marathon sub 3:45)?")

    return {"workout_type": wtype, "metrics": base, "insights": insights, "prompt_focus": focus}


# ── STRENGTH ──────────────────────────────────────────────────────────────

def _analyze_strength(wtype, event, activity, act_id, base):
    insights = []
    if base["duration"] > 0:
        insights.append(f"Krachttraining {base['duration']}min voltooid.")

    focus = "Heel kort: krachttraining gedaan, goed. Rehab oefeningen erbij? Dat is het."
    return {"workout_type": wtype, "metrics": base, "insights": insights, "prompt_focus": focus}
