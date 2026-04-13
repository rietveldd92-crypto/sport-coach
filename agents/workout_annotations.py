"""Verrijkt workout-beschrijvingen met absolute waardes.

Bij runs: voegt pace (min:sec/km) toe naast het %-target.
Bij bikes: voegt watts toe naast het %-target.

Gebruikt een centrale threshold pace + FTP zodat de atleet direct ziet
hoe hard een 75%-blok écht is zonder zelf om te rekenen.
"""
from __future__ import annotations

import re

ATHLETE_FTP = 290
THRESHOLD_PACE_SEC_PER_KM = 260  # 4:20/km — drempelpace (zie endurance_coach)


def pct_to_watts(pct: float, ftp: int = ATHLETE_FTP) -> int:
    return int(round(ftp * pct / 100))


def pct_to_pace_str(pct: float, threshold_sec: int = THRESHOLD_PACE_SEC_PER_KM) -> str:
    """Lagere % = trager. 100% Pace = drempelpace."""
    if pct <= 0:
        return "—"
    sec_per_km = int(round(threshold_sec * 100 / pct))
    mm, ss = divmod(sec_per_km, 60)
    return f"{mm}:{ss:02d}/km"


def _is_run(sport: str) -> bool:
    return (sport or "") == "Run"


def _is_bike(sport: str) -> bool:
    return (sport or "") in ("Ride", "VirtualRide")


# Step-regel: `- 20m 97% 85rpm` of `- 10m ramp 50-80% Pace`
# Match de leidende N%  of ramp A-B% zodat we daarna `(Xw)` of `(pace)` kunnen invoegen.
_STEP_RE = re.compile(
    r"^(?P<prefix>\s*-\s*\d+\s*m(?:in)?\s+)"
    r"(?P<target>ramp\s+\d+\s*-\s*\d+%?|\d+(?:\.\d+)?%)"
    r"(?P<rest>.*)$",
    re.IGNORECASE,
)


def _target_values(target: str) -> tuple[float, float | None]:
    """Parse een target-token naar (avg_pct, end_pct_if_ramp)."""
    t = target.strip().lower()
    m = re.match(r"ramp\s+(\d+)\s*-\s*(\d+)%?", t)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return (a, float(b))
    m = re.match(r"(\d+(?:\.\d+)?)%?", t)
    if m:
        return (float(m.group(1)), None)
    return (0.0, None)


def annotate_description(
    desc: str,
    sport: str,
    ftp: int = ATHLETE_FTP,
    threshold_pace_sec: int = THRESHOLD_PACE_SEC_PER_KM,
) -> str:
    """Voeg absolute waardes toe achter elke step in de beschrijving.

    - Runs: `- 20m 75% Pace` -> `- 20m 75% Pace (5:47/km)`
    - Bikes: `- 20m 75% 90rpm` -> `- 20m 75% (218W) 90rpm`

    Idempotent: als de regel al een `(…W)` of `(…/km)` bevat, laten we hem
    met rust zodat dubbel-annoteren geen garbage oplevert.
    """
    if not desc or not (_is_run(sport) or _is_bike(sport)):
        return desc

    out_lines: list[str] = []
    for line in desc.splitlines():
        m = _STEP_RE.match(line)
        if not m:
            out_lines.append(line)
            continue
        # Al geannoteerd? Laat staan.
        if re.search(r"\([^)]*(W\)|/km\))", line):
            out_lines.append(line)
            continue

        avg, end = _target_values(m.group("target"))
        rest = m.group("rest")

        if _is_bike(sport):
            if end is not None:
                annot = f" ({pct_to_watts(m_start(m), ftp)}->{pct_to_watts(end, ftp)}W)"
            else:
                annot = f" ({pct_to_watts(avg, ftp)}W)"
        else:  # run
            if end is not None:
                annot = (
                    f" ({pct_to_pace_str(m_start(m), threshold_pace_sec)}->"
                    f"{pct_to_pace_str(end, threshold_pace_sec)})"
                )
            else:
                annot = f" ({pct_to_pace_str(avg, threshold_pace_sec)})"
        new_line = f"{m.group('prefix')}{m.group('target')}{annot}{rest}"

        out_lines.append(new_line)
    return "\n".join(out_lines)


def m_start(match: re.Match) -> float:
    """Startwaarde uit een ramp-target."""
    t = match.group("target").strip().lower()
    m = re.match(r"ramp\s+(\d+)\s*-\s*\d+%?", t)
    if m:
        return float(m.group(1))
    return 0.0
