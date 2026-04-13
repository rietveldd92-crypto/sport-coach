"""Plotly workout-structuur chart met zone-kleuring.

Parst een Tima/bike_coach workout-beschrijving in intervals met
duur + intensiteitspercentage, rendert als area chart met zone-kleuren.
Optioneel overlay van werkelijk gereden samples (intervals.icu).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

try:
    import plotly.graph_objects as go
except ImportError:  # pragma: no cover — plotly verplicht in prod
    go = None


# ── ZONE-KLEUREN ───────────────────────────────────────────────────────────

ZONE_COLORS = [
    # (upper_bound_pct, color, label)
    (55, "#3D7CC9", "Z1"),
    (75, "#4FA668", "Z2"),
    (88, "#E6C85A", "Z3"),
    (105, "#E67E5A", "Z4"),
    (999, "#C9475A", "Z5"),
]


def _color_for_pct(pct: float) -> str:
    for upper, color, _ in ZONE_COLORS:
        if pct <= upper:
            return color
    return ZONE_COLORS[-1][1]


# ── INTERVAL DATACLASS ─────────────────────────────────────────────────────

@dataclass
class Interval:
    duration_min: float
    intensity_pct: float  # gemiddelde intensiteit als 1 getal (voor ramps: middelpunt)
    label: str = ""
    # Voor ramps: start/eind intensiteit apart (voor nauwkeurige plot).
    start_pct: Optional[float] = None
    end_pct: Optional[float] = None

    @property
    def is_ramp(self) -> bool:
        return self.start_pct is not None and self.end_pct is not None \
            and abs((self.start_pct or 0) - (self.end_pct or 0)) > 1


# ── PARSER ─────────────────────────────────────────────────────────────────

# Regex helpers
_LINE_REP = re.compile(r"^\s*(\d+)\s*[xX]\s*$")  # "2x" of "3X" op eigen regel
_LINE_STEP = re.compile(
    r"^\s*-\s*"
    r"(\d+)\s*m(?:in)?\s+"                      # "20m" of "20min"
    r"(?P<intensity>ramp\s+\d+-\d+%?|\d+(?:\.\d+)?%?)"  # "97%" of "ramp 50-80%"
    r"\s*(?P<rest>.*)$",
    re.IGNORECASE,
)
_LINE_STEP_COMPACT = re.compile(
    r"^\s*-?\s*(\d+)\s*m(?:in)?\s+(\d+)(?:-(\d+))?%", re.IGNORECASE,
)


def _parse_intensity(raw: str) -> tuple[float, Optional[float], Optional[float]]:
    """Parse een intensiteits-token.

    Returns (avg_pct, start_pct, end_pct). Voor een ramp zijn start/end
    gevuld; voor een vaste intensiteit zijn ze None.
    """
    raw = raw.strip().lower()
    # Ramp: "ramp 50-80%" of "ramp 75-50"
    m = re.match(r"ramp\s+(\d+)\s*-\s*(\d+)%?", raw)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return ((a + b) / 2, float(a), float(b))
    # Fixed: "97%" of "97"
    m = re.match(r"(\d+(?:\.\d+)?)%?", raw)
    if m:
        v = float(m.group(1))
        return (v, None, None)
    return (0.0, None, None)


def parse_workout_structure(description: str) -> list[Interval]:
    """Parse een workout-beschrijving naar een lijst intervals.

    Best-effort — onbekende formaten → lege lijst (caller valt dan terug).
    Herkent:
    - Section-headers (Warmup / Main Set / Cooldown) — puur label, wordt
      als laatste label meegegeven aan volgende steps.
    - Herhalingsmarkers (`Nx` op eigen regel).
    - Steps: `- 20m 97% 85rpm` of `- 10m ramp 50-80%`.
    """
    if not description:
        return []

    lines = description.splitlines()
    intervals: list[Interval] = []

    # Buffer voor "Nx" + volgende steps. Omdat herhaling op meerdere steps
    # kan slaan (`2x` + 2 steps erna), gebruiken we een simpele state:
    # na een Nx-marker verzamelen we volgende steps tot een blank line
    # of een volgende section-header — die worden N keer herhaald.
    current_section = ""
    pending_rep: Optional[int] = None
    rep_buffer: list[Interval] = []

    def _flush_rep():
        nonlocal pending_rep, rep_buffer
        if pending_rep and rep_buffer:
            for _ in range(pending_rep):
                intervals.extend(rep_buffer)
        elif rep_buffer:
            intervals.extend(rep_buffer)
        pending_rep = None
        rep_buffer = []

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            # Blank: flush rep-buffer (section-einde)
            _flush_rep()
            continue

        # Rep-marker?
        m_rep = _LINE_REP.match(line)
        if m_rep:
            _flush_rep()
            pending_rep = int(m_rep.group(1))
            continue

        # Step?
        m_step = _LINE_STEP.match(line)
        if m_step:
            duur = int(m_step.group(1))
            avg, a, b = _parse_intensity(m_step.group("intensity"))
            rest = (m_step.group("rest") or "").strip()
            iv = Interval(
                duration_min=float(duur),
                intensity_pct=avg,
                label=current_section + (f" — {rest}" if rest else ""),
                start_pct=a,
                end_pct=b,
            )
            if pending_rep is not None:
                rep_buffer.append(iv)
            else:
                intervals.append(iv)
            continue

        # Section-header? (geen streepje, niet 'Nx', niet leeg)
        if not line.startswith("-") and not _LINE_REP.match(line):
            # Alleen als het een korte header-achtige regel is (≤ 3 woorden)
            if len(line.split()) <= 3 and not any(c.isdigit() for c in line):
                _flush_rep()
                current_section = line
                continue

        # Anders: onbekende regel → negeren.

    _flush_rep()
    return intervals


# ── RENDER ─────────────────────────────────────────────────────────────────

def _empty_figure(message: str = "Structure not available"):
    if go is None:  # pragma: no cover
        return None
    fig = go.Figure()
    fig.add_annotation(
        text=message, showarrow=False,
        font=dict(color="#8A8680", size=13),
        x=0.5, y=0.5, xref="paper", yref="paper",
    )
    fig.update_layout(
        paper_bgcolor="#0A0A0A",
        plot_bgcolor="#0A0A0A",
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        height=180,
        margin=dict(l=10, r=10, t=10, b=10),
    )
    return fig


def _abs_label(pct: float, sport: str) -> str:
    """Absolute waarde voor hover: watts bij bike, pace bij run."""
    try:
        from agents.workout_annotations import (
            pct_to_pace_str, pct_to_watts, _is_bike, _is_run,
        )
    except Exception:
        return f"{pct:.0f}%"
    if _is_bike(sport):
        return f"{pct:.0f}% ({pct_to_watts(pct)}W)"
    if _is_run(sport):
        return f"{pct:.0f}% ({pct_to_pace_str(pct)})"
    return f"{pct:.0f}%"


def render_workout_chart(
    workout: dict,
    actual_samples: list | None = None,
    height: int = 200,
):
    """Genereer een Plotly-figuur voor de structuur van een workout.

    Args:
        workout: dict met minimaal `beschrijving` (str).
        actual_samples: optionele lijst (time_min, intensity_pct) — wordt
            als dunne witte lijn overlaid.

    Returns:
        plotly.graph_objects.Figure — of None als plotly niet geïnstalleerd.
    """
    if go is None:  # pragma: no cover
        return None

    beschrijving = (workout or {}).get("beschrijving") or ""
    sport = (workout or {}).get("sport") or ""
    intervals = parse_workout_structure(beschrijving)

    if not intervals:
        return _empty_figure()

    # Bouw step-plot: x = cumulatieve tijd, y = intensiteit, per interval
    # een kleine rechthoek. Voor ramps plotten we 2 punten (start/eind).
    xs: list[float] = []
    ys: list[float] = []
    colors: list[str] = []
    t = 0.0
    for iv in intervals:
        if iv.is_ramp and iv.start_pct is not None and iv.end_pct is not None:
            xs.extend([t, t + iv.duration_min])
            ys.extend([iv.start_pct, iv.end_pct])
            colors.append(_color_for_pct(iv.intensity_pct))
        else:
            xs.extend([t, t + iv.duration_min])
            ys.extend([iv.intensity_pct, iv.intensity_pct])
            colors.append(_color_for_pct(iv.intensity_pct))
        t += iv.duration_min

    fig = go.Figure()

    # Één gevulde area per interval — anders wordt zone-kleur niet duidelijk.
    t = 0.0
    for iv in intervals:
        seg_x: list[float]
        seg_y: list[float]
        if iv.is_ramp and iv.start_pct is not None and iv.end_pct is not None:
            seg_x = [t, t + iv.duration_min]
            seg_y = [iv.start_pct, iv.end_pct]
        else:
            seg_x = [t, t + iv.duration_min]
            seg_y = [iv.intensity_pct, iv.intensity_pct]
        color = _color_for_pct(iv.intensity_pct)
        if iv.is_ramp and iv.start_pct is not None and iv.end_pct is not None:
            hover = (
                f"{iv.duration_min:.0f}m ramp<br>"
                f"{_abs_label(iv.start_pct, sport)} → {_abs_label(iv.end_pct, sport)}"
            )
        else:
            hover = f"{iv.duration_min:.0f}m<br>{_abs_label(iv.intensity_pct, sport)}"
        fig.add_trace(go.Scatter(
            x=seg_x, y=seg_y,
            fill="tozeroy",
            fillcolor=color,
            line=dict(color=color, width=0),
            mode="lines",
            hoveron="fills",
            hovertemplate=hover + "<extra></extra>",
            text=hover,
            showlegend=False,
        ))
        t += iv.duration_min

    # Optionele overlay van werkelijke samples
    if actual_samples:
        ax = [p[0] for p in actual_samples]
        ay = [p[1] for p in actual_samples]
        fig.add_trace(go.Scatter(
            x=ax, y=ay,
            mode="lines",
            line=dict(color="#EFEFEF", width=1.2),
            name="Actual",
            hoverinfo="skip",
            showlegend=False,
        ))

    total_duration = sum(iv.duration_min for iv in intervals)
    max_y = max(ys) if ys else 100
    fig.update_layout(
        paper_bgcolor="#0A0A0A",
        plot_bgcolor="#0A0A0A",
        font=dict(color="#EFEFEF", family="Inter, sans-serif"),
        showlegend=False,
        hovermode="x",
        hoverlabel=dict(bgcolor="#1A1A1A", font=dict(color="#EFEFEF")),
        margin=dict(l=10, r=10, t=10, b=30),
        height=height,
        xaxis=dict(
            gridcolor="#222",
            zerolinecolor="#222",
            title=dict(text="min", font=dict(size=10, color="#8A8680")),
            range=[0, total_duration],
        ),
        yaxis=dict(
            gridcolor="#222",
            zerolinecolor="#222",
            range=[0, max(110, max_y + 10)],
            ticksuffix="%",
        ),
        bargap=0,
    )
    return fig
