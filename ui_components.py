"""
ui_components — Custom Streamlit layout helpers voor Sport Coach.

Scaffold voor Fase 0. Alle functies bestaan maar renderen voorlopig nog
Streamlit-default-achtige versies zodat niets breekt. Fase 1 vult elk
component met de echte design-taal (dark mode, Fraunces/Inter, warme
accent, mobile-first).

Regel: wie een component aanroept, ziet NOOIT raw Streamlit widgets
eromheen hangen. Alle styling zit hier. Call-sites blijven leesbaar.

Gebruik:
    import ui_components as ui

    ui.inject_global_css()
    ui.section_header("Vandaag")
    ui.today_hero(workout=..., coach_note=..., checkin_done=False)
    ui.coach_card("Goed geslapen en fris — tijd voor volume.", tone="neutral")
    ui.day_card(date=..., workout=..., status="planned", reason="...")
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional, Literal

import streamlit as st


# ── GLOBAL CSS ─────────────────────────────────────────────────────────────

_GLOBAL_CSS_INJECTED_KEY = "_ui_global_css_injected"

# ── DESIGN TOKENS ──────────────────────────────────────────────────────────
# Één plek om het palet aan te passen. Accent is terracotta #C4603C —
# bewuste keuze (DECISIONS.md): warmer/ruger dan ember, past bij "30%
# trainer / 70% coach". Dark mode is default.
#
# Tokens staan expliciet in CSS variabelen — het hele design trekt aan
# deze handles. Als je ooit light mode wilt: body[data-theme="light"]
# override met nieuwe waardes van dezelfde variabelen.

_GLOBAL_CSS = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600;9..144,700&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">

<style>
    :root {
        /* Base */
        --bg: #0E0F12;
        --bg-raised: #17181C;
        --bg-elevated: #1E1F24;
        --border: #24262D;
        --border-strong: #2E3038;

        /* Text */
        --text: #F4F2EE;
        --text-muted: #8A8680;
        --text-dim: #5B5852;

        /* Accent — terracotta */
        --accent: #C4603C;
        --accent-hover: #D47049;
        --accent-bg: rgba(196, 96, 60, 0.08);
        --accent-border: rgba(196, 96, 60, 0.35);

        /* Status */
        --positive: #5B8C5A;
        --positive-bg: rgba(91, 140, 90, 0.1);
        --warning: #D4A24C;
        --warning-bg: rgba(212, 162, 76, 0.1);
        --alert: #B84646;
        --alert-bg: rgba(184, 70, 70, 0.1);

        /* Type */
        --font-display: "Fraunces", Georgia, "Times New Roman", serif;
        --font-body: "Inter", -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
        --font-mono: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
    }

    /* Reset + hide Streamlit chrome */
    #MainMenu, footer, header,
    [data-testid="stToolbar"],
    [data-testid="stDecoration"],
    [data-testid="stStatusWidget"] { display: none !important; }

    /* App background — full dark */
    .stApp,
    [data-testid="stAppViewContainer"],
    [data-testid="stHeader"] {
        background: var(--bg) !important;
    }
    .stApp > header { display: none; }

    /* Mobile-first container */
    .block-container {
        max-width: 680px !important;
        padding-top: 1.4rem !important;
        padding-bottom: 5rem !important;
        padding-left: 1.1rem !important;
        padding-right: 1.1rem !important;
    }

    /* ── Typography baseline ─────────────────────────────────── */
    html, body, .stApp, [class*="css"] {
        font-family: var(--font-body);
        color: var(--text);
        font-feature-settings: "tnum" 1, "cv11" 1;
    }
    .stMarkdown, .stMarkdown p, .stMarkdown li, .stMarkdown span {
        color: var(--text) !important;
        font-family: var(--font-body);
    }
    h1, h2, h3, h4, h5, h6 {
        font-family: var(--font-display);
        color: var(--text) !important;
        font-weight: 600;
        letter-spacing: -0.02em;
    }
    p, li, span { line-height: 1.6; }
    code, pre { font-family: var(--font-mono); }

    /* Tabular numbers waar het telt */
    .stMetric [data-testid="stMetricValue"],
    .ui-stat-inline .value,
    .ui-today-hero .stats,
    .ui-workout-details { font-variant-numeric: tabular-nums; }

    /* ── Section header ──────────────────────────────────────── */
    .ui-section-header {
        font-family: var(--font-body);
        font-size: 0.68rem;
        text-transform: uppercase;
        letter-spacing: 0.14em;
        color: var(--text-muted);
        font-weight: 600;
        margin: 1.6rem 0 0.5rem 0;
    }

    /* ── Coach card — warme quote styling ────────────────────── */
    .ui-coach-card {
        border-left: 2px solid var(--accent);
        padding: 1rem 1.2rem 1rem 1.3rem;
        margin: 0.8rem 0;
        background: var(--accent-bg);
        border-radius: 0 12px 12px 0;
        font-family: var(--font-display);
        font-size: 1rem;
        line-height: 1.7;
        color: var(--text);
    }
    .ui-coach-card.tone-positive {
        border-left-color: var(--positive);
        background: var(--positive-bg);
    }
    .ui-coach-card.tone-warning {
        border-left-color: var(--warning);
        background: var(--warning-bg);
    }
    .ui-coach-card.tone-alert {
        border-left-color: var(--alert);
        background: var(--alert-bg);
    }

    /* ── Today hero — grote workout card ─────────────────────── */
    .ui-today-hero {
        padding: 1.6rem 1.8rem 1.4rem 1.8rem;
        margin: 0.2rem 0 1.4rem 0;
        background: var(--bg-raised);
        border: 1px solid var(--border);
        border-radius: 20px;
        position: relative;
        overflow: hidden;
    }
    .ui-today-hero::before {
        content: "";
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 2px;
        background: linear-gradient(90deg, var(--accent) 0%, transparent 100%);
    }
    .ui-today-hero .label {
        font-size: 0.66rem;
        text-transform: uppercase;
        letter-spacing: 0.16em;
        color: var(--accent);
        font-weight: 600;
        margin-bottom: 0.5rem;
    }
    .ui-today-hero .title {
        font-family: var(--font-display);
        font-size: 1.75rem;
        font-weight: 600;
        color: var(--text);
        line-height: 1.15;
        letter-spacing: -0.02em;
        margin-bottom: 0.4rem;
    }
    .ui-today-hero .stats {
        font-size: 0.82rem;
        color: var(--text-muted);
        margin-bottom: 1rem;
    }
    .ui-today-hero .note {
        font-family: var(--font-display);
        font-size: 0.95rem;
        color: var(--text);
        line-height: 1.65;
        padding-top: 0.9rem;
        border-top: 1px solid var(--border);
        font-style: italic;
    }

    /* ── Day card — één dag in weekview ──────────────────────── */
    .ui-day-card {
        padding: 0.95rem 1.2rem;
        border-radius: 14px;
        margin: 0.4rem 0;
        border: 1px solid var(--border);
        background: var(--bg-raised);
        transition: border-color 0.15s ease;
    }
    .ui-day-card:hover { border-color: var(--border-strong); }
    .ui-day-card.status-done {
        opacity: 0.55;
        background: transparent;
    }
    .ui-day-card.status-today {
        border-color: var(--accent-border);
        background: var(--accent-bg);
    }
    .ui-day-card.status-missed {
        border-color: rgba(184, 70, 70, 0.3);
    }
    .ui-day-card .day {
        font-size: 0.66rem;
        text-transform: uppercase;
        letter-spacing: 0.14em;
        color: var(--text-muted);
        font-weight: 600;
    }
    .ui-day-card .name {
        font-family: var(--font-display);
        font-size: 1.02rem;
        font-weight: 600;
        color: var(--text);
        margin-top: 0.2rem;
        letter-spacing: -0.01em;
    }
    .ui-day-card .reason {
        font-size: 0.78rem;
        color: var(--text-muted);
        margin-top: 0.35rem;
        line-height: 1.55;
    }

    /* ── Workout details — structuur blok ────────────────────── */
    .ui-workout-details {
        background: var(--bg-elevated);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 0.9rem 1.1rem;
        margin: 0.4rem 0 0.6rem 0;
        font-family: var(--font-mono);
        font-size: 0.78rem;
        line-height: 1.75;
        color: var(--text);
        white-space: pre-wrap;
        overflow-x: auto;
    }
    .ui-workout-details .wd-section {
        color: var(--accent);
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        font-size: 0.7rem;
        margin-top: 0.5rem;
        margin-bottom: 0.2rem;
        display: block;
    }
    .ui-workout-details .wd-section:first-child { margin-top: 0; }
    .ui-workout-details .wd-reps {
        color: var(--warning);
        font-weight: 600;
    }
    .ui-workout-details .wd-step {
        color: var(--text);
        padding-left: 0.5rem;
        display: block;
    }
    .ui-workout-details .wd-note {
        color: var(--text-muted);
        font-family: var(--font-body);
        font-style: italic;
        font-size: 0.78rem;
        display: block;
        margin-top: 0.8rem;
        padding-top: 0.7rem;
        border-top: 1px dashed var(--border);
    }

    /* ── Stat inline — klein grijs tabular ───────────────────── */
    .ui-stat-inline {
        display: inline-block;
        font-variant-numeric: tabular-nums;
        font-size: 0.78rem;
        color: var(--text-muted);
        margin-right: 1rem;
    }
    .ui-stat-inline .label {
        text-transform: uppercase;
        letter-spacing: 0.1em;
        font-size: 0.62rem;
        margin-right: 0.3rem;
        color: var(--text-dim);
    }
    .ui-stat-inline .value {
        color: var(--text);
        font-weight: 600;
    }

    /* ── Sidebar overrides ───────────────────────────────────── */
    section[data-testid="stSidebar"] {
        background: var(--bg-raised) !important;
        border-right: 1px solid var(--border) !important;
    }
    section[data-testid="stSidebar"] .block-container {
        padding-top: 2rem !important;
    }
    section[data-testid="stSidebar"] * {
        color: var(--text);
    }
    section[data-testid="stSidebar"] label {
        color: var(--text-muted) !important;
    }

    /* ── Button styling — dark, warm hover ──────────────────── */
    .stButton > button {
        background: var(--bg-raised) !important;
        color: var(--text) !important;
        border: 1px solid var(--border) !important;
        border-radius: 10px !important;
        font-family: var(--font-body) !important;
        font-size: 0.82rem !important;
        font-weight: 500 !important;
        padding: 0.4rem 0.9rem !important;
        transition: all 0.15s ease !important;
    }
    .stButton > button:hover {
        border-color: var(--accent) !important;
        color: var(--accent) !important;
        background: var(--accent-bg) !important;
    }
    .stButton > button:focus {
        box-shadow: 0 0 0 2px var(--accent-bg) !important;
    }
    .stButton > button[kind="primary"] {
        background: var(--accent) !important;
        color: var(--bg) !important;
        border-color: var(--accent) !important;
    }

    /* ── Metric styling (sidebar) ────────────────────────────── */
    [data-testid="stMetric"] { background: transparent; }
    [data-testid="stMetricLabel"] {
        color: var(--text-dim) !important;
        font-size: 0.62rem !important;
        text-transform: uppercase;
        letter-spacing: 0.1em;
    }
    [data-testid="stMetricValue"] {
        color: var(--text) !important;
        font-family: var(--font-display) !important;
        font-size: 1.4rem !important;
        font-weight: 600 !important;
    }

    /* ── Progress bar — warme accent ────────────────────────── */
    .stProgress > div > div > div > div {
        background: var(--accent) !important;
    }
    .stProgress > div > div > div {
        background: var(--border) !important;
    }

    /* ── Week progress caption ───────────────────────────────── */
    .week-progress {
        font-size: 0.74rem;
        color: var(--text-muted);
        font-weight: 500;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        margin: 1rem 0 0.4rem 0;
    }

    /* ── Verberg oude legacy workout-row styling (rest van app) ─ */
    .workout-row {
        background: var(--bg-raised);
        border-radius: 14px;
        border: 1px solid var(--border);
        padding: 0.95rem 1.2rem;
        margin: 0.4rem 0;
    }
    .workout-row.is-done { opacity: 0.55; }
    .workout-row .wr-day {
        font-size: 0.66rem;
        text-transform: uppercase;
        letter-spacing: 0.14em;
        color: var(--text-muted);
        font-weight: 600;
    }
    .workout-row .wr-name {
        font-family: var(--font-display);
        font-size: 1rem;
        font-weight: 600;
        color: var(--text);
        margin-top: 0.15rem;
    }
    .workout-row .wr-stats {
        font-size: 0.74rem;
        color: var(--text-muted);
        margin-top: 0.3rem;
    }
    .wr-check {
        display: inline-block;
        width: 18px; height: 18px;
        border-radius: 50%;
        text-align: center;
        line-height: 18px;
        font-size: 0.66rem;
        margin-right: 0.6rem;
        flex-shrink: 0;
    }
    .wr-check.done {
        background: var(--positive);
        color: var(--bg);
    }
    .wr-check.pending {
        border: 1.5px solid var(--border-strong);
        background: transparent;
    }

    /* Coach feedback card (oude Gemini output) */
    .coach-feedback {
        background: var(--bg-elevated);
        border-radius: 14px;
        padding: 1.2rem 1.4rem;
        margin: 0.5rem 0 1rem 0;
        border: 1px solid var(--border);
        font-family: var(--font-body);
        font-size: 0.9rem;
        line-height: 1.7;
        color: var(--text);
    }
    .coach-feedback .coach-avatar {
        font-size: 0.66rem;
        font-weight: 600;
        color: var(--accent);
        text-transform: uppercase;
        letter-spacing: 0.14em;
        margin-bottom: 0.6rem;
    }

    /* Feel note pre-workout */
    .feel-note {
        background: var(--bg-raised);
        border: 1px solid var(--border);
        border-radius: 10px;
        padding: 0.8rem 1.1rem;
        margin: 0.4rem 0 0.6rem 0;
        font-family: var(--font-display);
        font-size: 0.88rem;
        font-style: italic;
        color: var(--text);
        line-height: 1.6;
    }

    /* Divider subtler */
    hr { border-color: var(--border) !important; }

    /* ── Morning check-in ────────────────────────────────── */
    .ui-checkin {
        background: var(--bg-raised);
        border: 1px solid var(--border);
        border-radius: 16px;
        padding: 1.2rem 1.4rem;
        margin: 0.8rem 0 1.2rem 0;
    }
    .ui-checkin .ci-title {
        font-family: var(--font-display);
        font-size: 1.05rem;
        font-weight: 600;
        color: var(--text);
        margin-bottom: 0.2rem;
        letter-spacing: -0.01em;
    }
    .ui-checkin .ci-subtitle {
        font-size: 0.78rem;
        color: var(--text-muted);
        margin-bottom: 1rem;
    }

    /* Slider label styling override voor de check-in */
    .ui-checkin + div [data-testid="stSlider"] label {
        font-family: var(--font-body);
        font-size: 0.78rem !important;
        color: var(--text-muted) !important;
        text-transform: uppercase;
        letter-spacing: 0.08em;
    }

    /* ── Data-to-human snippet ───────────────────────────── */
    .ui-human-line {
        font-family: var(--font-display);
        font-size: 0.95rem;
        color: var(--text);
        line-height: 1.65;
        margin: 0.3rem 0 0.6rem 0;
        font-style: italic;
    }
    .ui-human-line .numbers {
        font-family: var(--font-body);
        font-style: normal;
        color: var(--text-muted);
        font-size: 0.78rem;
        letter-spacing: 0.02em;
        display: block;
        margin-top: 0.2rem;
    }

    /* Sidebar: fase/context tekst */
    .sidebar-phase {
        font-family: var(--font-display);
        font-size: 1.15rem;
        font-weight: 600;
        color: var(--text);
        line-height: 1.35;
        margin-bottom: 0.4rem;
        letter-spacing: -0.01em;
    }
    .sidebar-fitness {
        font-size: 0.84rem;
        color: var(--text-muted);
        line-height: 1.55;
        margin-bottom: 1rem;
    }
    .sidebar-weeks {
        display: inline-block;
        background: var(--accent);
        color: var(--bg);
        font-size: 0.68rem;
        font-weight: 600;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        padding: 0.35rem 0.9rem;
        border-radius: 20px;
        margin-bottom: 1.1rem;
    }
</style>
"""


def inject_global_css() -> None:
    """Inject de globale CSS één keer per Streamlit-sessie.

    Gebruikt session_state om dubbele injectie te voorkomen bij reruns.
    """
    if st.session_state.get(_GLOBAL_CSS_INJECTED_KEY):
        return
    st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)
    st.session_state[_GLOBAL_CSS_INJECTED_KEY] = True


# ── COMPONENTS ─────────────────────────────────────────────────────────────

Tone = Literal["neutral", "positive", "warning", "alert"]


def section_header(text: str) -> None:
    """Kleine uppercase section header. Geen st.markdown("## ...") meer."""
    st.markdown(f'<div class="ui-section-header">{text}</div>', unsafe_allow_html=True)


def coach_card(body: str, tone: Tone = "neutral", title: Optional[str] = None) -> None:
    """Warm quote-styled coach bericht. Vervangt st.info / st.success / st.warning.

    tone:
        neutral  — warm accent (ember), default
        positive — zacht groen
        warning  — amber
        alert    — rood (alleen voor echte problemen)
    """
    tone_class = "" if tone == "neutral" else f" tone-{tone}"
    title_html = f'<div class="ui-section-header" style="margin:0 0 0.3rem 0;">{title}</div>' if title else ""
    st.markdown(
        f'<div class="ui-coach-card{tone_class}">{title_html}{body}</div>',
        unsafe_allow_html=True,
    )


def today_hero(
    title: str,
    sport: str,
    stats_parts: list[str],
    coach_note: Optional[str] = None,
    label: str = "Vandaag",
) -> None:
    """De grote 'Vandaag'-kaart. Workout titel groot, stats klein, coach-note eronder.

    Args:
        title: Workout naam (bijv. "Threshold 3x8 min @ 95%")
        sport: "Hardlopen" of "Fietsen"
        stats_parts: Lijst met strings zoals ["45 min", "TSS ~65"]
        coach_note: Optionele pre-workout noot (uit workout_feel)
        label: Bovenaan (standaard "Vandaag")
    """
    stats_line = f"{sport} &middot; " + " &middot; ".join(stats_parts) if stats_parts else sport
    note_html = f'<div class="note">{coach_note}</div>' if coach_note else ""
    st.markdown(
        f'<div class="ui-today-hero">'
        f'<div class="label">{label}</div>'
        f'<div class="title">{title}</div>'
        f'<div class="stats">{stats_line}</div>'
        f'{note_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


def day_card(
    day_label: str,
    name: str,
    status: Literal["planned", "done", "missed", "today"] = "planned",
    reason: Optional[str] = None,
    stats_parts: Optional[list[str]] = None,
) -> None:
    """Een dag-kaart in de weekview. Rust, ruimte, status-dot ipv badge.

    Fase 0: minimal render. Fase 4 voegt swap-interactie toe.
    """
    stats_html = ""
    if stats_parts:
        stats_html = '<div class="reason">' + " &middot; ".join(stats_parts) + '</div>'
    reason_html = f'<div class="reason">{reason}</div>' if reason else ""
    st.markdown(
        f'<div class="ui-day-card status-{status}">'
        f'<div class="day">{day_label}</div>'
        f'<div class="name">{name}</div>'
        f'{stats_html}'
        f'{reason_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


def stat_inline(label: str, value: str) -> None:
    """Kleine inline stat: 'TSS 72' of 'DUUR 45 min'. Tabular figures."""
    st.markdown(
        f'<span class="ui-stat-inline">'
        f'<span class="label">{label}</span>'
        f'<span class="value">{value}</span>'
        f'</span>',
        unsafe_allow_html=True,
    )


def availability_slider_row(day_label: str, key_prefix: str) -> tuple[Optional[int], Optional[str]]:
    """Scaffold: één rij voor beschikbaarheid per dag.

    Fase 0: returnt tuple (None, None) — echte implementatie komt in Fase 4
    als de scheduler bestaat. Dit is hier puur om de signature te pinnen
    zodat callers eraan kunnen bouwen.
    """
    # TODO Fase 4: custom pill buttons voor duur + intensiteit
    return (None, None)


# ── WORKOUT DETAILS ────────────────────────────────────────────────────────

# Labels die een "section" openen in onze workout-descriptions.
# Case-insensitive match op regel-start.
_SECTION_LABELS = {
    "warmup", "warm up", "warm-up", "opwarming",
    "main set", "hoofdset", "hoofd set", "main",
    "cooldown", "cool down", "cool-down", "afkoelen",
    "rehab", "activatie", "mobiliteit",
    "neuromusculair", "strides",
}

# Regex die een herhalingsmarker herkent: "4x", "3 x", "5×"
_REPS_RE = re.compile(r"^\s*(\d+)\s*[x×]\s*$", re.IGNORECASE)

# Regex voor een step-regel: "- 8m 95% 85rpm" of "• 5m ramp 45-65%"
_STEP_RE = re.compile(r"^\s*[-•·]\s+(.+)$")


def _parse_workout_description(description: str) -> list[tuple[str, str]]:
    """Parse een workout description naar (kind, text) tuples.

    Kind is een van: section, reps, step, note, blank.
    Laat onbekende regels als 'note' doorvallen zodat niks verloren gaat.
    """
    out: list[tuple[str, str]] = []
    if not description:
        return out

    for raw_line in description.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            out.append(("blank", ""))
            continue

        # Section header? (exact match, case-insensitive, evt met ":")
        stripped = line.strip().rstrip(":").lower()
        if stripped in _SECTION_LABELS:
            out.append(("section", line.strip().rstrip(":")))
            continue

        # Reps marker?
        reps_match = _REPS_RE.match(line)
        if reps_match:
            out.append(("reps", f"{reps_match.group(1)}×"))
            continue

        # Step (begint met - of •)
        step_match = _STEP_RE.match(line)
        if step_match:
            out.append(("step", step_match.group(1)))
            continue

        # Alles anders = coach commentaar / note
        out.append(("note", line.strip()))

    return out


def human_line(sentence: str, numbers: Optional[str] = None) -> None:
    """Een menselijke zin met optioneel de ruwe getallen klein eronder.

    Voorbeeld: human_line("Je basis groeit gestaag.", "CTL 44 · TSB +3")
    """
    num_html = f'<span class="numbers">{numbers}</span>' if numbers else ""
    st.markdown(
        f'<div class="ui-human-line">{sentence}{num_html}</div>',
        unsafe_allow_html=True,
    )


def morning_checkin(
    existing: Optional[dict] = None,
    key_prefix: str = "checkin",
) -> Optional[dict]:
    """Render de morning check-in (4 sliders) en return de waardes bij submit.

    Args:
        existing: huidig record uit history_db.get_wellness(today) — wordt
            gebruikt om de sliders te pre-fillen. None = eerste keer invullen.
        key_prefix: uniek prefix voor session-state keys.

    Returns:
        None als er niet is ingevuld/opgeslagen.
        Dict {sleep_score, energy, soreness, motivation} bij submit.
    """
    st.markdown(
        '<div class="ui-checkin">'
        '<div class="ci-title">Morning check-in</div>'
        '<div class="ci-subtitle">Hoe voel je je vandaag? 30 sec, stuurt je training aan.</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    defaults = existing or {}
    sleep = st.slider(
        "Slaap",
        min_value=1, max_value=5,
        value=int(defaults.get("sleep_score") or 3),
        key=f"{key_prefix}_sleep",
        help="1 = slecht geslapen, 5 = diep en lang",
    )
    energy = st.slider(
        "Energie",
        min_value=1, max_value=5,
        value=int(defaults.get("energy") or 3),
        key=f"{key_prefix}_energy",
        help="1 = leeg, 5 = bruisend",
    )
    soreness = st.slider(
        "Spierpijn (omgekeerd: 5 = geen pijn)",
        min_value=1, max_value=5,
        value=int(defaults.get("soreness") or 3),
        key=f"{key_prefix}_soreness",
        help="1 = overal pijn, 5 = fris en ontspannen",
    )
    motivation = st.slider(
        "Motivatie",
        min_value=1, max_value=5,
        value=int(defaults.get("motivation") or 3),
        key=f"{key_prefix}_motivation",
        help="1 = geen zin, 5 = ik wil NU trainen",
    )

    col_save, col_skip = st.columns([2, 1])
    submitted = col_save.button(
        "Opslaan", key=f"{key_prefix}_save", use_container_width=True
    )
    col_skip.button("Later", key=f"{key_prefix}_skip")

    if submitted:
        return {
            "sleep_score": sleep,
            "energy": energy,
            "soreness": soreness,
            "motivation": motivation,
        }
    return None


def workout_details(description: str) -> None:
    """Render de workout structuur in een leesbare, getypeerde weergave.

    Parsert de description naar sections (Warmup/Main/Cooldown), rep-
    markers (4x), steps en notes. Kleurt de delen volgens het palet:
    accent voor section labels, warning voor rep counts, body voor steps,
    gedimd italic voor notes.
    """
    if not description or not description.strip():
        return

    parsed = _parse_workout_description(description)
    if not parsed:
        return

    # Build HTML
    parts = ['<div class="ui-workout-details">']
    in_notes = False  # flip na de eerste niet-step/section/reps note-block
    last_was_step_like = False

    for kind, text in parsed:
        if kind == "blank":
            if last_was_step_like:
                parts.append("")  # whitespace line
            continue

        safe = (
            text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
        )

        if kind == "section":
            parts.append(f'<span class="wd-section">{safe}</span>')
            last_was_step_like = True
            in_notes = False
        elif kind == "reps":
            parts.append(f'<span class="wd-reps">{safe}</span>')
            last_was_step_like = True
        elif kind == "step":
            parts.append(f'<span class="wd-step">• {safe}</span>')
            last_was_step_like = True
        elif kind == "note":
            # Notes aan het einde (na alle steps) krijgen de 'wd-note' stijl;
            # notes tussendoor krijgen ook muted styling maar inline.
            parts.append(f'<span class="wd-note">{safe}</span>')
            last_was_step_like = False
            in_notes = True

    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)
