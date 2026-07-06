"""De vier pijlers van duurprestatie — het trainingsmodel van deze app.

Marathon-/raceperformance wordt bepaald door vier factoren (Dennis'
formulering, 2026-07-06):

  1. Lactaatdrempel — hogere drempel → hogere drempelpace → hogere racepace.
  2. Running economy — minder energie per km op racepace.
  3. Fatigue resistance — de pace vasthouden diep in de wedstrijd.
  4. VO2max — het plafond waar de drempel onder hangt.

Per wedstrijd verschuiven de accenten (10K: drempel+VO2; marathon: fatigue
resistance + economy op marathonpace), maar het idee is constant: hogere
drempelpace → hoger tempo → beter resultaat.

Elke geplande sessie hoort bij precies één pijler (of is expliciet
"support": aerobe basis die de pijlers draagt). Sessies zonder pijler
worden niet gepland — dat is de anti-junk-regel.
"""
from __future__ import annotations

PIJLER_LABELS: dict[str, str] = {
    "lactaatdrempel": (
        "PIJLER: LACTAATDREMPEL — hogere drempelpace = hogere racepace. "
        "Dit is de sleutelsessie van de week."
    ),
    "running_economy": (
        "PIJLER: RUNNING ECONOMY — efficiënter lopen op racepace "
        "(strides/neuromusculair, licht en snel voetenwerk)."
    ),
    "fatigue_resistance": (
        "PIJLER: FATIGUE RESISTANCE — de pace vasthouden als het zwaar "
        "wordt. Duur en vermoeide-benen-werk, nooit boven Z2 tenzij "
        "racepace-blokken gepland zijn."
    ),
    "vo2max": (
        "PIJLER: VO2MAX — het plafond optillen. Korte intensieve blokken; "
        "op de fiets om knie/hamstring te sparen."
    ),
    "support": (
        "SUPPORT — aerobe basis die de vier pijlers draagt. Geen doel op "
        "zich; bij tijdgebrek of vermoeidheid schrappen is prima."
    ),
}

# type/naam-keywords → pijler. Volgorde is betekenisvol: eerste match wint.
_PIJLER_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("lactaatdrempel", ("drempel", "threshold", "tempoduur", "tempoloon",
                        "sweetspot", "over_unders", "over-unders",
                        "marathon_tempo", "cruise", "cp_intervals",
                        "pyramide", "interval_10km")),
    ("vo2max", ("vo2", "30/15", "ronnestad")),
    ("running_economy", ("strides", "heuvels", "hill")),
    ("fatigue_resistance", ("lange_duur", "long_run", "long_slow",
                            "lange duurloop", "long endurance", "fatmax")),
)


def classify_pijler(sessie: dict) -> str:
    """Bepaal de pijler van een sessie op type/naam. Fallback: support."""
    sessie_type = (sessie.get("type") or "").lower()
    naam = (sessie.get("naam") or "").lower()
    for pijler, keywords in _PIJLER_KEYWORDS:
        if any(k in sessie_type or k in naam for k in keywords):
            return pijler
    return "support"


def pijler_header(sessie: dict) -> str:
    """De labelregel die bovenaan de workout-beschrijving komt."""
    return PIJLER_LABELS[classify_pijler(sessie)]
