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


def this_monday():
    today = date.today()
    return today - timedelta(days=today.weekday())


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


DELAHAIJE_QUOTES = [
    "Volume triumphs quality all the time!",
    "Een gelukkige atleet is een snelle atleet.",
    "Ik ben dertig procent trainer, zeventig procent coach.",
    "Als mijn hartslag niet omhooggaat van de atleet, kan ik die nooit begeleiden.",
    "Pas wanneer de basis staat, bouw je snelheid en kracht op.",
    "Gelukkige atleten presteren beter. De stem van de atleet is altijd doorslaggevend.",
    "Don't try to speed it up.",
    "Look for alternatives — zoek alternatieve trainingsvormen.",
    "De mitochondrien maken het niet uit of je ze traint door te fietsen of te lopen.",
    "Zwaardere trainingen worden vaak te vroeg gedaan. De basis moet eerst staan.",
    "Loop 4x10 minuten zo hard als je kunt, maar de laatste moet net zo snel zijn als de eerste.",
    "Te veel atleten staan te kwetsbaar in het leven. Welzijn staat altijd centraal.",
]


def _build_workout_context(event, activity):
    """Bouw een rijke context dict uit event + activity data."""
    hr = activity.get("average_heartrate") or activity.get("icu_average_hr") or 0
    hr_max = activity.get("max_heartrate") or activity.get("icu_hr_max") or 190
    hr_pct = round(hr / hr_max * 100) if hr and hr_max else 0
    distance = round((activity.get("distance") or 0) / 1000, 1)
    duration = round((activity.get("moving_time") or activity.get("elapsed_time") or 0) / 60)
    tss = activity.get("icu_training_load") or activity.get("training_load") or 0
    avg_power = activity.get("average_watts") or activity.get("icu_average_watts")
    max_hr_act = activity.get("max_heartrate") or activity.get("icu_hr_max") or 0
    avg_pace = None
    if distance > 0 and duration > 0 and activity.get("type") == "Run":
        avg_pace = round(duration / distance, 2)  # min/km
    cadence = activity.get("average_cadence") or activity.get("icu_average_cadence")
    calories = activity.get("calories") or activity.get("icu_calories")
    target_tss = event.get("load_target") or 0

    return {
        "hr": hr, "hr_max": hr_max, "hr_pct": hr_pct,
        "distance": distance, "duration": duration, "tss": tss,
        "avg_power": avg_power, "max_hr_act": max_hr_act,
        "avg_pace": avg_pace, "cadence": cadence, "calories": calories,
        "target_tss": target_tss,
    }


def _determine_feedback_angle(event, ctx, recent_activities):
    """Bepaal vanuit welke hoek de feedback moet komen. Varieert per situatie."""
    e_name = event.get("name", "").lower()
    e_type = event.get("type", "")

    # Hoeveel trainingen in de afgelopen 3 dagen?
    today = date.today()
    recent_3d = [a for a in recent_activities
                 if a.get("start_date_local", "")[:10] >= (today - timedelta(days=3)).isoformat()]
    consecutive_load = len(recent_3d)

    angles = []

    # 1. Zone compliance
    if e_type == "Run":
        if ctx["hr_pct"] > 82 and any(k in e_name for k in ["z2", "duurloop", "easy", "fartlek", "bosrun", "progressie", "pickup"]):
            angles.append("zone_te_hoog")
        elif ctx["hr_pct"] > 0 and ctx["hr_pct"] <= 75:
            angles.append("zone_perfect")
        elif ctx["hr_pct"] > 75:
            angles.append("zone_bovengrens")

    if e_type in ("Ride", "VirtualRide") and ctx["avg_power"]:
        power_pct = ctx["avg_power"] / 290 * 100
        if "threshold" in e_name and power_pct < 90:
            angles.append("vermogen_te_laag")
        elif "threshold" in e_name and power_pct > 100:
            angles.append("vermogen_boven_ftp")
        elif "sweetspot" in e_name and 85 <= power_pct <= 95:
            angles.append("sweetspot_perfect")

    # 2. Volume check
    if ctx["target_tss"] > 0:
        tss_ratio = ctx["tss"] / ctx["target_tss"]
        if tss_ratio > 1.25:
            angles.append("meer_dan_gepland")
        elif tss_ratio < 0.7:
            angles.append("minder_dan_gepland")
        else:
            angles.append("op_schema")

    # 3. Opeenvolgende belasting
    if consecutive_load >= 4:
        angles.append("veel_achtereen")
    elif consecutive_load <= 1:
        angles.append("fris")

    # 4. Kadans check (hardlopen)
    if e_type == "Run" and ctx["cadence"]:
        if ctx["cadence"] < 170:
            angles.append("kadans_laag")
        elif ctx["cadence"] >= 180:
            angles.append("kadans_top")

    # 5. Pace check (hardlopen)
    if ctx["avg_pace"] and ctx["avg_pace"] < 5.0 and "z2" in e_name:
        angles.append("te_snel_voor_z2")

    # 6. Workout type specifiek
    if "lange duurloop" in e_name:
        angles.append("long_run")
    elif "threshold" in e_name:
        angles.append("threshold")
    elif "sweetspot" in e_name:
        angles.append("sweetspot")
    elif "fartlek" in e_name:
        angles.append("fartlek")
    elif "bosrun" in e_name or "trail" in e_name:
        angles.append("trail")
    elif "group ride" in e_name or "zwift" in e_name:
        angles.append("zwift")

    return angles


def generate_feedback(event, activity):
    if not activity:
        return None

    ctx = _build_workout_context(event, activity)
    recent_acts = fetch_recent()
    angles = _determine_feedback_angle(event, ctx, recent_acts)

    # State voor fase-context
    try:
        with open(STATE_PATH) as f:
            state = json.load(f)
        ctl = state.get("load", {}).get("ctl_estimate", 49)
        phase = state.get("current_phase", "herstel_opbouw_I").replace("_", " ")
        weeks_to_race = max(0, (date.fromisoformat(state.get("race_date", "2026-10-18")) - date.today()).days // 7)
    except Exception:
        ctl = 49
        phase = "onbekend"
        weeks_to_race = 28

    # Quote selecteren — roteer op basis van dag van het jaar
    quote = DELAHAIJE_QUOTES[date.today().timetuple().tm_yday % len(DELAHAIJE_QUOTES)]

    # Recente activiteiten samenvatten (3 dagen context)
    recent_lines = []
    for ra in recent_acts[:5]:
        ra_date = ra.get("start_date_local", "")[:10]
        ra_name = ra.get("name", "?")
        ra_tss = ra.get("icu_training_load") or 0
        ra_type = ra.get("type", "")
        recent_lines.append(f"  {ra_date} | {ra_type} | {ra_name} | TSS {ra_tss:.0f}")
    recent_str = "\n".join(recent_lines) if recent_lines else "  Geen recente data."

    if not CLAUDE_AVAILABLE:
        return _rich_rule_feedback(event, ctx, angles, quote)

    # Bouw rijke prompt
    power_line = f"Vermogen: {ctx['avg_power']}W ({round(ctx['avg_power']/290*100)}% FTP)" if ctx["avg_power"] else ""
    pace_line = f"Pace: {ctx['avg_pace']:.2f} min/km" if ctx["avg_pace"] else ""
    cadence_line = f"Kadans: {ctx['cadence']} spm" if ctx["cadence"] else ""
    tss_compare = ""
    if ctx["target_tss"]:
        tss_compare = f"Gepland: {ctx['target_tss']} TSS, werkelijk: {ctx['tss']:.0f} TSS ({round(ctx['tss']/ctx['target_tss']*100)}%)"

    angle_hints = ", ".join(angles[:4]) if angles else "geen bijzonderheden"

    prompt = f"""Je bent Louis Delahaije, de holistische coach achter Abdi Nageeye en Nienke Brinkman.
Je coacht een ambitieuze recreant (CTL {ctl}, FTP 290W) die traint voor de Amsterdam Marathon ({weeks_to_race} weken).
Hij herstelt van een gluteus medius blessure (linkerheup/knie). Huidige fase: {phase}.

GEPLANDE WORKOUT: {event.get('name', '?')}
Beschrijving: {event.get('description', '')[:300]}

UITGEVOERD:
- Type: {activity.get('type', '?')}
- Duur: {ctx['duration']} min | Afstand: {ctx['distance']} km
- Hartslag: gem {ctx['hr']} bpm ({ctx['hr_pct']}% HRmax), max {ctx['max_hr_act']} bpm
- {power_line}
- {pace_line}
- {cadence_line}
- {tss_compare}

RECENTE TRAININGEN (context):
{recent_str}

SIGNALEN DIE IK ZIE: {angle_hints}

Geef persoonlijke, gevarieerde feedback. NIET altijd hetzelfde format. Wissel af tussen:
- Soms kort en krachtig (2 zinnen)
- Soms analytisch (wat ging goed, wat kan beter, waarom)
- Soms motiverend en filosofisch
- Soms praktisch (concreet advies voor morgen)
- Soms confronterend als het te hard was ("Je liep weer te snel. Ik zeg het niet graag twee keer.")

Dingen om op te letten:
- Z2 runs: was de hartslag echt in Z2? Kadans boven 175?
- Fietssessies: vermogen consistent? Niet te hard gestart?
- Lange duurloop: pace opgebouwd of te snel begonnen?
- Na harde sessies: is er genoeg herstel?
- Knie/heup: signalen in de data? HR drift kan wijzen op compensatie.
- Plezier: was dit een training om van te genieten?

Sluit af met een variatie op dit Delahaije-citaat (NIET letterlijk kopieren, maak het persoonlijk):
"{quote}"

Antwoord in Nederlands, platte tekst, 4-6 zinnen. Geen opsommingstekens."""

    try:
        client = anthropic.Anthropic()
        r = client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=350,
            messages=[{"role": "user", "content": prompt}])
        return r.content[0].text.strip()
    except Exception as e:
        return _rich_rule_feedback(event, ctx, angles, quote)


def _rich_rule_feedback(event, ctx, angles, quote):
    """Rijkere rule-based feedback als fallback."""
    lines = []
    e_name = event.get("name", "").lower()

    # Zone feedback
    if "zone_te_hoog" in angles:
        lines.append(f"Je hartslag was {ctx['hr_pct']}% HRmax — dat is boven Z2. "
                      f"Delahaije zou zeggen: 'Train trager dan je denkt.' "
                      f"Je aerobe systeem profiteert meer van rust dan van tempo.")
    elif "zone_perfect" in angles:
        lines.append(f"Hartslag {ctx['hr_pct']}% HRmax — netjes in Z2. "
                      f"Precies waar het moet zijn. Zo bouw je de basis.")
    elif "zone_bovengrens" in angles:
        lines.append(f"Hartslag {ctx['hr_pct']}% HRmax — net op de bovengrens van Z2. "
                      f"Prima, maar op warme dagen of na een drukke werkdag mag het rustiger.")

    # Vermogen feedback
    if "sweetspot_perfect" in angles:
        lines.append(f"Vermogen {ctx['avg_power']}W zit mooi in de sweetspot zone. "
                      f"Dit is de meest efficiente zone — hoge stimulus, beperkte vermoeidheid.")
    elif "vermogen_boven_ftp" in angles:
        lines.append(f"Vermogen {ctx['avg_power']}W was boven je FTP. Bewust? "
                      f"Als het makkelijk voelde, is je FTP waarschijnlijk gestegen.")
    elif "vermogen_te_laag" in angles:
        lines.append(f"Vermogen {ctx['avg_power']}W was aan de lage kant voor threshold. "
                      f"Niet erg — misschien een zware dag. Luister naar je lichaam.")

    # Volume feedback
    if "meer_dan_gepland" in angles:
        ratio = round(ctx["tss"] / ctx["target_tss"] * 100) if ctx["target_tss"] else 0
        lines.append(f"TSS {ctx['tss']:.0f} was {ratio}% van gepland — meer dan de bedoeling. "
                      f"Hou morgen licht.")
    elif "minder_dan_gepland" in angles:
        lines.append(f"TSS was lager dan gepland. Geen probleem — een training overslaan "
                      f"is beter dan een blessure.")

    # Consecutive load
    if "veel_achtereen" in angles:
        lines.append("Je hebt veel trainingen op rij gehad. Morgen rust of een hele makkelijke sessie.")

    # Kadans
    if "kadans_laag" in angles:
        lines.append(f"Kadans {ctx['cadence']} spm is aan de lage kant. "
                      f"Probeer 175+ te houden — hogere kadans = minder belasting per stap.")
    elif "kadans_top" in angles:
        lines.append(f"Kadans {ctx['cadence']} spm — top! Dat spaart je benen.")

    # Pace
    if "te_snel_voor_z2" in angles:
        lines.append(f"Pace {ctx['avg_pace']:.2f} min/km is snel voor Z2. "
                      f"Laat het tempo los, volg je hartslag.")

    # Type-specifiek
    if "long_run" in angles and not lines:
        lines.append("Lange duurloop voltooid! Dit is de belangrijkste training van de week. "
                      "Volume is king.")
    elif "trail" in angles and not lines:
        lines.append("Bosrun — goed voor je enkels, voeten en je hoofd. "
                      "Dit soort sessies houden het plezier erin.")
    elif "zwift" in angles and not lines:
        lines.append("Zwift sessie klaar. De fiets is je geheime wapen — "
                      "aerobe winst zonder impactbelasting.")

    if not lines:
        lines.append("Workout voltooid. Goed bezig!")

    lines.append(f'\n"{quote}" — Delahaije')
    return " ".join(lines)


# ── PAGE CONFIG ─────────────────────────────────────────────────────────────

st.set_page_config(page_title="Sport Coach", page_icon="🏃", layout="wide")
st.title("🏃 Sport Coach — Amsterdam Marathon 2026")

# ── SIDEBAR: WEEK SELECTOR ──────────────────────────────────────────────────

monday = this_monday()
with st.sidebar:
    st.header("Week")
    week_offset = st.slider("Week offset", -4, 8, 0, help="0 = deze week")
    selected_monday = monday + timedelta(weeks=week_offset)
    st.write(f"**{selected_monday}** t/m **{selected_monday + timedelta(days=6)}**")

    if st.button("Refresh data"):
        st.cache_data.clear()

    st.divider()
    try:
        with open(STATE_PATH) as f:
            state = json.load(f)
        ctl = state.get("load", {}).get("ctl_estimate", "?")
        phase = state.get("current_phase", "?").replace("_", " ").title()
        st.metric("CTL", ctl)
        st.metric("Fase", phase)
        race_date = state.get("race_date", "2026-10-18")
        weeks_left = max(0, (date.fromisoformat(race_date) - date.today()).days // 7)
        st.metric("Weken tot race", weeks_left)
    except Exception:
        pass

# ── MAIN: WEEK VIEW ─────────────────────────────────────────────────────────

events, activities = fetch_week(selected_monday.isoformat())
recent = fetch_recent()
matched = match_events_activities(events, activities)

if not matched:
    st.info("Geen workouts gevonden voor deze week.")
    st.stop()

# TSS summary
total_planned = sum(e["event"].get("load_target") or 0 for e in matched)
total_done = sum((e["activity"].get("icu_training_load") or 0) if e["activity"] else 0 for e in matched)
col1, col2, col3 = st.columns(3)
col1.metric("Gepland TSS", total_planned)
col2.metric("Voltooid TSS", f"{total_done:.0f}")
col3.metric("Uitvoering", f"{round(total_done / total_planned * 100)}%" if total_planned else "—")

st.divider()

# ── WORKOUT CARDS ───────────────────────────────────────────────────────────

for i, item in enumerate(matched):
    event = item["event"]
    activity = item["activity"]
    done = item["done"]

    e_date = event.get("start_date_local", "")[:10]
    weekday = DAYS_FULL.get(date.fromisoformat(e_date).weekday(), "?") if e_date else "?"
    e_name = event.get("name", "?")
    e_type = event.get("type", "?")
    sport_emoji = "🏃" if e_type == "Run" else "🚴"
    status_emoji = "✅" if done else "⬜"

    # Activity stats
    stats = ""
    if activity:
        hr = activity.get("average_heartrate") or activity.get("icu_average_hr") or 0
        tss = activity.get("icu_training_load") or 0
        dist = round((activity.get("distance") or 0) / 1000, 1)
        dur = round((activity.get("moving_time") or 0) / 60)
        power = activity.get("average_watts") or activity.get("icu_average_watts")
        stats = f"{dur}min | {dist}km | HR {hr} | TSS {tss:.0f}"
        if power:
            stats += f" | {power}W"

    with st.container():
        col_status, col_main, col_actions = st.columns([0.5, 6, 3])

        with col_status:
            st.write(f"### {status_emoji}")

        with col_main:
            st.write(f"**{weekday}** {sport_emoji} {e_name}")
            if stats:
                st.caption(stats)

        with col_actions:
            btn_col1, btn_col2 = st.columns(2)

            # Feedback button
            with btn_col1:
                if done and st.button("💬 Feedback", key=f"fb_{i}"):
                    st.session_state[f"show_fb_{i}"] = True

            # Swap button
            with btn_col2:
                if st.button("🔄 Swap", key=f"swap_{i}"):
                    st.session_state[f"show_swap_{i}"] = True

    # Feedback panel
    if st.session_state.get(f"show_fb_{i}"):
        with st.expander(f"Coach feedback — {e_name}", expanded=True):
            with st.spinner("Feedback genereren..."):
                fb = generate_feedback(event, activity)
            if fb:
                st.info(fb)
            else:
                st.warning("Geen activiteit data beschikbaar.")
            if st.button("Sluiten", key=f"close_fb_{i}"):
                st.session_state[f"show_fb_{i}"] = False
                st.rerun()

    # Swap panel
    if st.session_state.get(f"show_swap_{i}"):
        with st.expander(f"Swap — {e_name}", expanded=True):
            alts = get_alternatives(event)
            if not alts:
                st.warning("Geen alternatieven beschikbaar.")
            else:
                for j, alt in enumerate(alts):
                    col_alt, col_btn = st.columns([5, 1])
                    with col_alt:
                        st.write(f"**{alt['naam']}** — TSS ~{alt.get('tss_geschat', '?')}")
                    with col_btn:
                        if st.button("Kies", key=f"pick_{i}_{j}"):
                            try:
                                api.update_event(
                                    event["id"],
                                    name=alt["naam"],
                                    description=alt["beschrijving"],
                                    type=alt.get("sport", e_type))
                                st.success(f"Geswapped naar: {alt['naam']}")
                                st.cache_data.clear()
                                st.session_state[f"show_swap_{i}"] = False
                                st.rerun()
                            except Exception as e:
                                st.error(f"Swap mislukt: {e}")

            if st.button("Annuleren", key=f"cancel_swap_{i}"):
                st.session_state[f"show_swap_{i}"] = False
                st.rerun()

    st.divider()
