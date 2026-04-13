"""Coach-voice pre-workout intent.

Levert een korte, directe coaching-cue (1-3 zinnen) op basis van workout
`type`. Persona: analytisch, geen warmpraat. Wordt boven de beschrijving
getoond in de UI, BOVEN de structuur — niet vervangend.
"""
from __future__ import annotations

# Intent-map — sleutel is workout['type'] (lowercase). Subtrings worden
# ook gecheckt zodat varianten als "run_z2_standard" matchen op "z2".
_INTENTS: dict[str, str] = {
    "threshold": (
        "Twee doelen: exact vermogen vasthouden, mentale rust tussen blokken. "
        "Als blok 2 zwaarder voelt dan blok 1 is dat correct. "
        "Als blok 2 lichter voelt ging je te conservatief."
    ),
    "bike_threshold": (
        "Twee doelen: exact vermogen vasthouden, mentale rust tussen blokken. "
        "Als blok 2 zwaarder voelt dan blok 1 is dat correct. "
        "Als blok 2 lichter voelt ging je te conservatief."
    ),
    "cp_intervals": (
        "Maximale aerobe prikkel op vermoeide benen. Elke rep all-out maar "
        "herhaalbaar. Laatste rep moet net haalbaar zijn — niet makkelijk, "
        "niet onmogelijk."
    ),
    "fatmax_medium": (
        "High Z2 zonder drempel te raken. Ademhaling diep maar gecontroleerd. "
        "Vetstofwisseling traint hier, niet intensiteit."
    ),
    "fatmax_lang": (
        "High Z2 zonder drempel te raken. Ademhaling diep maar gecontroleerd. "
        "Vetstofwisseling traint hier, niet intensiteit."
    ),
    "long_slow": (
        "Volume met variatie. Cadens-blokken houden benen los. "
        "Hartslag onder aerobe drempel — als je hijgt ga je te hard."
    ),
    "easy_spin": (
        "Puur herstel. Benen rond draaien, niets meer. "
        "Ademhaling rustig, geen inspanning."
    ),
    "recovery_spin": (
        "Puur herstel. Benen rond draaien, niets meer. "
        "Ademhaling rustig, geen inspanning."
    ),
    "z2_standard": (
        "Conversatietempo. Je moet kunnen praten in hele zinnen. "
        "Dit is aerobe basis, geen training op tempo."
    ),
    "aerobic_z2": (
        "Conversatietempo. Je moet kunnen praten in hele zinnen. "
        "Dit is aerobe basis, geen training op tempo."
    ),
    "lange_duur": (
        "Eerste uur bewust sloom. Langzamer dan je denkt. "
        "Doel: voeten leren lang te lopen, niet snel."
    ),
    "long_run": (
        "Eerste uur bewust sloom. Langzamer dan je denkt. "
        "Doel: voeten leren lang te lopen, niet snel."
    ),
    "tempoduur": (
        "Net onder aerobe drempel. Comfortabel hard — praten in korte zinnen. "
        "Niet harder starten dan je kunt volhouden tot het eind."
    ),
    "tempoduurloop": (
        "Net onder aerobe drempel. Comfortabel hard — praten in korte zinnen. "
        "Niet harder starten dan je kunt volhouden tot het eind."
    ),
    "drempel": (
        "Hard, gelijkmatig, niet te hard starten. Je kunt nog net praten "
        "maar je wilt het niet. Laatste rep net haalbaar of volgende "
        "week stap terug."
    ),
    "marathon_tempo": (
        "Race-pace simulatie. Als dit zwaar voelt ga je te hard op race-dag. "
        "Beheers je tempo."
    ),
    "strides": (
        "Neuromusculaire prikkel, geen tempo-training. Versnellen, niet "
        "sprinten. Ademhaling mag rustig blijven."
    ),
}

_DEFAULT = "Voer uit zoals beschreven. Luister naar je lichaam."


# Mapping van namen-patronen (lowercase substrings) naar intent-keys.
# Gebruikt als fallback wanneer `type` niet direct een coach-type is
# (events uit intervals.icu hebben als `type` een sportcategorie).
_NAAM_PATTERNS: list[tuple[str, str]] = [
    ("marathon tempo", "marathon_tempo"),
    ("marathontempo", "marathon_tempo"),
    ("cp intervals", "cp_intervals"),
    ("cp ", "cp_intervals"),
    ("threshold", "threshold"),
    ("drempel", "drempel"),
    ("tempoduur", "tempoduur"),
    ("tempo duur", "tempoduur"),
    ("strides", "strides"),
    ("fatmax lang", "fatmax_lang"),
    ("fatmax", "fatmax_medium"),
    ("long slow", "long_slow"),
    ("lange duur", "lange_duur"),
    ("duurloop", "long_run"),
    ("herstel", "easy_spin"),
    ("recovery", "easy_spin"),
    ("easy spin", "easy_spin"),
    ("z2 ", "z2_standard"),
    ("z2+", "z2_standard"),
    ("z2 duurloop", "z2_standard"),
]


def get_intent(workout: dict | None) -> str:
    """Geef de coach-intent voor een workout.

    Kijkt eerst naar exacte match op `type`, daarna subtring-matching
    (bijv. "run_z2_standard" matcht "z2_standard"), en ten slotte
    naam-pattern-matching (voor intervals.icu events waar `type` de
    sportcategorie is en niet een coach-type). Fallback is een generieke
    1-liner.
    """
    if not workout:
        return _DEFAULT

    wtype = (workout.get("type") or "").strip().lower()

    # Exacte match op type
    if wtype and wtype in _INTENTS:
        return _INTENTS[wtype]

    # Substring-match op type (langste eerst — "long_run" vóór "run")
    if wtype:
        for key in sorted(_INTENTS.keys(), key=len, reverse=True):
            if key in wtype:
                return _INTENTS[key]

    # Fallback: match op `naam` (event-title)
    naam = (workout.get("naam") or workout.get("name") or "").strip().lower()
    if naam:
        for pattern, intent_key in _NAAM_PATTERNS:
            if pattern in naam:
                return _INTENTS.get(intent_key, _DEFAULT)

    return _DEFAULT
