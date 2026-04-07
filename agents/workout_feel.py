"""
Workout Feel — vertelt de atleet hoe een training moet voelen, VOOR de training.

Per workout type een coaching-noot die verwachtingen zet.
Na de training: vergelijk gevoel met data.
"""

from agents.workout_analysis import classify_workout


# Hoe moet deze workout voelen? (voor de training)
FEEL_BEFORE = {
    # Fiets
    "bike_threshold": (
        "Dit wordt pittig. De eerste interval voelt nog beheersbaar, "
        "de laatste doet pijn. Dat is precies de bedoeling. "
        "Als de laatste net zo makkelijk is als de eerste, mag het harder."
    ),
    "bike_sweetspot": (
        "Sweetspot voelt als 'comfortabel oncomfortabel'. "
        "Je moet nog net kunnen praten, maar je kiest ervoor om het niet te doen. "
        "Als je moet hijgen, zit je te hoog."
    ),
    "bike_over_unders": (
        "Over-unders zijn mentaal zwaar. De 'over' is kort maar doet pijn, "
        "de 'under' is net niet genoeg om te herstellen. Dat is het punt — "
        "je leert je lichaam om lactaat op te ruimen onder belasting."
    ),
    "bike_endurance": (
        "Dit is een rustige rit. Denk aan koffie-tempo. "
        "Je traint je vetstofwisseling, niet je benen. Geniet ervan."
    ),
    "bike_group": (
        "Zwift group ride — laat je meenemen door de groep. "
        "Niet proberen de groep te droppen. Het sociale aspect is de winst."
    ),
    "bike_cadence": (
        "Kadansdrills gaan over souplesse, niet over kracht. "
        "Het voelt onwennig bij hoge kadans, dat is normaal. Ontspan je bovenlichaam."
    ),
    "bike_drills": (
        "Single leg drills zijn coördinatie, niet intensiteit. "
        "Focus op de ronde trap, niet op het vermogen. Minder watt is prima."
    ),
    "bike_tempo": (
        "Tempo is net onder threshold. Het voelt alsof je lang door kan gaan, "
        "maar je wilt het niet. Precies goed."
    ),

    # Hardlopen
    "run_z2": (
        "Conversatietempo. Je moet hele zinnen kunnen uitspreken. "
        "Als je hijgt, ga je te hard. Laat het horloge los, volg je ademhaling."
    ),
    "run_recovery": (
        "Dit is geen training. Dit is actief herstel. "
        "Langzamer dan je denkt. Als het gênant langzaam voelt, zit je goed."
    ),
    "run_long": (
        "Begin bewust te langzaam. De eerste 5 kilometer zijn opwarming, niet training. "
        "Als je na 15km nog steeds lekker loopt, heb je het goed gedaan. "
        "Neem voeding mee als het langer dan 75 minuten is."
    ),
    "run_trail": (
        "Bosrun — vergeet je pace, geniet van de ondergrond. "
        "Zachte grond spaart je benen. Dit soort sessies houden het plezier erin."
    ),
    "run_fartlek": (
        "Fartlek is spelen met snelheid. De snelle stukken zijn kort en fris, "
        "niet uitputtend. Als je er niet van geniet, doe je het te hard."
    ),
    "run_progression": (
        "Begin rustig, word geleidelijk sneller. De laatste kilometers zijn de snelste. "
        "Het voelt alsof je de hele run naar dit moment hebt toegewerkt."
    ),
    "run_pickups": (
        "De versnellingen zijn kort — 20 seconden. Sprint niet, versnel soepel. "
        "Het is een neurommusculaire prikkel, geen interval. Je moet het leuk vinden."
    ),
    "run_tempo": (
        "Drempeltempo — je kunt nog net praten, maar je wilt het niet. "
        "Stabiel tempo is belangrijker dan snel tempo. "
        "De laatste kilometer moet net zo snel zijn als de eerste."
    ),
    "run_intervals": (
        "Intervals zijn precisiework. Loop ze op gevoel, niet op de klok. "
        "Het tempo komt vanzelf als de basis staat. Herstel volledig tussen de intervals."
    ),

    # Kracht
    "strength": (
        "Focus op kwaliteit, niet op zwaarte. Volle range of motion. "
        "De rehab oefeningen zijn het belangrijkst — die beschermen je knie en heup."
    ),
}

# Na de training: vergelijk data met verwachting
def compare_feel(workout_type: str, metrics: dict) -> str | None:
    """Vergelijk de data met hoe de workout had moeten voelen.

    Returns een coaching-noot of None als alles klopt.
    """
    hr_pct = metrics.get("hr_pct", 0)
    avg_power = metrics.get("avg_power")
    tss = metrics.get("tss", 0)

    if workout_type in ("run_z2", "run_recovery", "run_trail"):
        if hr_pct > 82:
            return (
                f"Je HR was {hr_pct}% HRmax — dat is boven Z2. "
                "Dit had makkelijk moeten voelen. Als het dat niet was, "
                "luister dan naar dat gevoel en ga volgende keer langzamer."
            )
        if hr_pct > 0 and hr_pct <= 75:
            return "HR netjes in Z2. Precies hoe het moet voelen — makkelijk en ontspannen."
        return None

    if workout_type == "run_long":
        decoupling = metrics.get("cardiac_decoupling_pct")
        if decoupling and decoupling > 5:
            return (
                f"Cardiac decoupling {decoupling}% — je HR steeg terwijl je pace gelijk bleef. "
                "Dat kan betekenen dat je te snel begon, of dat de aerobe basis nog groeit. "
                "Volgende keer: eerste helft bewust trager."
            )
        splits = metrics.get("splits", [])
        if splits and len(splits) >= 4:
            first = splits[0]["pace"]
            last = splits[-1]["pace"]
            if last < first - 0.05:
                return "Negative split — precies hoe Delahaije het wil. De beste duurlopen eindig je sterker dan je begint."
        return None

    if workout_type in ("bike_threshold", "bike_sweetspot"):
        powers = metrics.get("interval_powers", [])
        if powers and len(powers) >= 2:
            if powers[-1] < powers[0] * 0.92:
                return (
                    f"Je faded van {powers[0]}W naar {powers[-1]}W. "
                    "De laatste interval was zwaarder dan de eerste. "
                    "Volgende keer: begin 5W lager, dan kun je beter afsluiten."
                )
            if powers[-1] > powers[0] * 1.02:
                return "Sterk afgesloten — de laatste interval was harder dan de eerste. Dat is mentale kracht."
        hr_drift = metrics.get("hr_drift_pct")
        if hr_drift and hr_drift > 10:
            return (
                f"HR drift {hr_drift}% — je hart moest steeds harder werken voor hetzelfde vermogen. "
                "Mogelijk onvoldoende hersteld of gehydrateerd."
            )
        return None

    return None


def get_feel_note(event: dict) -> str | None:
    """Haal de coaching-noot op voor een workout (voor de training)."""
    wtype = classify_workout(event)
    return FEEL_BEFORE.get(wtype)


def get_post_workout_note(event: dict, metrics: dict) -> str | None:
    """Vergelijk de data met verwachting (na de training)."""
    wtype = classify_workout(event)
    return compare_feel(wtype, metrics)
