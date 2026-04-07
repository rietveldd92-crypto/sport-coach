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

sys.path.insert(0, str(Path(__file__).parent))
import intervals_client as api
from agents import workout_library as lib
from agents import workout_analysis
from agents.workout_feel import get_feel_note, get_post_workout_note

STATE_PATH = Path(__file__).parent / "state.json"

try:
    import anthropic
    CLAUDE_AVAILABLE = bool(os.getenv("ANTHROPIC_API_KEY"))
except ImportError:
    CLAUDE_AVAILABLE = False


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
    events = api.get_events(monday, sunday)
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


def get_alternatives(event):
    e_type = event.get("type", "")
    e_name = event.get("name", "").lower()
    try:
        with open(STATE_PATH) as f:
            state = json.load(f)
        prog = state.get("progression", {})
    except Exception:
        prog = {}
    t_step = prog.get("threshold_step", 3)
    ss_step = prog.get("sweetspot_step", 3)

    if e_type in ("Ride", "VirtualRide"):
        if any(k in e_name for k in ["threshold", "sweetspot", "over-under"]):
            alts = [
                lib.endurance_ride(90), lib.zwift_group_ride(75),
                lib.cadence_pyramids(290), lib.single_leg_drills(290),
                lib.sweetspot(290, max(1, ss_step - 2)),
                lib.threshold(290, max(1, t_step - 2)),
            ]
        else:
            alts = [
                lib.zwift_group_ride(75), lib.endurance_ride(75),
                lib.cadence_pyramids(290), lib.single_leg_drills(290),
                lib.sweetspot(290, max(1, ss_step)), lib.tempo_blocks(290),
            ]
    elif e_type == "Run":
        dur = 45
        for p in e_name.split():
            try:
                dur = int(p)
            except ValueError:
                pass
        alts = [
            lib.z2_standard(dur), lib.z2_progression(dur),
            lib.z2_fartlek(dur), lib.z2_trail(dur),
            lib.z2_with_pickups(dur), lib.recovery_run(max(25, dur - 10)),
        ]
    else:
        return []
    return [a for a in alts if a["naam"].lower() != e_name][:6]


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

def generate_feedback(event, activity):
    if not activity:
        return None

    analysis = workout_analysis.analyze(event, activity)
    metrics = analysis["metrics"]
    insights = analysis["insights"]
    wtype = analysis["workout_type"]
    prompt_focus = analysis["prompt_focus"]

    # Post-workout feel note
    feel_note = get_post_workout_note(event, metrics)
    if feel_note and not insights:
        insights = [feel_note]
    elif feel_note:
        insights.insert(0, feel_note)

    state = load_state()
    ctl = state.get("load", {}).get("ctl_estimate", 49)
    phase = state.get("current_phase", "herstel_opbouw_I").replace("_", " ")
    weeks_to_race = max(0, (date.fromisoformat(state.get("race_date", "2026-10-18")) - date.today()).days // 7)

    quote = DELAHAIJE_QUOTES[date.today().timetuple().tm_yday % len(DELAHAIJE_QUOTES)]

    if not CLAUDE_AVAILABLE:
        return _rule_feedback(analysis, quote)

    insights_str = "\n".join(f"- {i}" for i in insights) if insights else "- Geen bijzonderheden."

    extra_data = []
    if metrics.get("interval_powers"):
        extra_data.append(f"Power per interval: {metrics['interval_powers']}W")
    if metrics.get("hr_drift_pct") is not None:
        extra_data.append(f"HR drift: {metrics['hr_drift_pct']}%")
    if metrics.get("splits"):
        split_str = ", ".join(f"{s['pace']:.2f}/km" for s in metrics["splits"][:10])
        extra_data.append(f"Splits: {split_str}")
    if metrics.get("cardiac_decoupling_pct") is not None:
        extra_data.append(f"Cardiac decoupling: {metrics['cardiac_decoupling_pct']}%")
    if metrics.get("interval_paces"):
        extra_data.append(f"Interval paces: {[f'{p:.2f}' for p in metrics['interval_paces']]}/km")
    extra_str = "\n".join(f"- {e}" for e in extra_data) if extra_data else ""

    power_line = f"Vermogen: {metrics['avg_power']}W ({round(metrics['avg_power']/290*100)}% FTP)" if metrics.get("avg_power") else ""
    pace_line = f"Pace: {metrics.get('avg_pace', '?')} min/km" if metrics.get("avg_pace") else ""

    prompt = f"""Je bent Louis Delahaije. Kort, warm, persoonlijk. Geen opsommingstekens.

Atleet: CTL {ctl}, FTP 290W, Amsterdam Marathon in {weeks_to_race} weken. Fase: {phase}.

WORKOUT: {wtype} — {event.get('name', '?')}
Data: {metrics['duration']}min | {metrics['distance']}km | HR {metrics['hr_avg']}bpm ({metrics['hr_pct']}%HRmax) | TSS {metrics['tss']:.0f}
{power_line} {pace_line}

ANALYSE:
{extra_str}

BEVINDINGEN:
{insights_str}

INSTRUCTIE: {prompt_focus}

Lengterichtlijn:
- Z2/recovery: max 2 zinnen
- Threshold/sweetspot: 3-4 zinnen
- Lange duurloop: 3-5 zinnen

Sluit af met een variatie op: "{quote}"
Nederlands, platte tekst."""

    try:
        client = anthropic.Anthropic()
        r = client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=300,
            messages=[{"role": "user", "content": prompt}])
        return r.content[0].text.strip()
    except Exception:
        return _rule_feedback(analysis, quote)


def _rule_feedback(analysis, quote):
    insights = analysis["insights"]
    wtype = analysis["workout_type"]
    if not insights:
        return f"Goed bezig.\n\n\"{quote}\""
    if wtype in ("run_z2", "run_recovery", "run_trail", "bike_endurance"):
        return f"{insights[0]}\n\n\"{quote}\""
    text = " ".join(insights[:3])
    return f"{text}\n\n\"{quote}\""


# ── CUSTOM CSS ─────────────────────────────────────────────────────────────

CUSTOM_CSS = """
<style>
    /* Clean, minimal styling */
    .block-container { max-width: 720px; padding-top: 2rem; }
    h1 { font-weight: 300 !important; font-size: 1.8rem !important; letter-spacing: -0.02em; }
    .stMetric label { font-size: 0.75rem !important; color: #888 !important; }
    .stMetric [data-testid="stMetricValue"] { font-size: 1.1rem !important; }

    /* Coach feedback styling */
    .coach-feedback {
        background: #f8f7f5;
        border-left: 3px solid #2d5016;
        padding: 1.2rem 1.5rem;
        margin: 0.5rem 0 1rem 0;
        border-radius: 0 8px 8px 0;
        font-size: 0.95rem;
        line-height: 1.6;
        color: #1a1a1a;
    }
    .coach-quote {
        color: #666;
        font-style: italic;
        margin-top: 0.8rem;
        font-size: 0.85rem;
    }

    /* Feel note styling */
    .feel-note {
        background: #f0f4e8;
        border-radius: 8px;
        padding: 0.8rem 1.2rem;
        margin: 0.3rem 0 0.8rem 0;
        font-size: 0.88rem;
        color: #3d5a1e;
        line-height: 1.5;
    }

    /* Workout card */
    .workout-done { opacity: 0.85; }
    .workout-today { border-left: 3px solid #2d5016; padding-left: 0.8rem; }

    /* Status dot */
    .dot-done { color: #2d5016; }
    .dot-pending { color: #ccc; }

    /* Sidebar human text */
    .sidebar-narrative {
        font-size: 0.9rem;
        line-height: 1.6;
        color: #444;
        padding: 0.5rem 0;
    }
</style>
"""


# ── PAGE CONFIG ─────────────────────────────────────────────────────────────

st.set_page_config(page_title="Coach", page_icon="", layout="centered")
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

state = load_state()
monday = this_monday()

# ── SIDEBAR ────────────────────────────────────────────────────────────────

with st.sidebar:
    week_offset = st.slider("Week", -4, 8, 0, label_visibility="collapsed")
    selected_monday = monday + timedelta(weeks=week_offset)
    if week_offset == 0:
        st.caption("Deze week")
    else:
        st.caption(f"{selected_monday} t/m {selected_monday + timedelta(days=6)}")

    if st.button("Ververs"):
        st.cache_data.clear()

    st.divider()

    # Menselijke taal in plaats van metrics
    ctl = state.get("load", {}).get("ctl_estimate", 0)
    phase = state.get("current_phase", "herstel_opbouw_I")
    race_date = state.get("race_date", "2026-10-18")
    weeks_left = max(0, (date.fromisoformat(race_date) - date.today()).days // 7)

    st.markdown(f'<div class="sidebar-narrative">{phase_to_human(phase, weeks_left)}</div>',
                unsafe_allow_html=True)
    st.markdown(f'<div class="sidebar-narrative">{ctl_to_human(ctl)}</div>',
                unsafe_allow_html=True)

    # Compacte metrics voor de nerds
    with st.expander("Details"):
        c1, c2, c3 = st.columns(3)
        c1.metric("CTL", f"{ctl:.0f}")
        c2.metric("TSB", f"{state.get('load', {}).get('tsb_estimate', 0):+.0f}")
        c3.metric("Wk", weeks_left)


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

    st.markdown(f"### Vandaag: {e_name}")
    st.caption(sport)

    feel = get_feel_note(event)
    if feel:
        st.markdown(f'<div class="feel-note">{feel}</div>', unsafe_allow_html=True)

    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("Wissel", key="swap_today"):
            st.session_state["show_swap_today"] = True

    if st.session_state.get("show_swap_today"):
        alts = get_alternatives(event)
        if alts:
            for j, alt in enumerate(alts):
                c1, c2 = st.columns([5, 1])
                c1.write(f"{alt['naam']}")
                if c2.button("Kies", key=f"pick_today_{j}"):
                    try:
                        api.update_event(event["id"], name=alt["naam"],
                                         description=alt["beschrijving"],
                                         type=alt.get("sport", e_type))
                        st.cache_data.clear()
                        st.session_state["show_swap_today"] = False
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
        if st.button("Annuleren", key="cancel_swap_today"):
            st.session_state["show_swap_today"] = False
            st.rerun()

    st.divider()

# ── WEEK PROGRESS ──────────────────────────────────────────────────────────

total_planned = sum(e["event"].get("load_target") or 0 for e in matched)
total_done = sum((e["activity"].get("icu_training_load") or 0) if e["activity"] else 0 for e in matched)
done_count = sum(1 for e in matched if e["done"])

st.caption(f"{done_count} van {len(matched)} sessies voltooid")
if total_planned > 0:
    st.progress(min(1.0, total_done / total_planned))

# ── WORKOUT LIST ───────────────────────────────────────────────────────────

for i, item in enumerate(matched):
    event = item["event"]
    activity = item["activity"]
    done = item["done"]

    e_date = event.get("start_date_local", "")[:10]
    weekday = DAYS_FULL.get(date.fromisoformat(e_date).weekday(), "?") if e_date else "?"
    e_name = event.get("name", "?")
    e_type = event.get("type", "?")
    is_today = e_date == today_str

    # Status indicator
    dot = "**·**" if not done else "**:**"
    dot_class = "dot-done" if done else "dot-pending"

    # Stats line
    stats = ""
    if activity:
        hr = activity.get("average_heartrate") or activity.get("icu_average_hr") or 0
        tss = activity.get("icu_training_load") or 0
        dist = round((activity.get("distance") or 0) / 1000, 1)
        dur = round((activity.get("moving_time") or 0) / 60)
        power = activity.get("average_watts") or activity.get("icu_average_watts")
        stats = f"{dur}min  {dist}km  HR {hr}  TSS {tss:.0f}"
        if power:
            stats += f"  {power}W"

    # Workout row
    css_class = "workout-today" if is_today else ("workout-done" if done else "")
    col_main, col_actions = st.columns([7, 2])

    with col_main:
        status_icon = "&#10003;" if done else "&#9675;"
        color = "#2d5016" if done else "#ccc"
        st.markdown(
            f'<span style="color:{color}; margin-right:8px;">{status_icon}</span>'
            f'<strong>{weekday[:2]}</strong>&ensp;{e_name}',
            unsafe_allow_html=True
        )
        if stats:
            st.caption(stats)

    with col_actions:
        c1, c2 = st.columns(2)
        if done:
            if c1.button("Coach", key=f"fb_{i}"):
                st.session_state[f"show_fb_{i}"] = not st.session_state.get(f"show_fb_{i}", False)
        if c2.button("Wissel", key=f"swap_{i}"):
            st.session_state[f"show_swap_{i}"] = not st.session_state.get(f"show_swap_{i}", False)

    # Coach feedback
    if st.session_state.get(f"show_fb_{i}"):
        with st.spinner(""):
            fb = generate_feedback(event, activity)
        if fb:
            # Split quote if present
            parts = fb.rsplit('"', 2)
            if len(parts) >= 3 and len(parts[-2]) > 10:
                main_text = parts[0].strip().rstrip('"').rstrip('\n')
                quote_text = parts[-2].strip()
                st.markdown(
                    f'<div class="coach-feedback">{main_text}'
                    f'<div class="coach-quote">"{quote_text}"</div></div>',
                    unsafe_allow_html=True
                )
            else:
                st.markdown(f'<div class="coach-feedback">{fb}</div>', unsafe_allow_html=True)

    # Feel note for upcoming workouts (not done, not today's card which is shown above)
    if not done and not is_today:
        feel = get_feel_note(event)
        if feel:
            with st.expander("Hoe moet dit voelen?"):
                st.markdown(f'<div class="feel-note">{feel}</div>', unsafe_allow_html=True)

    # Swap panel
    if st.session_state.get(f"show_swap_{i}"):
        alts = get_alternatives(event)
        if alts:
            for j, alt in enumerate(alts):
                ca, cb = st.columns([5, 1])
                ca.write(f"{alt['naam']}")
                if cb.button("Kies", key=f"pick_{i}_{j}"):
                    try:
                        api.update_event(event["id"], name=alt["naam"],
                                         description=alt["beschrijving"],
                                         type=alt.get("sport", e_type))
                        st.cache_data.clear()
                        st.session_state[f"show_swap_{i}"] = False
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
        if st.button("Annuleer", key=f"cancel_{i}"):
            st.session_state[f"show_swap_{i}"] = False
            st.rerun()

    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)

# ── FOOTER QUOTE ───────────────────────────────────────────────────────────

quote = DELAHAIJE_QUOTES[date.today().timetuple().tm_yday % len(DELAHAIJE_QUOTES)]
st.markdown(f'<div style="text-align:center; color:#999; font-style:italic; '
            f'margin-top:2rem; font-size:0.85rem;">"{quote}"</div>',
            unsafe_allow_html=True)
