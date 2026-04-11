"""
adjust.py — Pas de lopende week aan op basis van jouw feedback.

Gebruik:
    python adjust.py "Kniepijn bij de run van dinsdag"
    python adjust.py "Donderdag overgeslagen door werk"
    python adjust.py "Gisteren extra 5km gelopen, voelde me geweldig"
    python adjust.py "Alles goed, geen klachten"
    python adjust.py --status

Gemini Flash interpreteert de tekst en bepaalt:
- Welke injury-signalen er zijn
- Welke sessies aangepast/verwijderd moeten worden
- Of het weekdoel omhoog/omlaag moet
"""

import os
import sys
import json
import argparse
from datetime import date, timedelta
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import intervals_client as api
import shared
from agents import injury_guard, load_manager

STATE_PATH = Path(__file__).parent / "state.json"

try:
    from google import genai
    _gemini_key = os.getenv("GOOGLE_API_KEY")
    if _gemini_key:
        _gemini_client = genai.Client(api_key=_gemini_key)
        GEMINI_AVAILABLE = True
    else:
        GEMINI_AVAILABLE = False
except ImportError:
    GEMINI_AVAILABLE = False

FEEDBACK_PROMPT = """Je bent de coach-AI van een hardloper die herstelt van een gluteus medius blessure.
De atleet heeft een doel: sub 40 min op de 10km op 16 juni 2026.
Huidige status: {status}

De atleet geeft de volgende feedback:
"{feedback}"

Analyseer dit en geef een JSON terug met exact deze velden (geen extra tekst, alleen JSON):
{{
    "injury_signals": [],        // lijst met signalen: "knie_pijn", "knie_twinge", "knie_ongemak", "rug_pijn", "rug_trekkend", "heup_instabiel", "heup_pijn", "been_uitdraaien"
    "sessie_impact": "normaal",  // "gemist", "te_zwaar", "te_licht", "normaal", "extra_gedaan"
    "urgentie": "volgende_week", // "direct" (pas deze week aan) of "volgende_week" (meenemen bij planning)
    "verwijder_intensiteit": false, // verwijder alle intensiteitsessies uit de huidige week?
    "volume_aanpassing": 0,      // -20, -10, 0, +10 (percentage aanpassing weekvolume)
    "rust_dag_vandaag": false,   // is een rustdag vandaag aanbevolen?
    "bericht": ""                // kort bericht voor de atleet (Nederlands, coach-toon)
}}

Wees conservatief: bij twijfel liever minder belasting. Kniepin = altijd directe actie.
"""


_load_state = shared.load_state
_save_state = shared.save_state


def _rule_based_parse(feedback: str) -> dict:
    """
    Simpele rule-based fallback als Claude niet beschikbaar is.
    Zoekt op sleutelwoorden.
    """
    fb = feedback.lower()
    signals = []
    sessie_impact = "normaal"
    urgentie = "volgende_week"
    verwijder_intensiteit = False
    volume_aanpassing = 0
    rust_dag = False

    # Positieve markers — als deze aanwezig zijn, geen injury-signalen detecteren
    positive_markers = ["prima", "goed", "geen pijn", "geen klachten", "geweldig", "super",
                        "lekker", "zonder problemen", "probleemloos", "gaat goed"]
    is_positive = any(m in fb for m in positive_markers)

    if not is_positive:
        # DIRECT signalen — gewrichtsklachten, onmiddellijk ingrijpen
        if any(w in fb for w in ["kniepijn", "knie pijn", "knie doet pijn", "pijn in mijn knie", "knieklacht"]):
            signals.append("knie_pijn")
            verwijder_intensiteit = True
            urgentie = "direct"
            volume_aanpassing = -20
            rust_dag = True
        if any(w in fb for w in ["heuppijn", "heup pijn", "heup doet pijn"]):
            signals.append("heup_pijn")
            verwijder_intensiteit = True
            urgentie = "direct"
            volume_aanpassing = min(volume_aanpassing, -20)
            rust_dag = True
        if any(w in fb for w in ["rugpijn", "rug pijn", "scherpe rug", "rug schiet"]):
            signals.append("rug_pijn")
            urgentie = "direct"
            volume_aanpassing = min(volume_aanpassing, -15)

        # BUFFERED signalen — normaal trainingsgevoel, gaat door de buffer
        # Deze worden genoteerd maar leiden niet direct tot aanpassingen
        if any(w in fb for w in ["knie voelt", "knie wat", "knie ongemak", "knie reageert", "knie trekt"]):
            signals.append("knie_twinge")
            # Geen directe actie — injury_guard buffer handelt dit af
        if any(w in fb for w in ["onderrug", "stuitje", "rug trekt", "rug reageert"]):
            signals.append("rug_trekkend")
        if any(w in fb for w in ["heup instabiel", "heup reageert", "heup voelt"]):
            signals.append("heup_instabiel")

    # Sessie-impact
    if any(w in fb for w in ["overgeslagen", "gemist", "niet gedaan", "geannuleerd", "skippen", "geskipt"]):
        sessie_impact = "gemist"
        urgentie = "volgende_week"
    elif any(w in fb for w in ["extra gelopen", "extra km", "meer gedaan dan", "langer gelopen dan"]):
        sessie_impact = "extra_gedaan"
        # Buffered — één keer extra is geen probleem
        signals.append("sessie_te_zwaar")
    elif any(w in fb for w in ["te zwaar", "afgemat", "uitgeput", "kapot", "doodmoe"]):
        sessie_impact = "te_zwaar"
        # Buffered — één zware dag hoort bij training
        signals.append("sessie_te_zwaar")
    elif any(w in fb for w in ["te makkelijk", "veel te licht", "had meer kunnen"]):
        sessie_impact = "te_licht"

    # Alles goed — reset
    if any(w in fb for w in ["alles goed", "geen klachten", "prima gelopen", "geweldig", "alles prima"]):
        sessie_impact = "normaal"
        signals = []
        urgentie = "volgende_week"

    # Bepaal of er directe signalen zijn (alleen die triggeren urgentie)
    from agents.injury_guard import DIRECT_SIGNALS
    has_direct = any(s in DIRECT_SIGNALS for s in signals)
    has_buffered_only = signals and not has_direct

    if has_direct:
        bericht = f"Gewrichtsklacht ({', '.join(s for s in signals if s in DIRECT_SIGNALS)}). Direct aanpassen."
    elif has_buffered_only:
        bericht = "Genoteerd. Eén slechte dag is geen probleem — pas bij een patroon grijpen we in."
        urgentie = "volgende_week"
        verwijder_intensiteit = False
        volume_aanpassing = 0
        rust_dag = False
    elif sessie_impact == "gemist":
        bericht = "Sessie gemist — kijken of de kwaliteitstraining elders in de week past."
    elif sessie_impact == "extra_gedaan":
        bericht = "Extra gedaan — genoteerd. We houden het in de gaten."
    else:
        bericht = "Goed bezig. Geen aanpassingen nodig."

    return {
        "injury_signals": signals,
        "sessie_impact": sessie_impact,
        "urgentie": urgentie,
        "verwijder_intensiteit": verwijder_intensiteit,
        "volume_aanpassing": volume_aanpassing,
        "rust_dag_vandaag": rust_dag,
        "bericht": bericht,
    }


def _gemini_parse(feedback: str, current_status: str) -> dict:
    """Gebruik Gemini Flash om feedback te interpreteren."""
    prompt = FEEDBACK_PROMPT.format(status=current_status, feedback=feedback)

    response = _gemini_client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
    )

    text = response.text.strip()
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def _get_current_week_workouts() -> list:
    """Haal de workouts van de huidige week op uit intervals.icu."""
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    try:
        events = api.get_events(monday, sunday)
        return [e for e in events if e.get("category") == "WORKOUT"]
    except Exception as e:
        print(f"  ⚠️  Kan events niet ophalen: {e}")
        return []


def _apply_adjustments(parsed: dict, dry_run: bool = True) -> None:
    """
    Pas de huidige week aan op basis van de geanalyseerde feedback.
    """
    signals = parsed.get("injury_signals", [])
    urgentie = parsed.get("urgentie", "volgende_week")
    verwijder_intensiteit = parsed.get("verwijder_intensiteit", False)
    volume_aanpassing = parsed.get("volume_aanpassing", 0)
    rust_dag = parsed.get("rust_dag_vandaag", False)

    # Sla injury-signalen op in state
    if signals:
        injury_guard.analyze(feedback_signals=signals)
        print(f"\n  📌 Injury-signalen opgeslagen: {', '.join(signals)}")

    # Directe aanpassingen deze week
    if urgentie == "direct":
        workouts = _get_current_week_workouts()
        today = date.today()

        # Harde sessies in de toekomst
        future_hard = [
            w for w in workouts
            if date.fromisoformat(w.get("start_date_local", "")[:10]) > today
            and any(kw in w.get("name", "").lower() for kw in
                    ["sweetspot", "vo2", "interval", "tempo", "strides"])
        ]

        # Toekomstige lichte sessies (morgen en dag erna)
        future_easy = [
            w for w in workouts
            if date.fromisoformat(w.get("start_date_local", "")[:10]) > today
        ]

        print(f"\n  Huidige week: {len(workouts)} workouts gevonden.")

        if verwijder_intensiteit and future_hard:
            print(f"  Intensiteitssessies te verwijderen: {len(future_hard)}")
            for w in future_hard:
                print(f"    ❌ {w.get('name')} op {w.get('start_date_local', '')[:10]}")
                if not dry_run:
                    try:
                        api.delete_event(w["id"])
                    except Exception as e:
                        print(f"       Fout bij verwijderen: {e}")

        if rust_dag:
            # Verwijder de eerstvolgende workout
            tomorrow_workouts = [
                w for w in workouts
                if date.fromisoformat(w.get("start_date_local", "")[:10]) == today + timedelta(days=1)
            ]
            if tomorrow_workouts:
                for w in tomorrow_workouts:
                    print(f"  ❌ Morgen rust: {w.get('name')} verwijderd.")
                    if not dry_run:
                        try:
                            api.delete_event(w["id"])
                        except Exception as e:
                            print(f"     Fout: {e}")

        # Verzacht de eerstvolgende 2 harde sessies als volume_aanpassing negatief
        if volume_aanpassing <= -10 and not verwijder_intensiteit:
            for w in future_hard[:2]:
                new_name = f"[Verzacht] {w.get('name', '')}"
                print(f"  📉 Verzacht: {w.get('name')} → {new_name}")
                if not dry_run:
                    try:
                        api.update_event(w["id"], name=new_name)
                    except Exception as e:
                        print(f"     Fout: {e}")

    elif urgentie == "volgende_week":
        print("  📋 Aanpassingen worden meegenomen bij de volgende weekplanning.")

    # Update state met sessie-impact
    state = _load_state()
    if state["weekly_log"]:
        state["weekly_log"][-1]["notes"] = (
            state["weekly_log"][-1].get("notes", "") +
            f" | Feedback: {parsed.get('bericht', '')}"
        )
    _save_state(state)

    if dry_run and urgentie == "direct":
        print("\n  [DRY RUN] Geen wijzigingen doorgevoerd. Voer uit met --schrijf.")


def main():
    parser = argparse.ArgumentParser(description="Sport Coach — week aanpassen op basis van feedback")
    parser.add_argument("feedback", nargs="?", default=None,
                        help="Jouw feedback in gewone taal")
    parser.add_argument("--schrijf", action="store_true",
                        help="Pas de events daadwerkelijk aan in intervals.icu")
    parser.add_argument("--status", action="store_true",
                        help="Toon huidige status")
    args = parser.parse_args()

    if args.status or not args.feedback:
        ig = injury_guard.analyze()
        lm = load_manager.analyze()
        print("\n═══ HUIDIGE STATUS ═══")
        print(f"Injury Guard: {ig['status'].upper()} — {ig['message']}")
        print(f"CTL/ATL/TSB: {lm['ctl']} / {lm['atl']} / {lm['tsb']:+.1f}")
        print(f"Fase: {lm['current_phase']} | Weekdoel: {lm['recommended_weekly_tss']} TSS")
        return

    feedback = args.feedback
    dry_run = not args.schrijf

    print(f"\n  Feedback: \"{feedback}\"")
    print("  Analyseren...")

    # Huidige status voor context
    ig = injury_guard.analyze()
    status_str = f"Injury Guard: {ig['status']}, {ig['days_symptom_free']} symptoomvrije dagen."

    # Interpreteer feedback
    if GEMINI_AVAILABLE:
        try:
            parsed = _gemini_parse(feedback, status_str)
            print("  (Gemini Flash analyse)")
        except Exception as e:
            print(f"  ⚠️  Gemini niet bereikbaar ({e}), rule-based analyse.")
            parsed = _rule_based_parse(feedback)
    else:
        parsed = _rule_based_parse(feedback)
        print("  (Rule-based analyse — geen GOOGLE_API_KEY)")

    # Toon analyse
    print(f"\n  📊 Analyse:")
    print(f"  Injury-signalen:    {parsed.get('injury_signals') or 'geen'}")
    print(f"  Sessie-impact:      {parsed.get('sessie_impact')}")
    print(f"  Urgentie:           {parsed.get('urgentie')}")
    print(f"  Intensiteit weg:    {'ja' if parsed.get('verwijder_intensiteit') else 'nee'}")
    print(f"  Volume aanpassing:  {parsed.get('volume_aanpassing'):+d}%")
    print(f"  Rust vandaag:       {'ja' if parsed.get('rust_dag_vandaag') else 'nee'}")
    print(f"\n  🗣️  Coach: {parsed.get('bericht')}")

    _apply_adjustments(parsed, dry_run=dry_run)


if __name__ == "__main__":
    main()
