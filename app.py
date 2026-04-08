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
from agents import workout_library as lib
from agents import workout_analysis
from agents.workout_feel import get_feel_note, get_post_workout_note

STATE_PATH = Path(__file__).parent / "state.json"

# ── LLM SETUP ──────────────────────────────────────────────────────────────
# We gebruiken Google Gemini (gratis tier).
# Pro voor key/zware sessies (intervals, threshold, long run, sweetspot, over-unders, tempo).
# Flash voor de rest (Z2, recovery, endurance, drills, kracht).
# Streamlit Cloud: zet GOOGLE_API_KEY in app secrets.

GEMINI_AVAILABLE = False
_gemini_client = None
try:
    from google import genai as google_genai
    from google.genai import types as genai_types
    _gemini_key = os.getenv("GOOGLE_API_KEY")
    # Streamlit Cloud secrets fallback
    if not _gemini_key:
        try:
            _gemini_key = st.secrets.get("GOOGLE_API_KEY")
        except Exception:
            _gemini_key = None
    if _gemini_key:
        _gemini_client = google_genai.Client(api_key=_gemini_key)
        GEMINI_AVAILABLE = True
except ImportError:
    pass

GEMINI_PRO_MODEL = "gemini-2.5-pro"
GEMINI_FLASH_MODEL = "gemini-2.5-flash"

# Workout types die "Pro" verdienen — daar is diepere analyse meeste waard
HARD_WORKOUT_TYPES = {
    "run_long", "run_tempo", "run_intervals", "run_progression", "run_fartlek",
    "bike_threshold", "bike_sweetspot", "bike_over_unders", "bike_tempo",
}

# Coach-persona / system prompt — door de gebruiker zelf opgesteld
COACH_SYSTEM_PROMPT = """Jij bent mijn persoonlijke coach. Wees direct, eerlijk en analytisch.

Doel: maximaliseer mijn prestatie en ontwikkeling richting de Amsterdam Marathon (sub 3:45) op 18 oktober 2026.

Houd rekening met:
- Ik functioneer het best met hoge standaarden, autonomie en inhoudelijke feedback
- Ik heb sterk analytisch vermogen en zelfreflectie
- Ik haak af op vaagheid, lage ambitie of overdreven positiviteit
- Blessuregevoeligheid: linkerhamstring/heup en onderrug → bewaak belasting kritisch
- Focus: progressie, fatigue resistance, slimme opbouw en herstel

Jouw gedrag:
- Geef concrete, scherpe feedback (wat werkt / wat niet)
- Benoem risico's en fouten direct
- Geen motivatiepraat, geen clichés
- Altijd praktisch en toepasbaar
- Prioriteer impact boven volledigheid
- Wees kort, scherp en zonder ruis"""


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


def _avg(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _trend_arrow(recent, baseline):
    """Pijl voor trend — recent vs baseline."""
    if recent is None or baseline is None or baseline == 0:
        return ""
    diff_pct = (recent - baseline) / baseline * 100
    if diff_pct > 5:
        return "stijgend"
    if diff_pct < -5:
        return "dalend"
    return "stabiel"


def build_wellness_context(activity_date: str) -> str:
    """Bouw een wellness-snippet voor de activity-datum + 7-day trend.

    Returns een platte tekst-blok of '' als er geen data is.
    """
    wellness = fetch_wellness_window(days=14)
    if not wellness:
        return ""

    today_record = next((w for w in wellness if w.get("id") == activity_date), None)

    # Trend: laatste 7 dagen vs 7 dagen daarvoor
    sorted_w = sorted(wellness, key=lambda w: w.get("id", ""))
    last7 = sorted_w[-7:]
    prev7 = sorted_w[-14:-7]

    lines = []

    if today_record:
        bits = []
        if (hrv := today_record.get("hrv")) is not None:
            bits.append(f"HRV {hrv:.0f}ms")
        if (rhr := today_record.get("restingHR")) is not None:
            bits.append(f"rust-HR {rhr}bpm")
        if (sleep := today_record.get("sleepSecs")) is not None:
            bits.append(f"slaap {sleep/3600:.1f}u")
        if (ss := today_record.get("sleepScore")) is not None:
            bits.append(f"slaapscore {ss:.0f}")
        if (sor := today_record.get("soreness")) is not None:
            bits.append(f"spierpijn {sor}/4")
        if (fat := today_record.get("fatigue")) is not None:
            bits.append(f"vermoeidheid {fat}/4")
        if (mood := today_record.get("mood")) is not None:
            bits.append(f"stemming {mood}/4")
        if (mot := today_record.get("motivation")) is not None:
            bits.append(f"motivatie {mot}/4")
        if (rea := today_record.get("readiness")) is not None:
            bits.append(f"readiness {rea}")
        if (inj := today_record.get("injury")) is not None:
            bits.append(f"blessure {inj}/4")
        if bits:
            lines.append(f"Op {activity_date}: " + ", ".join(bits) + ".")

    # 7d trend
    hrv_recent = _avg([w.get("hrv") for w in last7])
    hrv_base = _avg([w.get("hrv") for w in prev7])
    rhr_recent = _avg([w.get("restingHR") for w in last7])
    rhr_base = _avg([w.get("restingHR") for w in prev7])
    sleep_recent = _avg([w.get("sleepSecs") for w in last7])

    trend_bits = []
    if hrv_recent is not None and hrv_base is not None:
        arrow = _trend_arrow(hrv_recent, hrv_base)
        trend_bits.append(f"HRV 7d-gem {hrv_recent:.0f}ms ({arrow} t.o.v. week ervoor)")
    if rhr_recent is not None and rhr_base is not None:
        arrow = _trend_arrow(rhr_recent, rhr_base)
        # voor RHR: lager is beter, dus draai de interpretatie om
        if arrow == "stijgend":
            arrow = "oplopend (mogelijk vermoeidheid)"
        elif arrow == "dalend":
            arrow = "dalend (gunstig)"
        trend_bits.append(f"rust-HR 7d-gem {rhr_recent:.0f}bpm ({arrow})")
    if sleep_recent is not None:
        trend_bits.append(f"slaap 7d-gem {sleep_recent/3600:.1f}u/nacht")

    if trend_bits:
        lines.append("Trend: " + "; ".join(trend_bits) + ".")

    return "\n".join(lines)


def build_neighbor_context(matched: list, event_date: str) -> str:
    """Wat is er gisteren gedaan en wat staat er morgen gepland?"""
    try:
        d = date.fromisoformat(event_date)
    except Exception:
        return ""

    yesterday = (d - timedelta(days=1)).isoformat()
    tomorrow = (d + timedelta(days=1)).isoformat()

    lines = []
    for item in matched:
        e = item["event"]
        e_date = e.get("start_date_local", "")[:10]
        e_name = e.get("name", "?")

        if e_date == yesterday:
            if item["done"] and item["activity"]:
                act = item["activity"]
                tss = act.get("icu_training_load") or 0
                hr = act.get("average_heartrate") or 0
                hr_pct = round(hr / 190 * 100) if hr else 0
                lines.append(
                    f"Gisteren: {e_name} — voltooid, TSS {tss:.0f}, HR {hr_pct}%HRmax."
                )
            else:
                lines.append(f"Gisteren: {e_name} — niet voltooid.")
        elif e_date == tomorrow:
            target = e.get("load_target") or 0
            tag = f" (target TSS {target})" if target else ""
            lines.append(f"Morgen gepland: {e_name}{tag}.")

    return "\n".join(lines)


def build_similar_workouts_context(wtype: str, activity_id: int, recent_28d: list) -> str:
    """Vergelijk met max 3 vergelijkbare workouts uit afgelopen 28 dagen."""
    from agents.workout_analysis import classify_workout

    similar = []
    for act in recent_28d:
        if str(act.get("id")) == str(activity_id):
            continue
        # Bouw een fake-event om classify_workout te kunnen gebruiken
        fake_event = {"name": act.get("name", ""), "type": act.get("type", "")}
        if classify_workout(fake_event) != wtype:
            continue
        similar.append(act)

    if not similar:
        return ""

    similar.sort(key=lambda a: a.get("start_date_local", ""), reverse=True)
    similar = similar[:3]

    lines = []
    for s in similar:
        s_date = s.get("start_date_local", "")[:10]
        dur = round((s.get("moving_time") or 0) / 60)
        dist = round((s.get("distance") or 0) / 1000, 1)
        hr = s.get("average_heartrate") or s.get("icu_average_hr") or 0
        hr_pct = round(hr / 190 * 100) if hr else 0
        tss = s.get("icu_training_load") or 0
        pace_str = ""
        if dist > 0 and dur > 0 and (s.get("type") == "Run"):
            pace = dur / dist
            pace_str = f", pace {pace:.2f}/km"
        power_str = ""
        if s.get("average_watts"):
            power_str = f", {s.get('average_watts'):.0f}W"
        lines.append(
            f"- {s_date}: {dur}min, {dist}km, HR {hr_pct}%{pace_str}{power_str}, TSS {tss:.0f}"
        )

    return "Vergelijkbare workouts (laatste 28d):\n" + "\n".join(lines)


def build_state_context(state: dict) -> str:
    """Korte snapshot van fase, blessure, weken-tot-race uit state.json."""
    bits = []
    phase = state.get("current_phase", "?").replace("_", " ")
    bits.append(f"Fase: {phase}")

    race_date_str = state.get("race_date", "")
    if race_date_str:
        try:
            wks = max(0, (date.fromisoformat(race_date_str) - date.today()).days // 7)
            bits.append(f"{wks} weken tot {state.get('race_name', 'race')}")
        except Exception:
            pass

    inj = state.get("injury", {})
    if inj.get("active_signals"):
        bits.append(f"Actieve blessure-signalen: {', '.join(inj['active_signals'])}")
    elif inj.get("days_symptom_free"):
        bits.append(f"{inj['days_symptom_free']}d symptoomvrij")
    if inj.get("fysio_constraint"):
        bits.append(f"Fysio: {inj['fysio_constraint']}")

    load = state.get("load", {})
    if "ctl_estimate" in load and "tsb_estimate" in load:
        bits.append(f"CTL {load['ctl_estimate']:.0f}, TSB {load['tsb_estimate']:+.0f}")

    return " | ".join(bits)


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

def _gemini_call(model_name: str, prompt: str) -> str:
    """Single Gemini-call met juiste config per model.

    - Flash: thinking uit (snel + voorspelbaar token-budget)
    - Pro: thinking aan met beperkt budget (kwaliteit telt hier)
    """
    if "flash" in model_name:
        cfg = genai_types.GenerateContentConfig(
            max_output_tokens=2000,
            temperature=0.7,
            thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
        )
    else:
        cfg = genai_types.GenerateContentConfig(
            max_output_tokens=4000,
            temperature=0.7,
            thinking_config=genai_types.ThinkingConfig(thinking_budget=1024),
        )

    response = _gemini_client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=cfg,
    )
    text = (response.text or "").strip()
    if not text:
        # Diagnose lege response
        try:
            fr = response.candidates[0].finish_reason
            raise RuntimeError(f"lege response, finish_reason={fr}")
        except (AttributeError, IndexError):
            raise RuntimeError("lege response zonder candidate")
    return text


@st.cache_data(ttl=600, show_spinner=False)
def _cached_feedback(activity_id, event_id, model_name: str, _prompt: str) -> str:
    """Cache de Gemini-call op activity+event+model id.

    `_prompt` heeft underscore-prefix → Streamlit hasht 'm niet (scheelt werk
    op een lange string, en de andere 3 args zijn al genoeg uniek).
    """
    return _gemini_call(model_name, _prompt)


def generate_feedback(event, activity, matched=None):
    if not activity:
        return None

    analysis = workout_analysis.analyze(event, activity)
    metrics = analysis["metrics"]
    insights = analysis["insights"]
    wtype = analysis["workout_type"]
    prompt_focus = analysis["prompt_focus"]

    # Post-workout feel note (vergelijkt verwacht gevoel met data)
    feel_note = get_post_workout_note(event, metrics)
    if feel_note and not insights:
        insights = [feel_note]
    elif feel_note:
        insights.insert(0, feel_note)

    state = load_state()

    if not GEMINI_AVAILABLE:
        return _rule_feedback(analysis)

    # ── CONTEXT BLOKKEN ────────────────────────────────────────────────────
    state_ctx = build_state_context(state)

    activity_date = (activity.get("start_date_local") or "")[:10]
    wellness_ctx = build_wellness_context(activity_date) if activity_date else ""

    neighbor_ctx = ""
    if matched:
        event_date = (event.get("start_date_local") or "")[:10]
        if event_date:
            neighbor_ctx = build_neighbor_context(matched, event_date)

    recent_28d = fetch_recent_28d()
    similar_ctx = build_similar_workouts_context(wtype, activity.get("id"), recent_28d)

    # ── METRIEKEN BLOK ─────────────────────────────────────────────────────
    insights_str = "\n".join(f"- {i}" for i in insights) if insights else "- Geen bijzonderheden uit de auto-analyse."

    deep_data = []
    if metrics.get("interval_powers"):
        deep_data.append(f"Power per work-interval: {metrics['interval_powers']}W (gem {metrics.get('interval_avg_power', '?')}W = {metrics.get('interval_pct_ftp', '?')}% FTP, spread {metrics.get('interval_power_spread_pct', '?')}%)")
    if metrics.get("hr_drift_pct") is not None:
        deep_data.append(f"HR drift over intervals: {metrics['hr_drift_pct']}%")
    if metrics.get("splits"):
        split_str = ", ".join(f"{s['pace']:.2f}" for s in metrics["splits"][:12])
        deep_data.append(f"Km-splits (min/km): {split_str}")
    if metrics.get("cardiac_decoupling_pct") is not None:
        deep_data.append(f"Cardiac decoupling: {metrics['cardiac_decoupling_pct']}% (lager = beter aerobe basis)")
    if metrics.get("avg_pace_first_third") and metrics.get("avg_pace_last_third"):
        deep_data.append(f"Pacing: eerste derde {metrics['avg_pace_first_third']:.2f}/km → laatste derde {metrics['avg_pace_last_third']:.2f}/km")
    if metrics.get("interval_paces"):
        deep_data.append(f"Interval paces (min/km): {[f'{p:.2f}' for p in metrics['interval_paces']]}")
    if metrics.get("z1z2_pct") is not None:
        deep_data.append(f"Tijd in zones: Z1+Z2 {metrics['z1z2_pct']}%, boven Z2 {metrics['z3plus_pct']}%")
    if metrics.get("vi"):
        deep_data.append(f"Variability Index: {metrics['vi']}")
    if metrics.get("cadence"):
        deep_data.append(f"Gem. kadans: {metrics['cadence']}")
    deep_str = "\n".join(f"- {d}" for d in deep_data) if deep_data else "- Geen interval/split-detail beschikbaar."

    power_line = (
        f"Vermogen: {metrics['avg_power']}W (gem) / {metrics['np_power']}W (NP) = {round(metrics['avg_power']/290*100)}% FTP"
        if metrics.get("avg_power") and metrics.get("np_power")
        else (f"Vermogen: {metrics['avg_power']}W = {round(metrics['avg_power']/290*100)}% FTP" if metrics.get("avg_power") else "")
    )
    pace_line = f"Gem. pace: {metrics.get('avg_pace', '?')} min/km" if metrics.get("avg_pace") else ""

    target_tss = metrics.get("target_tss") or event.get("load_target") or 0
    target_line = f"Geplande TSS-target: {target_tss}" if target_tss else ""
    desc = (event.get("description") or "").strip()[:300]

    # ── PROMPT ────────────────────────────────────────────────────────────
    prompt = f"""{COACH_SYSTEM_PROMPT}

REFERENTIEWAARDEN ATLEET (gebruik DEZE, verzin geen andere)
- FTP: 290W
- HRmax: 190bpm
- Z2 hartslag-bandbreedte: 129–152bpm (68–80% HRmax)

LIVE STATE
{state_ctx}

DEZE WORKOUT
Type: {wtype}
Naam: {event.get('name', '?')}
Plan-beschrijving: {desc or '(geen)'}
{target_line}

UITGEVOERD
Duur {metrics['duration']}min | Afstand {metrics['distance']}km | Gem HR {metrics['hr_avg']}bpm ({metrics['hr_pct']}% HRmax) | TSS {metrics['tss']:.0f}
{power_line}
{pace_line}

DIEPE METRIEKEN
{deep_str}

AUTO-ANALYSE BEVINDINGEN
{insights_str}

WELLNESS / HERSTEL
{wellness_ctx or '(geen wellness data beschikbaar)'}

CONTEXT WEEK
{neighbor_ctx or '(geen buur-workouts)'}

{similar_ctx or '(geen vergelijkbare workouts in laatste 28 dagen)'}

INTERNE ANALYSE-FOCUS (niet noemen in output): {prompt_focus}

OUTPUT FORMAT
Geef je feedback in exact deze 4 secties. Gebruik **bold** voor de labels, geen H-headers. Houd het kort en scherp. Maximaal 200 woorden totaal. Geen quote, geen slotzin, geen motivatiepraat.

**Wat gaat goed**
1-3 zinnen. Concreet, met cijfers uit de data hierboven.

**Wat gaat fout / risico's**
1-3 zinnen. Eerlijk, geen verzachting. Bewaak linkerhamstring/heup/onderrug expliciet als er signalen zijn (HR drift, te veel intensiteit, fatigue trend, slechte slaap). Als er niets fout is, schrijf dat ook expliciet ("geen risico's deze sessie").

**Concreet advies**
Maximaal 3 acties, genummerd. Specifiek, meetbaar, toepasbaar. "Morgen Z2, HR onder 152bpm" — niet "blijf rustig".

**Aanpassing in strategie**
Alleen invullen als je vindt dat het weekplan of de fase-aanpak moet schuiven. Anders schrijf: "geen aanpassing nodig"."""

    # Kies model: Pro voor key sessies, Flash voor de rest
    model_name = GEMINI_PRO_MODEL if wtype in HARD_WORKOUT_TYPES else GEMINI_FLASH_MODEL

    try:
        return _cached_feedback(activity.get("id"), event.get("id"), model_name, prompt)
    except Exception as e:
        # Pro quota op? Probeer Flash als fallback
        if model_name == GEMINI_PRO_MODEL:
            try:
                return _cached_feedback(activity.get("id"), event.get("id"), GEMINI_FLASH_MODEL, prompt)
            except Exception as e2:
                return f"(Gemini fout: {e2})\n\n" + _rule_feedback(analysis)
        return f"(Gemini fout: {e})\n\n" + _rule_feedback(analysis)


def _rule_feedback(analysis):
    """Fallback als Gemini niet beschikbaar is. Geen quote, geen motivatiepraat —
    alleen de auto-analyse insights als platte tekst."""
    insights = analysis.get("insights", [])
    if not insights:
        return "**Wat gaat goed**\nWorkout voltooid, geen bijzonderheden uit auto-analyse.\n\n**Wat gaat fout / risico's**\nGeen risico's gedetecteerd.\n\n**Concreet advies**\n1. Volg het bestaande weekplan.\n\n**Aanpassing in strategie**\nGeen aanpassing nodig."
    text = " ".join(insights[:3])
    return f"**Wat gaat goed**\n{text}\n\n**Wat gaat fout / risico's**\nGeen specifieke risico's uit deze auto-analyse — Gemini AI niet beschikbaar voor diepere check.\n\n**Concreet advies**\n1. Volg het bestaande plan tot AI weer werkt.\n\n**Aanpassing in strategie**\nGeen aanpassing nodig."


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

    _, col_swap = st.columns([5, 1])
    with col_swap:
        if st.button("Wissel", key="swap_today"):
            st.session_state["show_swap_today"] = True

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
