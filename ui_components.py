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

from datetime import date
from typing import Optional, Literal

import streamlit as st


# ── GLOBAL CSS ─────────────────────────────────────────────────────────────

_GLOBAL_CSS_INJECTED_KEY = "_ui_global_css_injected"

# Placeholder CSS. Fase 1 vervangt dit door de volledige design-taal.
# Voor nu: hide Streamlit chrome, smalle mobile-first container, basis dark
# mode met warme accent. Geen Google Fonts nog — komt in Fase 1.
_GLOBAL_CSS = """
<style>
    /* Reset + hide Streamlit chrome */
    #MainMenu, footer, header { visibility: hidden; }

    /* Mobile-first container: 680px max zoals huidige app */
    .block-container {
        max-width: 680px !important;
        padding-top: 1.5rem !important;
        padding-bottom: 4rem !important;
    }

    /* Typography baseline — Fase 1 vervangt families */
    html, body, [class*="css"] {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
                     system-ui, sans-serif;
    }

    /* Section header — klein, uppercase, letterspacing */
    .ui-section-header {
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.12em;
        color: #8A8680;
        font-weight: 600;
        margin: 1.5rem 0 0.4rem 0;
    }

    /* Coach card — warme quote styling */
    .ui-coach-card {
        border-left: 3px solid #E56A3E;
        padding: 0.9rem 1.1rem 0.9rem 1.2rem;
        margin: 0.8rem 0;
        background: rgba(229, 106, 62, 0.04);
        border-radius: 0 10px 10px 0;
        font-size: 0.94rem;
        line-height: 1.65;
        color: #2a2a2a;
    }
    .ui-coach-card.tone-positive {
        border-left-color: #5B8C5A;
        background: rgba(91, 140, 90, 0.05);
    }
    .ui-coach-card.tone-warning {
        border-left-color: #D4A24C;
        background: rgba(212, 162, 76, 0.06);
    }
    .ui-coach-card.tone-alert {
        border-left-color: #B84646;
        background: rgba(184, 70, 70, 0.05);
    }

    /* Today hero — grote workout card */
    .ui-today-hero {
        padding: 1.4rem 1.6rem;
        margin: 0.6rem 0 1.2rem 0;
        background: linear-gradient(135deg, #fbfaf7 0%, #f5f1ea 100%);
        border: 1px solid #e8e2d6;
        border-radius: 18px;
    }
    .ui-today-hero .label {
        font-size: 0.7rem;
        text-transform: uppercase;
        letter-spacing: 0.12em;
        color: #8A8680;
        font-weight: 600;
        margin-bottom: 0.4rem;
    }
    .ui-today-hero .title {
        font-size: 1.5rem;
        font-weight: 700;
        color: #0E0F12;
        line-height: 1.25;
        margin-bottom: 0.25rem;
    }
    .ui-today-hero .stats {
        font-size: 0.82rem;
        color: #8A8680;
        margin-bottom: 0.9rem;
    }
    .ui-today-hero .note {
        font-size: 0.9rem;
        color: #3d3b38;
        line-height: 1.6;
        padding-top: 0.8rem;
        border-top: 1px solid rgba(14, 15, 18, 0.08);
    }

    /* Day card — één dag in weekview */
    .ui-day-card {
        padding: 0.85rem 1.1rem;
        border-radius: 12px;
        margin: 0.35rem 0;
        border: 1px solid #f0ede6;
        background: white;
    }
    .ui-day-card.status-done { opacity: 0.65; }
    .ui-day-card.status-missed { border-color: rgba(184, 70, 70, 0.25); }
    .ui-day-card .day {
        font-size: 0.7rem;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        color: #8A8680;
        font-weight: 600;
    }
    .ui-day-card .name {
        font-size: 0.96rem;
        font-weight: 600;
        color: #0E0F12;
        margin-top: 0.15rem;
    }
    .ui-day-card .reason {
        font-size: 0.8rem;
        color: #6b6661;
        margin-top: 0.3rem;
        line-height: 1.5;
    }

    /* Stat inline — klein grijs tabular */
    .ui-stat-inline {
        display: inline-block;
        font-variant-numeric: tabular-nums;
        font-size: 0.8rem;
        color: #8A8680;
        margin-right: 0.9rem;
    }
    .ui-stat-inline .label {
        text-transform: uppercase;
        letter-spacing: 0.08em;
        font-size: 0.66rem;
        margin-right: 0.25rem;
    }
    .ui-stat-inline .value {
        color: #0E0F12;
        font-weight: 600;
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
