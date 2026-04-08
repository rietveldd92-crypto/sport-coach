"""
feedback_engine — Gedeelde AI-feedback generator voor app.py, coach.py en auto_feedback.py.

Bevat:
- Coach persona / system prompt
- Context builders (wellness, neighbors, similar workouts, state)
- Prompt assemblage
- Gemini call (Pro voor key sessies, Flash voor de rest, Pro→Flash fallback)
- Rule-based fallback

De pure functies hier weten niets van Streamlit caching of CLI argparse.
De caller (app.py / coach.py / auto_feedback.py) is verantwoordelijk voor:
- Het ophalen van events, activities, wellness data
- Optioneel cachen van calls (Streamlit doet dat zelf)
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Optional

from agents import workout_analysis
from agents.workout_feel import get_post_workout_note
from agents.workout_analysis import classify_workout

# ── LLM SETUP ──────────────────────────────────────────────────────────────

GEMINI_PRO_MODEL = "gemini-2.5-pro"
GEMINI_FLASH_MODEL = "gemini-2.5-flash"

# Workout types die "Pro" verdienen — daar is diepere analyse meeste waard
HARD_WORKOUT_TYPES = {
    "run_long", "run_tempo", "run_intervals", "run_progression", "run_fartlek",
    "bike_threshold", "bike_sweetspot", "bike_over_unders", "bike_tempo",
}

# Referentiewaarden — pas hier aan als FTP/HRmax verandert
ATHLETE_FTP = 290
ATHLETE_HRMAX = 190
Z2_HR_MIN = round(ATHLETE_HRMAX * 0.68)  # 129
Z2_HR_MAX = round(ATHLETE_HRMAX * 0.80)  # 152

_gemini_client = None
_genai_types = None


def _ensure_gemini():
    """Lazy-init de Gemini client. Returns True als beschikbaar."""
    global _gemini_client, _genai_types
    if _gemini_client is not None:
        return True
    try:
        from google import genai as google_genai
        from google.genai import types as genai_types
    except ImportError:
        return False

    key = os.getenv("GOOGLE_API_KEY")
    if not key:
        # Streamlit secrets fallback (alleen als streamlit beschikbaar)
        try:
            import streamlit as st
            key = st.secrets.get("GOOGLE_API_KEY")
        except Exception:
            pass
    if not key:
        return False

    _gemini_client = google_genai.Client(api_key=key)
    _genai_types = genai_types
    return True


def gemini_available() -> bool:
    """Check of Gemini client kan starten."""
    return _ensure_gemini()


# ── COACH PERSONA ──────────────────────────────────────────────────────────

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


# ── CONTEXT HELPERS ────────────────────────────────────────────────────────

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


def build_wellness_context(activity_date: str, wellness_records: list) -> str:
    """Bouw een wellness-snippet voor de activity-datum + 7-day trend.

    `wellness_records` is een lijst zoals teruggegeven door intervals_client.get_wellness().
    """
    if not wellness_records:
        return ""

    today_record = next((w for w in wellness_records if w.get("id") == activity_date), None)

    sorted_w = sorted(wellness_records, key=lambda w: w.get("id", ""))
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


def build_neighbor_context(week_events: list, event_date: str) -> str:
    """Wat is er gisteren gedaan en wat staat er morgen gepland?

    `week_events` is een lijst van dicts met keys 'event', 'activity', 'done'
    (zoals app.py's match_events_activities() returnt).
    """
    try:
        d = date.fromisoformat(event_date)
    except Exception:
        return ""

    yesterday = (d - timedelta(days=1)).isoformat()
    tomorrow = (d + timedelta(days=1)).isoformat()

    lines = []
    for item in week_events:
        e = item.get("event", {})
        e_date = e.get("start_date_local", "")[:10]
        e_name = e.get("name", "?")

        if e_date == yesterday:
            if item.get("done") and item.get("activity"):
                act = item["activity"]
                tss = act.get("icu_training_load") or 0
                hr = act.get("average_heartrate") or 0
                hr_pct = round(hr / ATHLETE_HRMAX * 100) if hr else 0
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


def build_similar_workouts_context(wtype: str, activity_id, recent_28d: list) -> str:
    """Vergelijk met max 3 vergelijkbare workouts uit afgelopen 28 dagen."""
    similar = []
    for act in recent_28d:
        if str(act.get("id")) == str(activity_id):
            continue
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
        hr_pct = round(hr / ATHLETE_HRMAX * 100) if hr else 0
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


# ── PROMPT ASSEMBLAGE ─────────────────────────────────────────────────────

def build_prompt(
    event: dict,
    activity: dict,
    *,
    state: dict,
    wellness_records: list,
    week_events: Optional[list] = None,
    recent_28d: Optional[list] = None,
) -> tuple[str, str, dict]:
    """Bouw de complete Gemini prompt + return (prompt, model_name, analysis).

    `model_name` is GEMINI_PRO_MODEL voor key sessies, anders Flash.
    """
    analysis = workout_analysis.analyze(event, activity)
    metrics = analysis["metrics"]
    insights = list(analysis["insights"])  # copy
    wtype = analysis["workout_type"]
    prompt_focus = analysis["prompt_focus"]

    feel_note = get_post_workout_note(event, metrics)
    if feel_note and not insights:
        insights = [feel_note]
    elif feel_note:
        insights.insert(0, feel_note)

    state_ctx = build_state_context(state)

    activity_date = (activity.get("start_date_local") or "")[:10]
    wellness_ctx = build_wellness_context(activity_date, wellness_records or []) if activity_date else ""

    neighbor_ctx = ""
    if week_events:
        event_date = (event.get("start_date_local") or "")[:10]
        if event_date:
            neighbor_ctx = build_neighbor_context(week_events, event_date)

    similar_ctx = build_similar_workouts_context(wtype, activity.get("id"), recent_28d or [])

    insights_str = "\n".join(f"- {i}" for i in insights) if insights else "- Geen bijzonderheden uit de auto-analyse."

    deep_data = []
    if metrics.get("interval_powers"):
        deep_data.append(
            f"Power per work-interval: {metrics['interval_powers']}W (gem {metrics.get('interval_avg_power', '?')}W = {metrics.get('interval_pct_ftp', '?')}% FTP, spread {metrics.get('interval_power_spread_pct', '?')}%)"
        )
    if metrics.get("hr_drift_pct") is not None:
        deep_data.append(f"HR drift over intervals: {metrics['hr_drift_pct']}%")
    if metrics.get("splits"):
        split_str = ", ".join(f"{s['pace']:.2f}" for s in metrics["splits"][:12])
        deep_data.append(f"Km-splits (min/km): {split_str}")
    if metrics.get("cardiac_decoupling_pct") is not None:
        deep_data.append(f"Cardiac decoupling: {metrics['cardiac_decoupling_pct']}% (lager = beter aerobe basis)")
    if metrics.get("avg_pace_first_third") and metrics.get("avg_pace_last_third"):
        deep_data.append(
            f"Pacing: eerste derde {metrics['avg_pace_first_third']:.2f}/km → laatste derde {metrics['avg_pace_last_third']:.2f}/km"
        )
    if metrics.get("interval_paces"):
        deep_data.append(f"Interval paces (min/km): {[f'{p:.2f}' for p in metrics['interval_paces']]}")
    if metrics.get("z1z2_pct") is not None:
        deep_data.append(f"Tijd in zones: Z1+Z2 {metrics['z1z2_pct']}%, boven Z2 {metrics['z3plus_pct']}%")
    if metrics.get("vi"):
        deep_data.append(f"Variability Index: {metrics['vi']}")
    if metrics.get("cadence"):
        deep_data.append(f"Gem. kadans: {metrics['cadence']}")
    deep_str = "\n".join(f"- {d}" for d in deep_data) if deep_data else "- Geen interval/split-detail beschikbaar."

    if metrics.get("avg_power") and metrics.get("np_power"):
        power_line = f"Vermogen: {metrics['avg_power']}W (gem) / {metrics['np_power']}W (NP) = {round(metrics['avg_power']/ATHLETE_FTP*100)}% FTP"
    elif metrics.get("avg_power"):
        power_line = f"Vermogen: {metrics['avg_power']}W = {round(metrics['avg_power']/ATHLETE_FTP*100)}% FTP"
    else:
        power_line = ""
    pace_line = f"Gem. pace: {metrics.get('avg_pace', '?')} min/km" if metrics.get("avg_pace") else ""

    target_tss = metrics.get("target_tss") or event.get("load_target") or 0
    target_line = f"Geplande TSS-target: {target_tss}" if target_tss else ""
    desc = (event.get("description") or "").strip()[:300]

    prompt = f"""{COACH_SYSTEM_PROMPT}

REFERENTIEWAARDEN ATLEET (gebruik DEZE, verzin geen andere)
- FTP: {ATHLETE_FTP}W
- HRmax: {ATHLETE_HRMAX}bpm
- Z2 hartslag-bandbreedte: {Z2_HR_MIN}–{Z2_HR_MAX}bpm (68–80% HRmax)

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
Maximaal 3 acties, genummerd. Specifiek, meetbaar, toepasbaar. "Morgen Z2, HR onder {Z2_HR_MAX}bpm" — niet "blijf rustig".

**Aanpassing in strategie**
Alleen invullen als je vindt dat het weekplan of de fase-aanpak moet schuiven. Anders schrijf: "geen aanpassing nodig".

EXTRA REGEL
Noem nooit interne workout-type tags zoals "bike_threshold", "run_long", "run_intervals" letterlijk in je output. Gebruik gewone Nederlandse termen: "threshold-rit", "lange duurloop", "intervaltraining"."""

    model_name = GEMINI_PRO_MODEL if wtype in HARD_WORKOUT_TYPES else GEMINI_FLASH_MODEL
    return prompt, model_name, analysis


# ── GEMINI CALL ────────────────────────────────────────────────────────────

def gemini_call(model_name: str, prompt: str) -> str:
    """Single Gemini-call met juiste config per model.

    - Flash: thinking uit (snel + voorspelbaar token-budget)
    - Pro: thinking aan met beperkt budget (kwaliteit telt hier)
    """
    if not _ensure_gemini():
        raise RuntimeError("Gemini client niet beschikbaar (geen GOOGLE_API_KEY)")

    if "flash" in model_name:
        cfg = _genai_types.GenerateContentConfig(
            max_output_tokens=2000,
            temperature=0.7,
            thinking_config=_genai_types.ThinkingConfig(thinking_budget=0),
        )
    else:
        cfg = _genai_types.GenerateContentConfig(
            max_output_tokens=4000,
            temperature=0.7,
            thinking_config=_genai_types.ThinkingConfig(thinking_budget=1024),
        )

    response = _gemini_client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=cfg,
    )
    text = (response.text or "").strip()
    if not text:
        try:
            fr = response.candidates[0].finish_reason
            raise RuntimeError(f"lege response, finish_reason={fr}")
        except (AttributeError, IndexError):
            raise RuntimeError("lege response zonder candidate")
    return text


# ── HIGH-LEVEL ENTRY POINTS ────────────────────────────────────────────────

def generate_feedback(
    event: dict,
    activity: dict,
    *,
    state: dict,
    wellness_records: list,
    week_events: Optional[list] = None,
    recent_28d: Optional[list] = None,
    call_fn=None,
) -> str:
    """Genereer AI feedback. Caller geeft alle data mee — geen HTTP fetches hier.

    `call_fn(model_name, prompt) -> str` kan worden gegeven door de caller voor
    custom caching (bijv. Streamlit's @st.cache_data). Default = directe gemini_call.
    """
    if not activity:
        return "Geen activiteit om feedback op te geven."

    prompt, model_name, analysis = build_prompt(
        event, activity,
        state=state,
        wellness_records=wellness_records,
        week_events=week_events,
        recent_28d=recent_28d,
    )

    if not _ensure_gemini():
        return rule_feedback(analysis)

    if call_fn is None:
        call_fn = gemini_call

    try:
        return call_fn(model_name, prompt)
    except Exception as e:
        # Pro quota op? Probeer Flash als fallback
        if model_name == GEMINI_PRO_MODEL:
            try:
                return call_fn(GEMINI_FLASH_MODEL, prompt)
            except Exception as e2:
                return f"(Gemini fout: {e2})\n\n" + rule_feedback(analysis)
        return f"(Gemini fout: {e})\n\n" + rule_feedback(analysis)


def rule_feedback(analysis: dict) -> str:
    """Fallback als Gemini niet beschikbaar is. Geen quote, geen motivatiepraat."""
    insights = analysis.get("insights", [])
    if not insights:
        return (
            "**Wat gaat goed**\nWorkout voltooid, geen bijzonderheden uit auto-analyse.\n\n"
            "**Wat gaat fout / risico's**\nGeen risico's gedetecteerd.\n\n"
            "**Concreet advies**\n1. Volg het bestaande weekplan.\n\n"
            "**Aanpassing in strategie**\nGeen aanpassing nodig."
        )
    text = " ".join(insights[:3])
    return (
        f"**Wat gaat goed**\n{text}\n\n"
        "**Wat gaat fout / risico's**\nGeen specifieke risico's uit deze auto-analyse — Gemini AI niet beschikbaar voor diepere check.\n\n"
        "**Concreet advies**\n1. Volg het bestaande plan tot AI weer werkt.\n\n"
        "**Aanpassing in strategie**\nGeen aanpassing nodig."
    )
