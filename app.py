"""
Sport Coach — Web UI (Streamlit)

    streamlit run app.py
"""

import os
import sys
import json
from datetime import date, timedelta
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))
import intervals_client as api
import config
import tp_sync_service
from agents import workout_library as lib
from agents import feedback_engine
from agents.workout_feel import get_feel_note
from trainingpeaks_errors import TPAPIError, TPAuthError, TPConversionError

STATE_PATH = Path(__file__).parent / "state.json"


# ── HELPERS ─────────────────────────────────────────────────────────────────

DAYS_NL = {0: "ma", 1: "di", 2: "wo", 3: "do", 4: "vr", 5: "za", 6: "zo"}
DAYS_FULL = {0: "Maandag", 1: "Dinsdag", 2: "Woensdag", 3: "Donderdag",
             4: "Vrijdag", 5: "Zaterdag", 6: "Zondag"}

DELAHAIJE_QUOTES = [
    "Volume triumphs quality all the time!",
    "Een gelukkige atleet is een snelle atleet.",
    "Ik ben dertig procent trainer, zeventig procent coach.",
    "Gelukkige atleten presteren beter.",
    "Pas wanneer de basis staat, bouw je snelheid en kracht op.",
    "Don't try to speed it up.",
    "De mitochondrien maken het niet uit of je ze traint door te fietsen of te lopen.",
    "Loop 4x10 min zo hard als je kunt, maar de laatste moet net zo snel zijn als de eerste.",
    "Welzijn staat altijd centraal.",
]


def this_monday():
    today = date.today()
    return today - timedelta(days=today.weekday())


def load_state():
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


@st.cache_data(ttl=120)
def fetch_week(monday_str: str):
    monday = date.fromisoformat(monday_str)
    sunday = monday + timedelta(days=6)
    # resolve=True bundelt workout_doc direct in elk event — nodig voor de
    # TP-sync knop op de Today Card (anders zou die nog een losse fetch
    # moeten doen per klik).
    events = api.get_events(monday, sunday, resolve=True)
    try:
        activities = api.get_activities(start=monday, end=sunday)
    except Exception:
        activities = []
    return events, activities


@st.cache_data(ttl=120)
def fetch_recent():
    try:
        return api.get_activities(start=date.today() - timedelta(days=7), end=date.today())
    except Exception:
        return []


@st.cache_data(ttl=300)
def fetch_recent_28d():
    """Activiteiten van afgelopen 28 dagen — voor 'vergelijkbare workouts'."""
    try:
        return api.get_activities(start=date.today() - timedelta(days=28), end=date.today())
    except Exception:
        return []


@st.cache_data(ttl=300)
def fetch_wellness_window(days: int = 14):
    """Wellness data — laatste N dagen, voor trend en vandaag-snapshot."""
    try:
        return api.get_wellness(start=date.today() - timedelta(days=days), end=date.today())
    except Exception:
        return []


def match_events_activities(events, activities):
    result = []
    for event in events:
        if event.get("category") != "WORKOUT":
            continue
        e_date = event.get("start_date_local", "")[:10]
        e_type = event.get("type", "")
        matched = None
        for act in activities:
            a_date = act.get("start_date_local", "")[:10]
            a_type = act.get("type", "")
            if a_date == e_date and types_match(e_type, a_type):
                matched = act
                break
        result.append({"event": event, "activity": matched, "done": matched is not None})
    result.sort(key=lambda x: x["event"].get("start_date_local", ""))
    return result


def types_match(et, at):
    if et in ("Run",) and at in ("Run",):
        return True
    if et in ("Ride", "VirtualRide") and at in ("Ride", "VirtualRide"):
        return True
    return et == at


def get_alternatives(event, category: str = "vergelijkbaar"):
    """Haal alternatieven op via de smart swap library."""
    return lib.get_swap_options(event, category, ftp=290)


def check_week_quality(matched_events: list, swap_event_id: str = None, swap_to: dict = None) -> dict:
    """Check of de week na een swap nog genoeg kwaliteitsprikkels heeft.

    Returns dict met has_enough_quality, quality_count, message.
    """
    quality_keywords = {"threshold", "sweetspot", "over-under", "tempo", "interval",
                        "vo2max", "tabata", "race sim", "marathon"}
    quality_count = 0

    for item in matched_events:
        event = item["event"]
        eid = event.get("id")
        name = (event.get("name") or "").lower()

        # Als dit het event is dat geswapped wordt, gebruik de nieuwe naam
        if swap_event_id and eid == swap_event_id and swap_to:
            name = swap_to.get("naam", "").lower()

        if any(q in name for q in quality_keywords):
            quality_count += 1

    has_enough = quality_count >= 1
    if quality_count == 0:
        message = "Let op: na deze swap heb je geen kwaliteitstraining meer deze week. Overweeg een andere dag harder te maken."
    elif quality_count == 1:
        message = "Je houdt 1 kwaliteitstraining over. Voldoende voor deze fase."
    else:
        message = f"{quality_count} kwaliteitstrainingen deze week."

    return {"has_enough_quality": has_enough, "quality_count": quality_count, "message": message}


def phase_to_human(phase: str, weeks_to_race: int) -> str:
    """Vertaal fase-code naar menselijke taal."""
    labels = {
        "herstel_opbouw_I": "We bouwen je fundament op",
        "herstel_opbouw_II": "De basis wordt sterker",
        "opbouw_I": "Volume groeit, de motor draait",
        "opbouw_II": "Stevige opbouw richting specifiek werk",
        "specifiek_I": "Marathonspecifiek — hier word je snel",
        "specifiek_II": "Piekbelasting, je bent bijna klaar",
        "taper": "Afbouw — vertrouw op het werk dat gedaan is",
        "race": "Race week. Dit is jouw moment.",
    }
    label = labels.get(phase, phase.replace("_", " ").title())
    return f"{label}. Nog {weeks_to_race} weken."


def ctl_to_human(ctl: float) -> str:
    """Vertaal CTL naar menselijke taal."""
    if ctl < 35:
        return "Je fitness is nog bescheiden. Elke week telt."
    elif ctl < 50:
        return "Je basis groeit. Je lichaam kan steeds meer aan."
    elif ctl < 65:
        return "Solide fitness. Je bent op de goede weg."
    elif ctl < 80:
        return "Sterke basis. Hier wordt het serieus."
    else:
        return "Topfitness. Je bent klaar voor de marathon."


# ── FEEDBACK GENERATION ────────────────────────────────────────────────────

@st.cache_data(ttl=600, show_spinner=False)
def _cached_gemini_call(activity_id, event_id, model_name: str, _prompt: str) -> str:
    """Streamlit-cached wrapper rond feedback_engine.gemini_call.

    `_prompt` heeft underscore-prefix → Streamlit hasht 'm niet.
    De andere 3 args (activity_id, event_id, model_name) zijn al uniek genoeg.
    """
    return feedback_engine.gemini_call(model_name, _prompt)


def generate_feedback(event, activity, matched=None):
    """Dunne wrapper om feedback_engine.generate_feedback met Streamlit-caching.

    Haalt de benodigde data via de @st.cache_data fetch_* helpers en geeft
    de cached call door als call_fn.
    """
    if not activity:
        return None

    state = load_state()
    wellness = fetch_wellness_window(days=14)
    recent_28d = fetch_recent_28d()

    # Wikkel de cached call zodat feedback_engine 'm kan aanroepen met (model, prompt)
    def call_fn(model_name: str, prompt: str) -> str:
        return _cached_gemini_call(
            activity.get("id"), event.get("id"), model_name, prompt
        )

    return feedback_engine.generate_feedback(
        event, activity,
        state=state,
        wellness_records=wellness,
        week_events=matched,
        recent_28d=recent_28d,
        call_fn=call_fn,
    )


# ── CUSTOM CSS ─────────────────────────────────────────────────────────────

CUSTOM_CSS = """
<style>
    /* ── Foundation ─────────────────────────────────────── */
    .block-container {
        max-width: 680px !important;
        padding-top: 1.5rem !important;
        padding-bottom: 3rem !important;
    }
    h1, h2, h3 {
        font-weight: 600 !important;
        letter-spacing: -0.03em !important;
        color: #1a1a1a !important;
    }
    h1 { font-size: 1.6rem !important; }
    h3 { font-size: 1.05rem !important; margin-bottom: 0.2rem !important; }

    /* Kill default Streamlit metric chrome */
    .stMetric label { font-size: 0.7rem !important; color: #999 !important; text-transform: uppercase; letter-spacing: 0.05em; }
    .stMetric [data-testid="stMetricValue"] { font-size: 1.05rem !important; font-weight: 600 !important; }

    /* ── Today Card ────────────────────────────────────── */
    .today-card {
        background: linear-gradient(135deg, #f4f8ee 0%, #eaf0dd 100%);
        border: 1px solid #d4dfc4;
        border-radius: 16px;
        padding: 1.6rem 1.8rem 1.4rem 1.8rem;
        margin: 0.5rem 0 1.5rem 0;
    }
    .today-card .today-label {
        font-size: 0.7rem;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        color: #6b8a4e;
        font-weight: 600;
        margin-bottom: 0.3rem;
    }
    .today-card .today-title {
        font-size: 1.3rem;
        font-weight: 700;
        color: #1a2e0a;
        line-height: 1.3;
        margin-bottom: 0.15rem;
    }
    .today-card .today-sport {
        font-size: 0.82rem;
        color: #6b8a4e;
        margin-bottom: 0.6rem;
    }
    .today-card .today-feel {
        font-size: 0.88rem;
        color: #3d5a1e;
        line-height: 1.55;
        background: rgba(255,255,255,0.55);
        border-radius: 10px;
        padding: 0.7rem 1rem;
        margin-top: 0.5rem;
    }

    /* ── Workout Row ───────────────────────────────────── */
    .workout-row {
        padding: 0.75rem 1rem;
        border-radius: 12px;
        margin: 0.25rem 0;
        transition: background 0.15s;
    }
    .workout-row:hover { background: #fafafa; }
    .workout-row.is-done { opacity: 0.7; }
    .workout-row .wr-day {
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #999;
        font-weight: 600;
    }
    .workout-row .wr-name {
        font-size: 0.95rem;
        font-weight: 600;
        color: #1a1a1a;
        line-height: 1.3;
    }
    .workout-row .wr-stats {
        font-size: 0.78rem;
        color: #888;
        margin-top: 0.15rem;
    }
    .wr-check {
        display: inline-block;
        width: 20px; height: 20px;
        border-radius: 50%;
        text-align: center;
        line-height: 20px;
        font-size: 0.7rem;
        margin-right: 0.5rem;
        flex-shrink: 0;
    }
    .wr-check.done { background: #2d5016; color: white; }
    .wr-check.pending { border: 2px solid #ddd; background: white; }

    /* ── Coach Feedback ────────────────────────────────── */
    .coach-feedback {
        background: #faf9f7;
        border-radius: 14px;
        padding: 1.3rem 1.5rem;
        margin: 0.5rem 0 1rem 0;
        border: 1px solid #eee;
        font-size: 0.92rem;
        line-height: 1.65;
        color: #2a2a2a;
    }
    .coach-feedback .coach-avatar {
        font-size: 0.72rem;
        font-weight: 600;
        color: #999;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        margin-bottom: 0.5rem;
    }
    .coach-quote {
        color: #888;
        font-style: italic;
        margin-top: 0.8rem;
        padding-top: 0.6rem;
        border-top: 1px solid #eee;
        font-size: 0.82rem;
    }

    /* ── Feel Note ─────────────────────────────────────── */
    .feel-note {
        background: #f7f5f0;
        border-radius: 10px;
        padding: 0.7rem 1rem;
        margin: 0.3rem 0 0.6rem 0;
        font-size: 0.85rem;
        color: #555;
        line-height: 1.5;
    }

    /* ── Week Progress ─────────────────────────────────── */
    .week-progress {
        font-size: 0.78rem;
        color: #999;
        font-weight: 500;
        letter-spacing: 0.02em;
        margin-bottom: 0.3rem;
    }
    /* Streamlit progress bar color override */
    .stProgress > div > div > div > div {
        background-color: #2d5016 !important;
        border-radius: 8px !important;
    }
    .stProgress > div > div > div {
        background-color: #eee !important;
        border-radius: 8px !important;
    }

    /* ── Sidebar ───────────────────────────────────────── */
    section[data-testid="stSidebar"] {
        background: #fafaf8 !important;
        border-right: 1px solid #eee !important;
    }
    section[data-testid="stSidebar"] .block-container {
        padding-top: 2rem !important;
    }
    .sidebar-phase {
        font-size: 1.0rem;
        font-weight: 600;
        color: #1a1a1a;
        line-height: 1.45;
        margin-bottom: 0.3rem;
    }
    .sidebar-fitness {
        font-size: 0.85rem;
        color: #666;
        line-height: 1.5;
        margin-bottom: 1rem;
    }
    .sidebar-weeks {
        display: inline-block;
        background: #2d5016;
        color: white;
        font-size: 0.72rem;
        font-weight: 600;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        padding: 0.3rem 0.8rem;
        border-radius: 20px;
        margin-bottom: 1rem;
    }

    /* Hide Streamlit branding */
    #MainMenu, footer, header { visibility: hidden; }

    /* Button styling */
    .stButton > button {
        border-radius: 8px !important;
        font-size: 0.8rem !important;
        padding: 0.25rem 0.75rem !important;
        border: 1px solid #ddd !important;
        background: white !important;
        color: #555 !important;
        font-weight: 500 !important;
    }
    .stButton > button:hover {
        border-color: #2d5016 !important;
        color: #2d5016 !important;
    }

    /* Divider subtler */
    hr { border-color: #f0f0f0 !important; }
</style>
"""


# ── PAGE CONFIG ─────────────────────────────────────────────────────────────

st.set_page_config(page_title="Coach", page_icon="", layout="centered")
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

state = load_state()
monday = this_monday()

# ── SIDEBAR ────────────────────────────────────────────────────────────────

with st.sidebar:
    # Menselijke context eerst — dat is wat telt
    ctl = state.get("load", {}).get("ctl_estimate", 0)
    phase = state.get("current_phase", "herstel_opbouw_I")
    race_date = state.get("race_date", "2026-10-18")
    weeks_left = max(0, (date.fromisoformat(race_date) - date.today()).days // 7)

    st.markdown(f'<div class="sidebar-weeks">Nog {weeks_left} weken</div>',
                unsafe_allow_html=True)

    phase_label = phase_to_human(phase, weeks_left)
    # Split de fase-zin (voor de punt) van het "Nog X weken" deel (dat staat al hierboven)
    phase_main = phase_label.split(". Nog")[0]
    st.markdown(f'<div class="sidebar-phase">{phase_main}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sidebar-fitness">{ctl_to_human(ctl)}</div>', unsafe_allow_html=True)

    st.markdown("")  # spacing
    week_offset = st.slider("Week", -4, 8, 0, label_visibility="collapsed")
    selected_monday = monday + timedelta(weeks=week_offset)
    if week_offset == 0:
        st.caption("Deze week")
    else:
        st.caption(f"{selected_monday.strftime('%d %b')} — {(selected_monday + timedelta(days=6)).strftime('%d %b')}")

    st.markdown("")  # spacing

    # Compacte metrics — klein en onderaan
    c1, c2 = st.columns(2)
    c1.metric("Fitness", f"{ctl:.0f}")
    c2.metric("Frisheid", f"{state.get('load', {}).get('tsb_estimate', 0):+.0f}")

    st.markdown("")
    if st.button("Ververs", use_container_width=True):
        st.cache_data.clear()

    # ── TrainingPeaks-sync status (alleen als feature-flag aan staat) ──
    if config.get_bool("TP_SYNC_ENABLED", default=False):
        st.markdown("")
        tp_status = st.session_state.get("tp_connection_status")
        if tp_status is None:
            st.caption("TP: onbekend")
        elif tp_status["ok"]:
            st.caption(f"TP: ✅ {tp_status['message']}")
        else:
            st.caption(f"TP: ❌ {tp_status['message']}")
        if st.button("Test TP verbinding", use_container_width=True):
            cookie = config.get_secret("TP_AUTH_COOKIE") or ""
            ok, msg = tp_sync_service.check_connection(cookie)
            st.session_state["tp_connection_status"] = {"ok": ok, "message": msg}
            st.rerun()


# ── MAIN ───────────────────────────────────────────────────────────────────

events, activities = fetch_week(selected_monday.isoformat())
recent = fetch_recent()
matched = match_events_activities(events, activities)

if not matched:
    quote = DELAHAIJE_QUOTES[date.today().timetuple().tm_yday % len(DELAHAIJE_QUOTES)]
    st.markdown(f"Geen workouts deze week.")
    st.markdown(f'<div class="coach-quote">"{quote}"</div>', unsafe_allow_html=True)
    st.stop()

# ── TODAY CARD (als we deze week bekijken) ─────────────────────────────────

today_str = date.today().isoformat()
today_event = None
if week_offset == 0:
    for item in matched:
        e_date = item["event"].get("start_date_local", "")[:10]
        if e_date == today_str and not item["done"]:
            today_event = item
            break

if today_event:
    event = today_event["event"]
    e_name = event.get("name", "")
    e_type = event.get("type", "")
    sport = "Hardlopen" if e_type == "Run" else "Fietsen"

    feel = get_feel_note(event)
    feel_html = f'<div class="today-feel">{feel}</div>' if feel else ""

    st.markdown(
        f'<div class="today-card">'
        f'<div class="today-label">Vandaag</div>'
        f'<div class="today-title">{e_name}</div>'
        f'<div class="today-sport">{sport}</div>'
        f'{feel_html}'
        f'</div>',
        unsafe_allow_html=True
    )

    # Sync-knop + Wissel-knop. TP-sync alleen tonen als:
    # (1) feature-flag aan staat
    # (2) sport wordt ondersteund
    # (3) event nog niet is gesynced in state.json
    tp_enabled = config.get_bool("TP_SYNC_ENABLED", default=False)
    tp_supported = e_type in tp_sync_service.SUPPORTED_SPORTS
    event_id = str(event.get("id", ""))
    tp_existing = tp_sync_service.is_synced(event_id) if tp_enabled else None

    if tp_enabled and tp_supported:
        _, col_tp, col_swap = st.columns([4, 1, 1])
    else:
        _, col_swap = st.columns([5, 1])
        col_tp = None

    if col_tp is not None:
        with col_tp:
            if tp_existing:
                st.caption(f"✅ TP")
            else:
                # Double-submit guard via session_state — Streamlit rerunt
                # bij elke interactie, dus zonder dit kan dubbele push.
                pending_key = f"tp_sync_pending_{event_id}"
                if st.button("→ TP", key=f"tp_sync_{event_id}",
                             disabled=st.session_state.get(pending_key, False)):
                    st.session_state[pending_key] = True
                    cookie = config.get_secret("TP_AUTH_COOKIE") or ""
                    try:
                        result = tp_sync_service.sync_event(event, cookie)
                        st.session_state["tp_sync_flash"] = {
                            "ok": True,
                            "msg": f"Gesynced naar TP (workoutId {result['tp_workout_id']})"
                        }
                    except TPAuthError as exc:
                        st.session_state["tp_sync_flash"] = {
                            "ok": False,
                            "msg": f"Cookie verlopen — {exc}",
                        }
                    except TPConversionError as exc:
                        st.session_state["tp_sync_flash"] = {
                            "ok": False, "msg": f"Conversie mislukt — {exc}"
                        }
                    except TPAPIError as exc:
                        st.session_state["tp_sync_flash"] = {
                            "ok": False, "msg": f"TP API fout — {exc}"
                        }
                    finally:
                        st.session_state[pending_key] = False
                    st.rerun()

    with col_swap:
        if st.button("Wissel", key="swap_today"):
            st.session_state["show_swap_today"] = True

    # Flash message na sync-actie (overleeft de rerun)
    flash = st.session_state.pop("tp_sync_flash", None)
    if flash:
        if flash["ok"]:
            st.success(flash["msg"])
        else:
            st.error(flash["msg"])

    if st.session_state.get("show_swap_today"):
        swap_cat_key = "swap_cat_today"
        if swap_cat_key not in st.session_state:
            st.caption("Wat wil je?")
            cat_cols = st.columns(4)
            for ci, (cat_id, cat_info) in enumerate(lib.SWAP_CATEGORIES.items()):
                if cat_cols[ci].button(cat_info["label"], key=f"cat_today_{cat_id}"):
                    st.session_state[swap_cat_key] = cat_id
                    st.rerun()
            if st.button("Annuleer", key="cancel_swap_today"):
                st.session_state["show_swap_today"] = False
                st.rerun()
        else:
            chosen_cat = st.session_state[swap_cat_key]
            alts = get_alternatives(event, category=chosen_cat)
            if alts:
                for j, alt in enumerate(alts):
                    quality_warning = ""
                    if chosen_cat == "makkelijker":
                        qcheck = check_week_quality(matched, event.get("id"), alt)
                        if not qcheck["has_enough_quality"]:
                            quality_warning = qcheck["message"]
                    c1, c2 = st.columns([5, 1])
                    c1.write(f"{alt['naam']}")
                    if quality_warning:
                        c1.caption(f"⚠ {quality_warning}")
                    if c2.button("Kies", key=f"pick_today_{j}"):
                        try:
                            api.update_event(event["id"], name=alt["naam"],
                                             description=alt["beschrijving"],
                                             type=alt.get("sport", e_type))
                            st.cache_data.clear()
                            del st.session_state[swap_cat_key]
                            st.session_state["show_swap_today"] = False
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))
            c1, c2 = st.columns(2)
            if c1.button("Terug", key="back_today"):
                del st.session_state[swap_cat_key]
                st.rerun()
            if c2.button("Annuleer", key="cancel_today"):
                del st.session_state[swap_cat_key]
                st.session_state["show_swap_today"] = False
                st.rerun()

    st.markdown("")  # spacing instead of divider

# ── WEEK PROGRESS ──────────────────────────────────────────────────────────

total_planned = sum(e["event"].get("load_target") or 0 for e in matched)
total_done = sum((e["activity"].get("icu_training_load") or 0) if e["activity"] else 0 for e in matched)
done_count = sum(1 for e in matched if e["done"])

st.markdown(f'<div class="week-progress">{done_count} / {len(matched)} sessies</div>',
            unsafe_allow_html=True)
if total_planned > 0:
    st.progress(min(1.0, total_done / total_planned))

# ── WORKOUT LIST ───────────────────────────────────────────────────────────

for i, item in enumerate(matched):
    event = item["event"]
    activity = item["activity"]
    done = item["done"]

    e_date = event.get("start_date_local", "")[:10]
    weekday_short = DAYS_NL.get(date.fromisoformat(e_date).weekday(), "?") if e_date else "?"
    e_name = event.get("name", "?")
    e_type = event.get("type", "?")
    is_today = e_date == today_str

    # Compact stats — alleen de kern
    stats_parts = []
    if activity:
        dur = round((activity.get("moving_time") or 0) / 60)
        dist = round((activity.get("distance") or 0) / 1000, 1)
        tss = activity.get("icu_training_load") or 0
        stats_parts = [f"{dur}min", f"{dist}km", f"TSS {tss:.0f}"]
    stats_html = " &middot; ".join(stats_parts)

    # Workout row — alles in een HTML blok voor visuele rust
    check_class = "done" if done else "pending"
    check_icon = "&#10003;" if done else ""
    done_class = " is-done" if done else ""

    st.markdown(
        f'<div class="workout-row{done_class}">'
        f'<div style="display:flex; align-items:flex-start;">'
        f'<span class="wr-check {check_class}">{check_icon}</span>'
        f'<div>'
        f'<div class="wr-day">{weekday_short}</div>'
        f'<div class="wr-name">{e_name}</div>'
        f'{"<div class=wr-stats>" + stats_html + "</div>" if stats_html else ""}'
        f'</div></div></div>',
        unsafe_allow_html=True
    )

    # Action buttons — compact, inline
    if done or not is_today:
        if done:
            btn_cols = st.columns([1, 1, 4])
            if btn_cols[0].button("Coach", key=f"fb_{i}"):
                st.session_state[f"show_fb_{i}"] = not st.session_state.get(f"show_fb_{i}", False)
            if btn_cols[1].button("Wissel", key=f"swap_{i}"):
                st.session_state[f"show_swap_{i}"] = not st.session_state.get(f"show_swap_{i}", False)
        elif not is_today:
            feel = get_feel_note(event)
            if feel:
                btn_cols = st.columns([1, 1, 4])
            else:
                btn_cols = st.columns([1, 5])
            if btn_cols[0].button("Wissel", key=f"swap_{i}"):
                st.session_state[f"show_swap_{i}"] = not st.session_state.get(f"show_swap_{i}", False)
            if feel and btn_cols[1].button("Hoe voelt dit?", key=f"feel_{i}"):
                st.session_state[f"show_feel_{i}"] = not st.session_state.get(f"show_feel_{i}", False)

    # Coach feedback — analytische bericht-stijl
    if st.session_state.get(f"show_fb_{i}"):
        with st.spinner(""):
            fb = generate_feedback(event, activity, matched=matched)
        if fb:
            # Container met label, content via st.markdown zodat **bold** rendert
            st.markdown(
                '<div class="coach-feedback">'
                '<div class="coach-avatar">Coach</div>'
                '</div>',
                unsafe_allow_html=True,
            )
            st.markdown(fb)

    # Feel note alleen op klik
    if not done and not is_today:
        feel = get_feel_note(event)
        if feel:
            if st.session_state.get(f"show_feel_{i}"):
                st.markdown(f'<div class="feel-note">{feel}</div>', unsafe_allow_html=True)

    # Smart Swap panel
    if st.session_state.get(f"show_swap_{i}"):
        swap_cat_key = f"swap_cat_{i}"

        # Stap 1: kies categorie
        if swap_cat_key not in st.session_state:
            st.caption("Wat wil je?")
            cat_cols = st.columns(4)
            for ci, (cat_id, cat_info) in enumerate(lib.SWAP_CATEGORIES.items()):
                if cat_cols[ci].button(cat_info["label"], key=f"cat_{i}_{cat_id}"):
                    st.session_state[swap_cat_key] = cat_id
                    st.rerun()
            if st.button("Annuleer", key=f"cancel_{i}"):
                st.session_state[f"show_swap_{i}"] = False
                st.rerun()

        # Stap 2: toon opties in gekozen categorie
        else:
            chosen_cat = st.session_state[swap_cat_key]
            cat_label = lib.SWAP_CATEGORIES[chosen_cat]["label"]
            st.caption(f"{cat_label}")

            alts = get_alternatives(event, category=chosen_cat)
            if alts:
                for j, alt in enumerate(alts):
                    # Check weekbalans als makkelijker
                    quality_warning = ""
                    if chosen_cat == "makkelijker":
                        qcheck = check_week_quality(matched, event.get("id"), alt)
                        if not qcheck["has_enough_quality"]:
                            quality_warning = qcheck["message"]

                    ca, cb = st.columns([5, 1])
                    ca.write(f"{alt['naam']}")
                    if quality_warning:
                        ca.caption(f"⚠ {quality_warning}")
                    if cb.button("Kies", key=f"pick_{i}_{j}"):
                        try:
                            api.update_event(event["id"], name=alt["naam"],
                                             description=alt["beschrijving"],
                                             type=alt.get("sport", e_type))
                            st.cache_data.clear()
                            del st.session_state[swap_cat_key]
                            st.session_state[f"show_swap_{i}"] = False
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))
            else:
                st.write("Geen alternatieven in deze categorie.")

            c1, c2 = st.columns(2)
            if c1.button("Terug", key=f"back_{i}"):
                del st.session_state[swap_cat_key]
                st.rerun()
            if c2.button("Annuleer", key=f"cancel_{i}"):
                del st.session_state[swap_cat_key]
                st.session_state[f"show_swap_{i}"] = False
                st.rerun()

# ── FOOTER QUOTE ───────────────────────────────────────────────────────────

quote = DELAHAIJE_QUOTES[date.today().timetuple().tm_yday % len(DELAHAIJE_QUOTES)]
st.markdown(
    f'<div style="text-align:center; color:#bbb; font-style:italic; '
    f'margin-top:3rem; padding:1.5rem 0; font-size:0.82rem; '
    f'border-top:1px solid #f0f0f0;">'
    f'"{quote}"<br><span style="font-size:0.7rem; font-style:normal; '
    f'color:#ccc;">— Louis Delahaije</span></div>',
    unsafe_allow_html=True
)
