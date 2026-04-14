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
from datetime import date, timedelta
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

    /* ── Day header — groot datum-label boven dag-blok ────────── */
    .ui-day-header {
        display: flex;
        align-items: baseline;
        gap: 0.55rem;
        margin: 1.4rem 0 0.4rem 0;
        padding-bottom: 0.35rem;
        border-bottom: 1px solid var(--border);
    }
    .ui-day-header.is-today {
        border-bottom-color: var(--accent-border);
    }
    .ui-day-header .dh-weekday {
        font-family: var(--font-display);
        font-size: 1.3rem;
        font-weight: 600;
        color: var(--text);
        letter-spacing: -0.01em;
    }
    .ui-day-header.is-today .dh-weekday {
        color: var(--accent);
    }
    .ui-day-header .dh-date {
        font-family: var(--font-mono);
        font-size: 0.78rem;
        color: var(--text-muted);
        font-variant-numeric: tabular-nums;
    }
    .ui-day-header .dh-tag {
        margin-left: auto;
        font-size: 0.62rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.14em;
        color: var(--accent);
    }

    /* ── Day card — één dag in weekview ──────────────────────── */
    .ui-day-card {
        padding: 1rem 1.2rem 1rem 1.4rem;
        border-radius: 14px;
        margin: 0.4rem 0;
        border: 1px solid var(--border);
        background: var(--bg-raised);
        transition: border-color 0.15s ease, transform 0.15s ease;
        position: relative;
    }
    .ui-day-card:hover {
        border-color: var(--border-strong);
    }
    /* Accent-streepje links voor today */
    .ui-day-card.status-today {
        border-color: var(--accent-border);
        background: linear-gradient(90deg, var(--accent-bg) 0%, var(--bg-raised) 60%);
    }
    .ui-day-card.status-today::before {
        content: "";
        position: absolute;
        left: 0; top: 14%; bottom: 14%;
        width: 3px;
        background: var(--accent);
        border-radius: 0 3px 3px 0;
    }
    /* Done: subtiele ✓ linksonder, minder vrolijk dan een groene badge */
    .ui-day-card.status-done {
        opacity: 0.55;
        background: transparent;
    }
    .ui-day-card.status-done .day::after {
        content: " ✓";
        color: var(--positive);
        font-weight: 600;
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
        font-size: 1.05rem;
        font-weight: 600;
        color: var(--text);
        margin-top: 0.2rem;
        letter-spacing: -0.01em;
        line-height: 1.3;
    }
    .ui-day-card .reason {
        font-size: 0.78rem;
        color: var(--text-muted);
        margin-top: 0.4rem;
        line-height: 1.55;
        font-variant-numeric: tabular-nums;
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

    /* ── Streamlit slider polish — terracotta thumb + track ──── */
    .stSlider [data-baseweb="slider"] {
        padding: 0.5rem 0;
    }
    /* Track achtergrond */
    .stSlider [data-baseweb="slider"] > div:first-child {
        background: var(--border) !important;
        height: 3px !important;
    }
    /* Actieve fill (links van de thumb) */
    .stSlider [data-baseweb="slider"] > div:first-child > div {
        background: var(--accent) !important;
    }
    /* Thumb knop */
    .stSlider [role="slider"] {
        background: var(--accent) !important;
        border-color: var(--accent) !important;
        box-shadow: 0 0 0 4px rgba(196, 96, 60, 0.15) !important;
    }
    /* Min/max labels */
    .stSlider [data-testid="stTickBarMin"],
    .stSlider [data-testid="stTickBarMax"] {
        color: var(--text-dim) !important;
        font-family: var(--font-body) !important;
        font-size: 0.66rem !important;
    }
    /* Huidige waarde (bubble boven thumb) */
    .stSlider [data-baseweb="tooltip"] {
        background: var(--bg-elevated) !important;
        color: var(--text) !important;
        border: 1px solid var(--accent-border) !important;
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
    @media (max-width: 640px) {
        .ui-checkin { padding: 1rem 1rem; }
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
        font-size: 0.82rem;
        color: var(--text-muted);
        margin-bottom: 1rem;
    }

    /* Segmented-control label styling (pill-based check-in) */
    .ui-checkin ~ div [data-testid="stSegmentedControl"] label,
    .ui-checkin ~ div label[data-testid="stWidgetLabel"] {
        font-family: var(--font-body);
        font-size: 0.78rem !important;
        color: var(--text-muted) !important;
        text-transform: uppercase;
        letter-spacing: 0.08em;
    }
    /* Pills stretchen over volle breedte zodat tap-targets op mobiel groot zijn */
    .ui-checkin ~ div [data-testid="stSegmentedControl"] > div {
        width: 100%;
    }
    .ui-checkin ~ div [data-testid="stSegmentedControl"] button {
        flex: 1 1 0 !important;
        min-height: 44px;
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
    """Inject de globale CSS bij elke Streamlit run.

    Streamlit wist de DOM bij iedere rerun — een session_state guard zou
    ervoor zorgen dat CSS alleen de eerste run wordt geladen, waarna
    dark mode verdwijnt zodra de gebruiker interacteert. Daarom
    unconditioneel injecteren.
    """
    st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)


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


_MONTHS_NL = {
    1: "jan", 2: "feb", 3: "mrt", 4: "apr", 5: "mei", 6: "jun",
    7: "jul", 8: "aug", 9: "sep", 10: "okt", 11: "nov", 12: "dec",
}


def day_header(day_date: date, is_today: bool = False, tag: Optional[str] = None) -> None:
    """Groot datum-label als sectie-scheider boven alle events van een dag.

    Zorgt dat je in de weekview direct ziet 'dit is Dinsdag', ook als de
    dag meerdere sessies heeft.
    """
    weekday = ["Maandag", "Dinsdag", "Woensdag", "Donderdag", "Vrijdag", "Zaterdag", "Zondag"][day_date.weekday()]
    date_label = f"{day_date.day} {_MONTHS_NL[day_date.month]}"
    today_class = " is-today" if is_today else ""
    tag_html = f'<span class="dh-tag">{tag}</span>' if tag else ""
    st.markdown(
        f'<div class="ui-day-header{today_class}">'
        f'<span class="dh-weekday">{weekday}</span>'
        f'<span class="dh-date">{date_label}</span>'
        f'{tag_html}'
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


_AVAIL_OPTIONS = [0, 30, 60, 90, 120, 150, 180, 210, 240]


def _avail_fmt(m: int) -> str:
    if m == 0:
        return "rust"
    if m % 60 == 0:
        return f"{m // 60}u"
    return f"{m // 60}u{m % 60:02d}"


def _minutes_fmt(m: int) -> str:
    """Format minuten als '1u 40m' / '45m' / '2u'. Voor budget-meldingen."""
    if m <= 0:
        return "0m"
    h, mm = divmod(int(m), 60)
    if h and mm:
        return f"{h}u {mm}m"
    if h:
        return f"{h}u"
    return f"{mm}m"


def availability_editor(
    week_start: date,
    weekly_tss_target: int,
    key_prefix: str = "avail",
) -> Optional[dict[str, int]]:
    """Render de beschikbaarheids-editor voor een week.

    Slider per dag in stappen van 30 min (max 240). Toont totaal en een
    waarschuwing als het TSS-doel niet haalbaar is met de opgegeven tijd.

    Returnt de nieuwe waardes wanneer de gebruiker op 'Opslaan' klikt,
    anders None. Caller is verantwoordelijk voor persisteren + replan.
    """
    from agents import availability as av

    # Als de week nog leeg is, pak de waardes van de vorige week als default.
    av.copy_from_prev_week(week_start)
    current = av.get_week(week_start)

    st.markdown(
        '<div class="ui-section-header">Beschikbaarheid deze week</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Per dag hoeveel tijd heb je? Stappen van 30 min, max 4 uur. "
        "Dagen op 'rust' worden overgeslagen bij het plannen."
    )

    new_values: dict[str, int] = {}
    dirty = False
    for i, day_name in enumerate(["Ma", "Di", "Wo", "Do", "Vr", "Za", "Zo"]):
        d = week_start + timedelta(days=i)
        key_iso = d.isoformat()
        default = current.get(key_iso) or 0
        state_key = f"{key_prefix}_val_{key_iso}"
        if state_key not in st.session_state:
            st.session_state[state_key] = default if default in _AVAIL_OPTIONS else 0
        cur = st.session_state[state_key]

        def _step(delta: int, k: str = state_key) -> None:
            idx = _AVAIL_OPTIONS.index(st.session_state[k])
            new_idx = max(0, min(len(_AVAIL_OPTIONS) - 1, idx + delta))
            st.session_state[k] = _AVAIL_OPTIONS[new_idx]

        cols = st.columns([1.2, 0.8, 1.4, 0.8])
        cols[0].markdown(
            f'<div style="padding-top: 0.45rem; font-weight: 600; '
            f'color: var(--text); font-size: 0.9rem;">'
            f'{day_name} <span style="color: var(--text-muted); font-weight: 400; '
            f'font-size: 0.78rem;">{d.day}/{d.month}</span></div>',
            unsafe_allow_html=True,
        )
        cols[1].button(
            "−", key=f"{key_prefix}_dec_{key_iso}",
            on_click=_step, args=(-1,),
            disabled=(cur == 0), use_container_width=True,
        )
        cols[2].markdown(
            f'<div style="padding-top: 0.45rem; text-align: center; '
            f'font-weight: 600; color: var(--text); font-size: 0.95rem; '
            f'font-variant-numeric: tabular-nums;">{_avail_fmt(cur)}</div>',
            unsafe_allow_html=True,
        )
        cols[3].button(
            "+", key=f"{key_prefix}_inc_{key_iso}",
            on_click=_step, args=(1,),
            disabled=(cur == _AVAIL_OPTIONS[-1]), use_container_width=True,
        )

        new_values[key_iso] = int(cur)
        if (current.get(key_iso) or 0) != cur:
            dirty = True

    # Auto-save: elke step-klik triggert rerun, hier persistereren we
    # direct zodat waardes niet verloren gaan als gebruiker wegnavigeert.
    if dirty:
        av.set_week(week_start, new_values)

    # Totaal + budget-check
    total_min = sum(new_values.values())
    needed = int(round((weekly_tss_target / av.TSS_PER_HOUR) * 60))
    shortfall = max(0, needed - total_min)

    status_color = "var(--positive)" if shortfall == 0 else "var(--warning)"
    status_msg = (
        f"Budget: {_minutes_fmt(total_min)} beschikbaar / ~{_minutes_fmt(needed)} "
        f"nodig voor {weekly_tss_target} TSS"
    )
    if shortfall > 0:
        status_msg += f" — <b>tekort {_minutes_fmt(shortfall)}</b>"

    st.markdown(
        f'<div style="margin-top: 0.8rem; padding: 0.7rem 1rem; '
        f'background: var(--bg-raised); border-left: 3px solid {status_color}; '
        f'border-radius: 6px; font-size: 0.85rem; color: var(--text);">'
        f'{status_msg}</div>',
        unsafe_allow_html=True,
    )

    # Replan-knop: waardes zijn al opgeslagen, deze triggert puur een herplan.
    if st.button("Week opnieuw plannen", key=f"{key_prefix}_save",
                 use_container_width=True):
        return new_values
    return None


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
    opts = [1, 2, 3, 4, 5]

    def _pick(label: str, default: int, field_key: str, help_text: str) -> int:
        val = st.segmented_control(
            label,
            options=opts,
            default=default,
            key=f"{key_prefix}_{field_key}",
            help=help_text,
        )
        return int(val) if val is not None else default

    sleep = _pick(
        "Slaap", int(defaults.get("sleep_score") or 3), "sleep",
        "1 = slecht geslapen, 5 = diep en lang",
    )
    energy = _pick(
        "Energie", int(defaults.get("energy") or 3), "energy",
        "1 = leeg, 5 = bruisend",
    )
    soreness = _pick(
        "Frisheid (5 = geen pijn)", int(defaults.get("soreness") or 3), "soreness",
        "1 = overal pijn, 5 = fris en ontspannen",
    )
    motivation = _pick(
        "Motivatie", int(defaults.get("motivation") or 3), "motivation",
        "1 = geen zin, 5 = ik wil NU trainen",
    )

    submitted = st.button(
        "Opslaan", key=f"{key_prefix}_save", use_container_width=True,
    )

    if submitted:
        return {
            "sleep_score": sleep,
            "energy": energy,
            "soreness": soreness,
            "motivation": motivation,
        }
    return None


def workout_intent_box(workout: dict | None) -> None:
    """Render een donkere accent-box met de coach-intent boven de workout.

    Intent is 1-3 zinnen directe cue, geen vervanging voor de beschrijving.
    Stilhouden als workout None of geen type heeft — fallback zit in
    get_intent zelf, maar we tonen dan bewust niks ipv een generiek
    zinnetje dat niets toevoegt.
    """
    if not workout or not (workout.get("type") or workout.get("naam")):
        return
    try:
        from agents.workout_intent import get_intent
    except Exception:
        return
    msg = get_intent(workout)
    if not msg:
        return
    # Toon niet als het puur de default-fallback is — geen meerwaarde.
    if msg.startswith("Voer uit zoals beschreven"):
        return
    safe = (
        msg.replace("&", "&amp;")
           .replace("<", "&lt;")
           .replace(">", "&gt;")
    )
    st.markdown(
        f"""
        <div style="background: #17181C; border-left: 3px solid var(--accent, #C4603C);
                    border-radius: 8px; padding: 0.75rem 1rem; margin: 0.6rem 0;
                    color: #E8E5DF; font-family: Georgia, 'Times New Roman', serif;
                    font-style: italic; font-size: 0.95rem; line-height: 1.5;">
            <span style="font-size: 0.62rem; text-transform: uppercase; letter-spacing: 0.14em;
                         font-style: normal; font-family: Inter, sans-serif;
                         color: var(--accent, #C4603C); font-weight: 600;
                         display: block; margin-bottom: 0.35rem;">Coach-intent</span>
            {safe}
        </div>
        """,
        unsafe_allow_html=True,
    )


def workout_action_row(event: dict, key_prefix: str) -> None:
    """Render Swap / Shorten / Skip actie-rij met inline preview-expanders.

    Gebruikt agents.workout_actions voor de impact-preview. Bij 'Apply'
    wordt intervals_client aangeroepen en een st.rerun getriggerd.

    Simpel opgezet: 3 knoppen → 3 expanders naast elkaar. Geen modals.
    """
    if not event or not event.get("id"):
        return
    try:
        from agents import workout_actions as wa
        from agents.workout_library import SWAP_CATEGORIES
    except Exception:
        return

    event_id = str(event["id"])
    cols = st.columns(3)
    show_swap_key = f"{key_prefix}_act_swap"
    show_short_key = f"{key_prefix}_act_short"
    show_skip_key = f"{key_prefix}_act_skip"

    if cols[0].button("Swap", key=f"{key_prefix}_btn_swap", use_container_width=True):
        st.session_state[show_swap_key] = not st.session_state.get(show_swap_key, False)
    if cols[1].button("Shorten", key=f"{key_prefix}_btn_short", use_container_width=True):
        st.session_state[show_short_key] = not st.session_state.get(show_short_key, False)
    if cols[2].button("Skip", key=f"{key_prefix}_btn_skip", use_container_width=True):
        st.session_state[show_skip_key] = not st.session_state.get(show_skip_key, False)

    # ── SWAP expander ──────────────────────────────────────────────────
    if st.session_state.get(show_swap_key):
        with st.expander("Swap naar", expanded=True):
            cat_keys = list(SWAP_CATEGORIES.keys())
            chosen = st.radio(
                "Categorie",
                options=cat_keys,
                format_func=lambda k: SWAP_CATEGORIES[k]["label"],
                key=f"{key_prefix}_swap_cat",
                horizontal=True,
            )
            preview = wa.preview_swap(event, chosen)
            st.caption(preview.narrative)
            if st.button("Bevestig swap", key=f"{key_prefix}_swap_confirm"):
                try:
                    wa.apply_swap(event_id, chosen, event=event)
                    st.success("Workout geswitcht.")
                    st.session_state[show_swap_key] = False
                    st.rerun()
                except Exception as exc:
                    st.error(f"Swap mislukt: {exc}")

    # ── SHORTEN expander ───────────────────────────────────────────────
    if st.session_state.get(show_short_key):
        with st.expander("Inkorten", expanded=True):
            factor_label = st.radio(
                "Hoeveel korter?",
                options=["80% (lichte crop)", "60% (flink korter)"],
                key=f"{key_prefix}_short_factor",
                horizontal=True,
            )
            factor = 0.8 if factor_label.startswith("80") else 0.6
            preview = wa.preview_shorten(event, factor=factor)
            st.caption(preview.narrative)
            if st.button("Bevestig inkorten", key=f"{key_prefix}_short_confirm"):
                try:
                    wa.apply_shorten(event_id, factor, event=event)
                    st.success("Workout ingekort.")
                    st.session_state[show_short_key] = False
                    st.rerun()
                except Exception as exc:
                    st.error(f"Inkorten mislukt: {exc}")

    # ── SKIP expander ──────────────────────────────────────────────────
    if st.session_state.get(show_skip_key):
        with st.expander("Skip deze sessie", expanded=True):
            preview = wa.preview_skip(event)
            st.caption(preview.narrative)
            if st.button("Bevestig skip", key=f"{key_prefix}_skip_confirm"):
                try:
                    wa.apply_skip(event_id)
                    st.success("Workout geskipped.")
                    st.session_state[show_skip_key] = False
                    st.rerun()
                except Exception as exc:
                    st.error(f"Skip mislukt: {exc}")


def workout_structure_chart(workout: dict | None, actual_samples: list | None = None, height: int = 200, key: Optional[str] = None) -> None:
    """Toon de workout-structuur als Plotly area chart (zone-gekleurd).

    Wordt boven de tekstuele beschrijving getoond. Als de parser niks kan
    maken van de tekst, tonen we niks — de tekst-details staan er ook nog.
    """
    if not workout:
        return
    try:
        from viz.workout_chart import render_workout_chart, parse_workout_structure
    except Exception:
        return
    beschrijving = (workout.get("beschrijving") or workout.get("description") or "").strip()
    if not beschrijving:
        return
    # Skip chart als parser niks vindt — vermijdt lege placeholder-figuur.
    if not parse_workout_structure(beschrijving):
        return
    sport = workout.get("sport") or workout.get("type") or ""
    fig = render_workout_chart(
        {"beschrijving": beschrijving, "sport": sport},
        actual_samples=actual_samples,
        height=height,
    )
    if fig is None:
        return
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False}, key=key)


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


# ── ADAPTIVE ADJUSTMENT BANNER ────────────────────────────────────────────

def render_adjustment_banner() -> None:
    """Toon bovenaan de pagina wat het adaptive systeem heeft aangepast.

    Leest laatste actieve entry uit agents.adjustments_log. Als er geen is,
    toont niks. Twee acties: "Ziet er goed uit" (dismiss) en "Draai terug"
    (revert + reverseert wijzigingen in intervals.icu).
    """
    # Lokale imports — banner is optioneel, breek de app niet als iets mist
    try:
        from agents import adjustments_log
    except Exception:
        return

    entry = adjustments_log.get_active()
    if not entry:
        return

    narrative = entry.get("narrative", "")
    invariant = entry.get("invariant", "")
    modifications = entry.get("modifications", []) or []
    entry_id = entry.get("id", "")

    # Card styling — dark surface, witte headline, muted body
    st.markdown(
        f"""
        <div style="background: #1F1F1F; border: 1px solid #2E2E2E;
                    border-radius: 14px; padding: 1rem 1.1rem;
                    margin: 0 0 1rem 0; color: #F0F0F0;">
            <div style="font-size: 0.68rem; text-transform: uppercase;
                        letter-spacing: 0.12em; color: #9CC2FF; font-weight: 600;
                        margin-bottom: 0.35rem;">Plan bijgewerkt</div>
            <div style="font-size: 0.95rem; color: #F0F0F0; margin-bottom: 0.55rem;">
                {narrative or 'Week aangepast op basis van je laatste sessies.'}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Wijzigingen-lijst
    if modifications:
        with st.expander(f"Wijzigingen ({len(modifications)})", expanded=False):
            for mod in modifications:
                action = mod.get("action", "?")
                reason = mod.get("reason", "")
                before_name = (mod.get("before") or {}).get("name", "")
                after_name = (mod.get("after") or {}).get("name", "")
                tss_delta = mod.get("tss_delta", 0)
                if action == "create":
                    line = f"+ Nieuw: **{after_name}** ({tss_delta:+d} TSS)"
                elif action == "delete":
                    line = f"− Verwijderd: **{before_name}**"
                else:
                    line = f"~ **{before_name}** → **{after_name}** ({tss_delta:+d} TSS)"
                st.markdown(f"- {line}")
                if reason:
                    st.caption(f"  {reason}")

    if invariant:
        st.caption(invariant)

    # Actieknoppen
    col1, col2, _ = st.columns([1, 1, 2])
    if col1.button("Ziet er goed uit", key=f"banner_ok_{entry_id}"):
        adjustments_log.mark_dismissed(entry_id)
        st.rerun()
    if col2.button("Draai terug", key=f"banner_revert_{entry_id}"):
        try:
            revert_adjustment(entry_id)
            st.success("Wijzigingen teruggedraaid.")
        except Exception as exc:
            st.error(f"Revert mislukt: {exc}")
        adjustments_log.mark_reverted(entry_id)
        st.rerun()


def revert_adjustment(entry_id: str) -> None:
    """Draai alle modifications van entry_id terug in intervals.icu.

    - modify → herstel originele velden (name, description, load_target, duration)
    - create → verwijder het aangemaakte event
    - delete → maak opnieuw aan vanuit before
    """
    from datetime import date as _date
    from agents import adjustments_log
    import intervals_client as api

    entry = adjustments_log.get_by_id(entry_id)
    if not entry:
        return

    for mod in entry.get("modifications", []) or []:
        # Skip mods die nooit succesvol zijn toegepast — anders proberen we
        # iets terug te draaien dat nooit live ging (silent fail of crash).
        if not mod.get("applied", False):
            continue
        action = mod.get("action")
        event_id = mod.get("event_id", "")
        before = mod.get("before") or {}
        after = mod.get("after") or {}
        try:
            if action == "modify" and event_id:
                api.update_event(event_id, **{
                    k: v for k, v in before.items()
                    if k in ("name", "description", "load_target", "duration")
                })
            elif action == "create":
                # Bij 'create' is created_event_id het ID dat intervals.icu
                # teruggaf bij de POST. Dat is het enige waarmee we kunnen deleten.
                created_id = mod.get("created_event_id")
                if created_id:
                    api.delete_event(str(created_id))
                else:
                    # Best-effort: oude code-pad dat niet kon resolven —
                    # niet stilzwijgend negeren maar duidelijk melden.
                    raise ValueError(
                        "Kan create-mod niet reverten: geen created_event_id "
                        "(mod aangemaakt vóór per-mod tracking-fix)."
                    )
            elif action == "delete" and before:
                dt_raw = before.get("start_date_local", "")[:10]
                if dt_raw:
                    api.create_event(
                        event_date=_date.fromisoformat(dt_raw),
                        name=before.get("name", "Hersteld"),
                        description=before.get("description", ""),
                        category="WORKOUT",
                    )
        except Exception as exc:  # pragma: no cover
            # Log naar Streamlit maar ga door — best-effort revert
            try:
                st.warning(f"Revert step failed ({action} {event_id}): {exc}")
            except Exception:
                pass
