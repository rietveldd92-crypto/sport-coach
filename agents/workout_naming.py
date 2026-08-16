"""workout_naming — de naam van een workout moet de stappen dekken.

Waarom dit bestaat: er stonden workouts in de kalender waarvan de naam een
andere sessie beschreef dan de body. Concreet 31 juli 2026:

    naam:  "Lange drempel - 2x30 min @ 4:20/km"   (ladder-trede 6)
    body:  "3x / - 15m 4:25/km Pace"              (ladder-trede 4)

Je traint naar de body, maar zowel jij als de coach-feedback lezen de naam.
Het gevolg was een sessie die als "niet afgemaakt" werd beoordeeld terwijl er
iets heel anders in het plan stond dan er boven stond.

De body is de waarheid — dat is wat intervals.icu afspeelt en wat je uitvoert.
Deze module leest de main set uit de body en corrigeert het reps/duur/pace-deel
van de naam als dat afwijkt. Het beschrijvende voorvoegsel ("Lange drempel",
"VO2max") blijft staan; alleen het feitelijke deel wordt rechtgezet.
"""

from __future__ import annotations

import re

# "3x" op een eigen regel = herhaling van het blok eronder.
_REPS_RE = re.compile(r"^\s*(\d+)\s*x\s*$", re.MULTILINE)
# "- 15m 4:25/km Pace" / "- 1.5km 4:19/km Pace" / "- 2m 112% Pace"
_STEP_RE = re.compile(
    r"^\s*-\s*(?P<dur>\d+(?:\.\d+)?)(?P<unit>km|m|s)\s+"
    r"(?P<target>\d+:\d{2}/km|\d+(?:-\d+)?%)",
    re.MULTILINE,
)
# Het feitelijke deel van een naam: "6x1.5km @ 4:17/km", "14x2m @ 112%"
_NAME_SPEC_RE = re.compile(
    r"(?P<reps>\d+)\s*x\s*(?P<dur>\d+(?:\.\d+)?)\s*(?P<unit>km|min|m|s)"
    r"\s*@\s*(?P<target>\d+:\d{2}/km|\d+%)"
)

_MAIN_SET_MARKER = "Main Set"


def _main_set(body: str) -> str:
    """Alleen het Main Set-blok; warmup en cooldown tellen niet mee."""
    if _MAIN_SET_MARKER in body:
        body = body.split(_MAIN_SET_MARKER, 1)[1]
    for stop in ("Cooldown", "Cool-down"):
        if stop in body:
            body = body.split(stop, 1)[0]
    return body


def parse_main_set(body: str) -> dict | None:
    """Lees reps, werkduur en target uit de main set van een beschrijving.

    Returns ``{"reps": int, "dur": float, "unit": str, "target": str}`` of None
    als de body geen herkenbare set heeft (vrije-vorm workouts, duurlopen).
    """
    if not body:
        return None
    section = _main_set(body)

    reps_match = _REPS_RE.search(section)
    reps = int(reps_match.group(1)) if reps_match else 1

    # De eerste stap ná de "Nx"-regel is het werkblok; daarna volgt de rust.
    search_from = reps_match.end() if reps_match else 0
    step = _STEP_RE.search(section, search_from)
    if not step:
        return None

    return {
        "reps": reps,
        "dur": float(step.group("dur")),
        "unit": step.group("unit"),
        "target": step.group("target"),
    }


def _fmt_spec(parsed: dict, unit_style: str = "min") -> str:
    """Bouw het feitelijke deel van de naam: "3x15 min @ 4:25/km".

    `unit_style` komt uit de naam die we corrigeren: de drempel-workouts heten
    "3x15 min", de VO2max-workouts "14x2m". We houden de schrijfwijze aan die
    er al stond, zodat een correctie geen tweede soort naam introduceert.
    """
    dur, unit = parsed["dur"], parsed["unit"]
    dur_str = f"{dur:g}"
    if unit == "m":
        unit_str = " min" if unit_style == "min" else "m"
    else:
        unit_str = unit
    return f"{parsed['reps']}x{dur_str}{unit_str} @ {parsed['target']}"


def _norm_spec(spec: str) -> str:
    """Vergelijkingsvorm: cosmetiek weg, betekenis behouden.

    "3x15 min @ 4:25/km" en "3x15min @ 4:25/km" zijn dezelfde sessie; daar
    hoeven we de naam niet voor te herschrijven.
    """
    return re.sub(r"\s+", "", spec.lower()).replace("min", "m")


def check(naam: str, beschrijving: str) -> tuple[str, str | None]:
    """Geef (gecorrigeerde_naam, waarschuwing).

    Waarschuwing is None als naam en body al met elkaar kloppen, of als de body
    geen parseerbare set heeft — dan laten we de naam ongemoeid in plaats van
    te gokken.
    """
    parsed = parse_main_set(beschrijving or "")
    if not parsed:
        return naam, None

    spec_match = _NAME_SPEC_RE.search(naam or "")
    if not spec_match:
        return naam, None

    huidig = spec_match.group(0)
    correct = _fmt_spec(parsed, unit_style=spec_match.group("unit"))

    if _norm_spec(huidig) == _norm_spec(correct):
        return naam, None

    nieuw = naam[:spec_match.start()] + correct + naam[spec_match.end():]
    warn = (
        f"Naam en inhoud liepen uiteen: naam zei '{huidig}', de stappen zijn "
        f"'{correct}'. Naam gecorrigeerd naar de stappen."
    )
    return nieuw, warn
