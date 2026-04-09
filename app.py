"""
Sport Coach — Web UI (Streamlit)

    streamlit run app.py
"""

import os
import random
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
import history_db
import tp_sync_service
import ui_components as ui
from agents import workout_library as lib
from agents import feedback_engine
from agents.workout_feel import get_feel_note
from trainingpeaks_errors import TPAPIError, TPAuthError, TPConversionError

# Zorg dat de history-db migraties zijn toegepast (idempotent).
# Dit moet één keer per app-run gebeuren, vóór de eerste query.
history_db.ensure_migrations()

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
    # moeten doen per klik). Fallback voor het geval intervals_client op de
    # cloud nog een oudere versie is zonder de resolve-parameter.
    try:
        events = api.get_events(monday, sunday, resolve=True)
    except TypeError:
        # Oude signature zonder resolve — TP sync werkt dan niet vanaf de UI
        # maar de rest blijft draaien.
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


def compute_ideal_tss(matched: list, current_event_id, weekly_target: float) -> float:
    """Bereken hoeveel TSS deze ene workout 'idealiter' zou leveren.

    Logica: het weekelijkse TSS-target minus wat al voltooid is minus wat er
    nog op andere dagen gepland staat. Dat is het gat dat deze ene workout
    zou moeten vullen om het weekplan rond te krijgen.

    - Te veel TSS al gedaan/gepland → lagere target voor deze swap
    - Te weinig → hogere target
    - Clamp [30, 200] om extreme targets te voorkomen bij lege of volle weken.
    """
    done_tss = 0.0
    other_planned_tss = 0.0
    current_id = str(current_event_id)

    for item in matched:
        event = item.get("event", {})
        eid = str(event.get("id", ""))

        if item.get("done") and item.get("activity"):
            done_tss += item["activity"].get("icu_training_load") or 0
        elif eid != current_id:
            # Niet de huidige workout én nog niet voltooid → plan TSS
            other_planned_tss += event.get("load_target") or 0

    ideal = weekly_target - done_tss - other_planned_tss
    return max(30.0, min(200.0, ideal))


def perform_instant_swap(event: dict, category: str, ftp: int = 290,
                          ideal_tss: float | None = None) -> dict | None:
    """Pak de best-passende (op TSS) keuze uit de top opties en schrijf meteen.

    Als `ideal_tss` is meegegeven: library sorteert op TSS-afstand en we
    pakken random uit top-5 (variatie binnen passende opties).

    Als `ideal_tss` is None: library doet random shuffle en we pakken random
    uit top-3 (legacy gedrag).

    Zet een success flash + undo payload in session_state voor show_swap_flash().
    """
    options = lib.get_swap_options(event, category, ftp=ftp, target_tss=ideal_tss)
    if not options:
        st.session_state["swap_flash"] = {
            "ok": False, "msg": f"Geen alternatieven gevonden in categorie '{category}'"
        }
        return None

    # Vermijd dezelfde workout als we toch al hebben — filter op naam
    current_name = (event.get("name") or "").lower()
    options = [o for o in options if o.get("naam", "").lower() != current_name]
    if not options:
        st.session_state["swap_flash"] = {
            "ok": False, "msg": "Alleen deze workout-variant beschikbaar in library"
        }
        return None

    # Bij TSS-sorting: variatie uit top-5 passende opties.
    # Bij random: top-3 zoals voorheen.
    pool_size = 5 if ideal_tss is not None else 3
    pick_pool = options[:pool_size]
    chosen = random.choice(pick_pool)

    try:
        api.update_event(
            event["id"],
            name=chosen["naam"],
            description=chosen["beschrijving"],
            type=chosen.get("sport", event.get("type")),
            load_target=chosen.get("tss_geschat"),
        )
    except Exception as exc:
        st.session_state["swap_flash"] = {
            "ok": False, "msg": f"Swap mislukt: {exc}"
        }
        return None

    # --- TP swap-propagatie ---
    # Als deze workout al gesynced was naar TP (en Zwift), moet de nieuwe
    # versie daar ook komen. is_synced() check is goedkoop; alleen als
    # die hit doet propagate_swap_if_synced het echte delete+post werk.
    tp_propagation_msg = ""
    if config.get_bool("TP_SYNC_ENABLED", default=False) and tp_sync_service.is_synced(event.get("id")):
        try:
            # Fresh event fetchen met workout_doc voor de converter
            def _fetch_fresh():
                start = date.fromisoformat((event.get("start_date_local") or "")[:10])
                events_new = api.get_events(start, start, resolve=True)
                for ev in events_new:
                    if str(ev.get("id")) == str(event.get("id")):
                        return ev
                return None

            result = tp_sync_service.propagate_swap_if_synced(
                event,
                _fetch_fresh,
                config.get_secret("TP_AUTH_COOKIE") or "",
            )
            if result and result.get("replaced"):
                tp_propagation_msg = " · ✅ ook in TP ververst"
        except TPAuthError as exc:
            tp_propagation_msg = f" · ⚠ TP niet ververst: cookie verlopen"
        except TPConversionError as exc:
            tp_propagation_msg = f" · ⚠ TP niet ververst: {exc}"
        except TPAPIError as exc:
            tp_propagation_msg = f" · ⚠ TP niet ververst: {exc}"

    # Success flash + undo payload. Toon TSS zodat je ziet hoe het past.
    new_tss = chosen.get("tss_geschat") or 0
    orig_tss = event.get("load_target") or 0
    tss_info = f" ({new_tss:.0f} TSS"
    if orig_tss:
        delta = new_tss - orig_tss
        tss_info += f", {delta:+.0f} vs origineel"
    if ideal_tss is not None:
        tss_info += f", week-target {ideal_tss:.0f}"
    tss_info += ")"

    st.session_state["swap_flash"] = {
        "ok": True,
        "msg": f"→ Gewisseld naar '{chosen['naam']}'{tss_info}{tp_propagation_msg}",
        "undo": {
            "event_id": event["id"],
            "orig_name": event.get("name", ""),
            "orig_description": event.get("description", ""),
            "orig_type": event.get("type", ""),
            "orig_load_target": event.get("load_target"),
        },
    }
    return chosen


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


def tsb_to_human(tsb: float) -> str:
    """Vertaal TSB (form) naar menselijke taal."""
    if tsb < -20:
        return "Diep vermoeid. Dit is opbouw-territorium."
    elif tsb < -10:
        return "Licht vermoeid. Normaal voor een opbouwweek."
    elif tsb < 0:
        return "Redelijk hersteld. Kwaliteit mag je aan."
    elif tsb < 10:
        return "Fris en klaar. Goede dag voor een harde sessie."
    else:
        return "Piek-fris. Je bent getapered of rustig geweest."


# ── TP SYNC BUTTON HELPER ───────────────────────────────────────────────────

def render_tp_sync_button(event: dict, key_suffix: str, container=None):
    """Render de TP-sync knop voor één event.

    Toont niets als:
    - feature-flag `TP_SYNC_ENABLED` uit staat
    - sport wordt niet ondersteund
    - workout-datum is NIET vandaag of morgen (zie DECISIONS.md — de
      atleet syncd alleen op de dag zelf om Zwift te laden)

    Toont "✅ TP" label als event al gesynced is (volgens state.json).
    Anders: "→ TP" knop die tp_sync_service.sync_event() triggert.

    Returns True als er iets werd gerenderd (knop of check).
    """
    tp_enabled = config.get_bool("TP_SYNC_ENABLED", default=False)
    if not tp_enabled:
        return False

    e_type = event.get("type", "?")
    if e_type not in tp_sync_service.SUPPORTED_SPORTS:
        return False

    # Constraint: alleen vandaag/morgen sync-knop tonen.
    event_date = (event.get("start_date_local") or "")[:10]
    if not tp_sync_service.is_syncable_date(event_date):
        return False

    event_id = str(event.get("id", ""))
    target = container if container is not None else st

    if tp_sync_service.is_synced(event_id):
        target.caption("✅ TP")
        return True

    pending_key = f"tp_sync_pending_{event_id}"
    button_key = f"tp_sync_{event_id}_{key_suffix}"
    if target.button(
        "→ TP",
        key=button_key,
        disabled=st.session_state.get(pending_key, False),
    ):
        st.session_state[pending_key] = True
        cookie = config.get_secret("TP_AUTH_COOKIE") or ""
        try:
            result = tp_sync_service.sync_event(event, cookie)
            st.session_state["tp_sync_flash"] = {
                "ok": True,
                "msg": f"Gesynced naar TP (workoutId {result['tp_workout_id']})",
            }
        except TPAuthError as exc:
            st.session_state["tp_sync_flash"] = {
                "ok": False, "msg": f"Cookie verlopen — {exc}",
            }
        except TPConversionError as exc:
            st.session_state["tp_sync_flash"] = {
                "ok": False, "msg": f"Conversie mislukt — {exc}",
            }
        except TPAPIError as exc:
            st.session_state["tp_sync_flash"] = {
                "ok": False, "msg": f"TP API fout — {exc}",
            }
        finally:
            st.session_state[pending_key] = False
        st.rerun()
    return True


def show_tp_flash():
    """Render de TP-sync flash message als die er is (overleeft één rerun)."""
    flash = st.session_state.pop("tp_sync_flash", None)
    if flash:
        tone = "positive" if flash["ok"] else "alert"
        ui.coach_card(flash["msg"], tone=tone)


def show_swap_flash():
    """Render de swap flash message. Bij success toont een undo-knop."""
    flash = st.session_state.pop("swap_flash", None)
    if not flash:
        return

    if not flash.get("ok"):
        ui.coach_card(flash["msg"], tone="alert")
        return

    # Success — toon coach_card met undo-knop ernaast
    col_msg, col_undo = st.columns([4, 1])
    with col_msg:
        ui.coach_card(flash["msg"], tone="positive")

    # Undo payload bevat: event_id, original name/description/type/load_target
    undo = flash.get("undo")
    if undo:
        if col_undo.button("↶ Terug", key=f"undo_swap_{undo['event_id']}"):
            try:
                kwargs = {
                    "name": undo["orig_name"],
                    "description": undo["orig_description"],
                    "type": undo["orig_type"],
                }
                if undo.get("orig_load_target") is not None:
                    kwargs["load_target"] = undo["orig_load_target"]
                api.update_event(undo["event_id"], **kwargs)
                st.cache_data.clear()
                st.session_state["swap_flash"] = {
                    "ok": True,
                    "msg": f"↶ Teruggezet naar '{undo['orig_name']}'",
                }
            except Exception as exc:
                st.session_state["swap_flash"] = {
                    "ok": False, "msg": f"Undo mislukt: {exc}",
                }
            st.rerun()


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


# ── PAGE CONFIG ─────────────────────────────────────────────────────────────

st.set_page_config(page_title="Coach", page_icon="", layout="centered")
ui.inject_global_css()

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
    tsb = state.get("load", {}).get("tsb_estimate", 0)
    st.markdown(f'<div class="sidebar-phase">{phase_main}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sidebar-fitness">{ctl_to_human(ctl)}<br>{tsb_to_human(tsb)}</div>', unsafe_allow_html=True)

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
    ui.coach_card(
        "Geen workouts deze week. Plan er een of wacht op het volgende schema.",
        tone="neutral",
    )
    st.stop()

# ── MORNING CHECK-IN (alleen bij deze week) ────────────────────────────────

today_str = date.today().isoformat()
today_date = date.today()

checkin_existing = None
checkin_score = None
if week_offset == 0:
    checkin_existing = history_db.get_wellness(today_date)
    checkin_score = history_db.morning_checkin_score(today_date)

# Toon check-in form alleen als niet voltooid vandaag EN we deze week bekijken
if week_offset == 0 and not checkin_existing:
    result = ui.morning_checkin(existing=None, key_prefix="checkin_main")
    if result is not None:
        history_db.record_wellness(
            today_date,
            sleep_score=result["sleep_score"],
            energy=result["energy"],
            soreness=result["soreness"],
            motivation=result["motivation"],
        )
        st.rerun()

# Al ingevuld: korte bevestigingsregel met de score + optie om te wijzigen
elif week_offset == 0 and checkin_existing and checkin_score is not None:
    # Compacte bevestiging — geen full form
    score_text = f"Check-in vandaag: {checkin_score:.1f}/5"
    if checkin_score < 3:
        ui.coach_card(
            f"{score_text}. Je lichaam geeft aan dat het wat minder gaat vandaag. "
            "Overweeg de training rustiger te maken — klik 'Wissel → Rustiger' op je workout.",
            tone="warning",
            title="Signaal van vandaag",
        )
    elif checkin_score >= 4.5:
        ui.coach_card(
            f"{score_text}. Alles groen — een goed moment om een kwaliteitssessie "
            "aan te pakken als dat in je plan past.",
            tone="positive",
            title="Groen licht",
        )
    else:
        # Stille bevestiging, geen card
        st.markdown(
            f'<div style="color: var(--text-dim); font-size: 0.78rem; '
            f'text-align: right; margin: -0.4rem 0 0.8rem 0;">'
            f'✓ {score_text}</div>',
            unsafe_allow_html=True,
        )

# ── TODAY CARD (als we deze week bekijken) ─────────────────────────────────

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

    # Stats line voor de today hero: duur + TSS target uit het event
    hero_stats = []
    target_tss = event.get("load_target")
    if target_tss:
        hero_stats.append(f"TSS ~{target_tss:.0f}")
    # Duur proberen te detecteren uit de naam (bijv. "— 45 min")
    for part in (e_name or "").lower().replace("min", " ").split():
        try:
            dur_min = int(part)
            if 10 <= dur_min <= 300:
                hero_stats.insert(0, f"{dur_min} min")
                break
        except ValueError:
            pass

    ui.today_hero(
        title=e_name,
        sport=sport,
        stats_parts=hero_stats,
        coach_note=get_feel_note(event),
        label="Vandaag",
    )

    # Workout structuur — uitklapbaar onder de hero
    description = event.get("description", "")
    if description.strip():
        show_details_key = "show_details_today"
        col_detail, _ = st.columns([2, 4])
        with col_detail:
            label = "Verberg workout ↑" if st.session_state.get(show_details_key) else "Bekijk workout ↓"
            if st.button(label, key="toggle_details_today"):
                st.session_state[show_details_key] = not st.session_state.get(show_details_key, False)
                st.rerun()
        if st.session_state.get(show_details_key):
            ui.workout_details(description)

    # Sync-knop + Wissel-knop — gebruik de gedeelde TP helper
    tp_enabled = config.get_bool("TP_SYNC_ENABLED", default=False)
    tp_supported = e_type in tp_sync_service.SUPPORTED_SPORTS

    if tp_enabled and tp_supported:
        _, col_tp, col_swap = st.columns([4, 1, 1])
        render_tp_sync_button(event, key_suffix="today", container=col_tp)
    else:
        _, col_swap = st.columns([5, 1])

    with col_swap:
        if st.button("Wissel", key="swap_today"):
            st.session_state["show_swap_today"] = True

    # Flash message na sync-actie (overleeft de rerun)
    show_tp_flash()

    # Instant-swap categorie-picker — klik = direct swap, geen tussenmenu
    if st.session_state.get("show_swap_today"):
        st.caption("Wissel naar...")
        cat_cols = st.columns(len(lib.SWAP_CATEGORIES) + 1)
        # Bereken wat deze workout idealiter nog aan TSS moet leveren om het
        # weekelijkse target te halen. Swap-pool wordt dan gesorteerd op
        # afstand tot dat target.
        weekly_target = state.get("load", {}).get("weekly_tss_target", 400)
        ideal_tss = compute_ideal_tss(matched, event.get("id"), weekly_target)

        for ci, (cat_id, cat_info) in enumerate(lib.SWAP_CATEGORIES.items()):
            if cat_cols[ci].button(cat_info["label"], key=f"cat_today_{cat_id}"):
                perform_instant_swap(event, cat_id, ideal_tss=ideal_tss)
                st.cache_data.clear()
                st.session_state["show_swap_today"] = False
                st.rerun()
        if cat_cols[-1].button("✕", key="cancel_swap_today"):
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

# Flash messages boven de week-list — werken voor alle rows
show_tp_flash()
show_swap_flash()

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
    # TP-sync knop verschijnt alleen op workouts van morgen. Vandaag staat
    # al op de Today-card. Gister/verder in de toekomst komt geen knop —
    # zie DECISIONS.md (atleet syncd primair voor Zwift op de dag zelf).
    show_tp_here = (
        not done
        and not is_today
        and config.get_bool("TP_SYNC_ENABLED", default=False)
        and e_type in tp_sync_service.SUPPORTED_SPORTS
        and tp_sync_service.is_syncable_date(e_date)
    )

    # Heeft dit event workout-structuur om te tonen?
    has_details = bool((event.get("description") or "").strip())

    if done or not is_today:
        if done:
            # Done row: Coach | Details | Wissel | filler
            btn_cols = st.columns([1, 1, 1, 3]) if has_details else st.columns([1, 1, 4])
            if btn_cols[0].button("Coach", key=f"fb_{i}"):
                st.session_state[f"show_fb_{i}"] = not st.session_state.get(f"show_fb_{i}", False)
            col_idx = 1
            if has_details:
                if btn_cols[col_idx].button("Details", key=f"det_{i}"):
                    st.session_state[f"show_det_{i}"] = not st.session_state.get(f"show_det_{i}", False)
                col_idx += 1
            if btn_cols[col_idx].button("Wissel", key=f"swap_{i}"):
                st.session_state[f"show_swap_{i}"] = not st.session_state.get(f"show_swap_{i}", False)
        elif not is_today:
            feel = get_feel_note(event)
            # Dynamische kolomberekening: Wissel + Details + (Feel) + (TP)
            button_count = 1  # Wissel
            if has_details:
                button_count += 1
            if feel:
                button_count += 1
            if show_tp_here:
                button_count += 1
            # Maak 1-kolom-per-knop met een filler zodat buttons niet te breed worden
            col_widths = [1] * button_count + [max(1, 5 - button_count)]
            btn_cols = st.columns(col_widths)

            if btn_cols[0].button("Wissel", key=f"swap_{i}"):
                st.session_state[f"show_swap_{i}"] = not st.session_state.get(f"show_swap_{i}", False)
            col_idx = 1
            if has_details:
                if btn_cols[col_idx].button("Details", key=f"det_{i}"):
                    st.session_state[f"show_det_{i}"] = not st.session_state.get(f"show_det_{i}", False)
                col_idx += 1
            if feel:
                if btn_cols[col_idx].button("Voel", key=f"feel_{i}"):
                    st.session_state[f"show_feel_{i}"] = not st.session_state.get(f"show_feel_{i}", False)
                col_idx += 1
            if show_tp_here:
                render_tp_sync_button(event, key_suffix=f"row{i}", container=btn_cols[col_idx])

    # Workout details expand (alleen als toggle aan)
    if st.session_state.get(f"show_det_{i}") and has_details:
        ui.workout_details(event.get("description") or "")

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

    # Instant-swap categorie-picker — klik = direct swap, geen tussenmenu
    if st.session_state.get(f"show_swap_{i}"):
        st.caption("Wissel naar...")
        cat_cols = st.columns(len(lib.SWAP_CATEGORIES) + 1)
        # Week-TSS-budget voor deze swap (zie Today card voor uitleg)
        weekly_target = state.get("load", {}).get("weekly_tss_target", 400)
        ideal_tss = compute_ideal_tss(matched, event.get("id"), weekly_target)

        for ci, (cat_id, cat_info) in enumerate(lib.SWAP_CATEGORIES.items()):
            if cat_cols[ci].button(cat_info["label"], key=f"cat_{i}_{cat_id}"):
                perform_instant_swap(event, cat_id, ideal_tss=ideal_tss)
                st.cache_data.clear()
                st.session_state[f"show_swap_{i}"] = False
                st.rerun()
        if cat_cols[-1].button("✕", key=f"cancel_swap_{i}"):
            st.session_state[f"show_swap_{i}"] = False
            st.rerun()

# Footer is bewust leeg — analytische tone wil geen quote-spam.
