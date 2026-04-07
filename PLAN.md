# Sport Coach Agent Team — Specifiek Plan

## Doel

Een AI coach team dat fungeert als jouw persoonlijke trainer. Het team plant wekelijks trainingen in intervals.icu, evalueert continu op basis van TSS, activiteiten, wellness en jouw feedback, en past het plan aan op basis van blessure-signalen, overtraining of gemiste sessies.

**Jij:** Dylsky (`i85836`), hardloper in herstel na gluteus medius blessure.
**Doelstelling:** Sub 40 min op de 10km in Leiden op **16 juni 2026** (13 weken).

---

## Jouw Situatie (Startpunt 15 maart 2026)

### Blessure context
- **Primair probleem:** Gluteus medius zwakte links → heupinstabiliteit → been draait naar buiten → kniedruk + trekkende pijn onderrug richting stuitje
- **Triggers:** Hogere intensiteit hardlopen (bewezen: 10×1min sneller → directe kniereactie)
- **Huidige training:**
  - Dagelijks revalidatie-oefeningen (heupactivatie, glute med)
  - Om de dag krachttraining
  - Volume opbouw richting 60–70 km/week, nog geen loopintensiteit
  - Fiets indoor (sweetspot werkt goed, geen knieproblemen)

### Wat wel kan, wat niet
| | Nu | Toekomst (conditioneel) |
|---|---|---|
| Rustig hardlopen (Z1-Z2) | ✅ Ja | ✅ Ja |
| Sweetspot fiets | ✅ Ja | ✅ Ja |
| Loopintensiteit (strides, tempolopen) | ❌ Nog niet | ✅ Na groene vlag |
| Krachttraining | ✅ Om de dag | ✅ Ja |
| Revalidatie-oefeningen | ✅ Dagelijks | ✅ Dagelijks |

---

## Trainingsfilosofie

Gebaseerd op **Guido Hartensveld**, **Jim van den Berg** en **Michael Butter**:

### Kernprincipes
1. **Polarized 80/20:** Minimaal 80% van het loopvolume in Z1-Z2 (aeroob, conversatietempo). Maximaal 20% intensief. **Niets in het midden** (Z3 threshold is gif in de basisfase).
2. **Opbouw voor intensiteit:** Eerst volume, dan intensiteit. Intensiteit op een zwakke basis = blessure.
3. **CTL/ATL/TSB model:** Fitheid (CTL) opbouwen zonder vermoeidheid (ATL) te hoog te laten oplopen. Vorm (TSB) piekt op racedag.
4. **Kracht & mobiliteit als training:** Geen optionele extra, maar verplicht onderdeel van het weekprogramma.
5. **Wedstrijd-specifieke afbouw:** De laatste 2-3 weken TSS afbouwen zodat TSB op racedag +15 tot +25 is.

### Sub-40 10km vereisten
- **Doelpace:** 4:00/km
- **Vereist:** VDOT ~50, drempelsnelheid ~4:05-4:10/km
- **CTL bij race:** ~75-85 punten
- **Opbouwpad:**
  - Wk 1-5: Alleen Z1-Z2 hardlopen + fiets sweetspot (basis)
  - Wk 6-8: Korte strides (10×20s) als geen kniepijn → voorzichtig introduceren
  - Wk 9-11: 10km-specifieke intervals (alleen als blessure-vrij)
  - Wk 12: Afbouw
  - Wk 13: Race week

---

## Periodisering (13 weken)

```
Week | Data          | Fase        | Max km | Intensiteit  | Fiets       | Doel CTL
-----|---------------|-------------|--------|--------------|-------------|----------
 1   | 16-22 mrt     | Basis I     | ~40km  | Geen         | 2× sweetspot| ~45
 2   | 23-29 mrt     | Basis I     | ~45km  | Geen         | 2× sweetspot| ~48
 3   | 30 mrt-5 apr  | Basis I     | ~48km  | Geen         | 2× sweetspot| ~52
 4   | 6-12 apr      | Basis II    | ~52km  | Geen         | 2× sweetspot| ~55
 5   | 13-19 apr     | Basis II    | ~55km  | Geen         | 2× sweetspot| ~58
 6   | 20-26 apr     | Opbouw I    | ~55km  | Strides*     | 2× sweetspot| ~62
 7   | 27 apr-3 mei  | Opbouw I    | ~58km  | Strides*     | 2× sweetspot| ~65
 8   | 4-10 mei      | Opbouw II   | ~60km  | Strides*     | 2× VO2max   | ~68
 9   | 11-17 mei     | Specifiek   | ~62km  | Tempo intervals*| 1× sweetspot| ~72
10   | 18-24 mei     | Specifiek   | ~65km  | Tempo intervals*| 1× sweetspot| ~75
11   | 25-31 mei     | Specifiek   | ~63km  | Tempo intervals*| 1× sweetspot| ~78
12   | 1-7 jun       | Afbouw      | ~45km  | Lichte strides| 1× easy    | ~76
13   | 8-16 jun      | Race week   | ~25km  | Race          | Geen        | TSB+20
```
`*` = alleen als Injury Guard groen licht geeft (zie agent hieronder)

---

## Weekstructuur (template)

```
Maandag:    Rust of herstelrun 30 min Z1 + rehab oefeningen
Dinsdag:    Loopduur 60-70 min Z2 + rehab oefeningen + krachttraining
Woensdag:   Fiets sweetspot 45-60 min + rehab oefeningen
Donderdag:  Loopduur 70-80 min Z2 (langste doordeweekse run) + rehab
Vrijdag:    Herstelrun 40 min Z1 of rust + rehab + krachttraining
Zaterdag:   Fiets sweetspot of lang easy + rehab
Zondag:     Lange duurloop 90-120 min Z2 + rehab
```

TSS-verdeling per week:
- Looptss: 60-70% van wekelijkse TSS
- Fiets TSS: 30-40% van wekelijkse TSS
- Revalidatie telt niet mee in TSS

---

## Agent Team Architectuur

```
Sport/
├── .env                           # INTERVALS_ATHLETE_ID, INTERVALS_API_KEY, ANTHROPIC_API_KEY
├── .gitignore
├── requirements.txt               # requests, python-dotenv, anthropic
├── intervals_client.py            # Klaar — uitbreiden met update_event, delete_event
├── state.json                     # Persistente staat (fase, CTL-schatting, blessure-status)
│
├── agents/
│   ├── __init__.py
│   ├── injury_guard.py            # Bewaakt blessure-signalen → rood/geel/groen
│   ├── load_manager.py            # CTL/ATL/TSB berekeningen + weekdoelen
│   ├── endurance_coach.py         # Looptraining ontwerp (Hartensveld-stijl)
│   ├── bike_coach.py              # Fietstraining ontwerp (sweetspot/VO2max)
│   └── week_planner.py            # Combineert alles → events in intervals.icu
│
├── plan_week.py                   # Script: plan komende week in
└── adjust.py                      # Script: pas huidige week aan op basis van feedback
```

---

## Agent 1: Injury Guard (`agents/injury_guard.py`)

**Verantwoordelijkheid:** De blessure-bewaker. Evalueert alle injury-signalen en geeft een stoplicht af dat alle andere agents respecteren.

**Input:**
- `state.json` → `injury_signals` (lijst van gemelde klachten)
- Wellness data (soreness, HRV-trend)
- Activiteiten van afgelopen 7 dagen
- Optioneel: feedback string van gebruiker

**Stoplicht logica:**
```
ROOD  → Geen hardloopintensiteit, volume -30%, alleen Z1, geen krachttraining
        Criteria: knieklacht gemeld afgelopen 3 dagen
                  OF lage rugklacht aanwezig bij enige intensiteit

GEEL  → Geen loopintensiteit, gewoon volume OK, fiets-intensiteit OK
        Criteria: geen acute klacht maar symptomen binnen 7 dagen
                  OF soreness > 4/10 OF HRV sterk dalend

GROEN → Normaal schema, intensiteit mag als periodisering het toelaat
        Criteria: 14+ symptoomvrije trainingsdagen
```

**Output (dict):**
```python
{
    "status": "rood" | "geel" | "groen",
    "run_intensity_allowed": bool,
    "bike_intensity_allowed": bool,
    "strength_allowed": bool,
    "volume_modifier": float,     # 0.7 = 30% minder, 1.0 = normaal, 1.05 = iets meer
    "days_symptom_free": int,
    "message": str,               # Uitleg voor de gebruiker
    "flags": list[str]            # bijv. ["knie_reactie_recent", "hrv_dalend"]
}
```

**Intensiteits-ontgrendeling:**
- Strides mogen na 14 aaneengesloten symptoomvrije dagen
- Tempolopen mogen na 21 aaneengesloten symptoomvrije dagen + strides zonder klachten
- Automatisch terugzetten naar GEEL bij nieuwe melding

---

## Agent 2: Load Manager (`agents/load_manager.py`)

**Verantwoordelijkheid:** Berekent CTL/ATL/TSB en bepaalt hoeveel trainingsbelasting de komende week verantwoord is.

**Input:**
- Activiteiten afgelopen 42 dagen (voor CTL-berekening)
- Wellness data (HRV, slaap, hartslag rust)
- `state.json` → vorige CTL-waarde als fallback
- Injury Guard output (volume_modifier)

**CTL/ATL/TSB berekening:**
```
CTL_nieuw = CTL_oud + (dagTSS - CTL_oud) / 42
ATL_nieuw = ATL_oud + (dagTSS - ATL_oud) / 7
TSB = CTL - ATL

Streefwaarden per fase:
  Basisfase:   TSB tussen -10 en -5  (licht vermoeid = aanpassen)
  Opbouwfase:  TSB tussen -15 en -10 (actieve opbouw)
  Specifiek:   TSB tussen -20 en -15 (piekbelasting)
  Taper:       TSB stijgt naar +20 (race dag)
```

**Output (dict):**
```python
{
    "ctl": float,
    "atl": float,
    "tsb": float,
    "recommended_weekly_tss": float,
    "max_single_session_tss": float,    # geen sessie boven dit getal
    "current_phase": str,               # "basis" | "opbouw" | "specifiek" | "taper"
    "weeks_to_race": int,
    "overtraining_risk": str,           # "laag" | "matig" | "hoog"
    "message": str
}
```

**Wekelijkse TSS targets (bij Injury Guard GROEN, volle belasting):**
```
Week 1-5 (basis):   TSS 350-450
Week 6-8 (opbouw):  TSS 450-550
Week 9-11 (spec):   TSS 550-650
Week 12 (afbouw):   TSS 350-400
Week 13 (race):     TSS 150-200
```

---

## Agent 3: Endurance Coach (`agents/endurance_coach.py`)

**Verantwoordelijkheid:** Ontwerpt de loopsessies voor de week, puur hardlopen. Past de polarized 80/20 methodiek toe van Hartensveld/Van den Berg.

**Input:**
- Load Manager output
- Injury Guard output
- Activiteiten afgelopen 28 dagen (welk volume, welke intensiteit)
- Huidige fase uit `state.json`

**Zone definities (hardlopen, hartslag-gebaseerd):**
```
Z1: <68% HRmax  — herstel/actief herstel
Z2: 68-80% HRmax — aeroob basis (het meeste werk hier)
Z3: 81-87% HRmax — drempel (VERMIJDEN in basis/opbouwfase)
Z4: 88-95% HRmax — VO2max (alleen fase 3+)
Z5: >95% HRmax  — maximaal (alleen race-simulatie)
```

**Sessie-templates per fase:**

*Basisfase (wk 1-5):*
```
Herstelloopje:    30-40 min Z1, na zware dag, maandag of vrijdag
Aeroob Z2:        60-75 min Z2 stabiel, dinsdag/donderdag
Lange duur:       90-120 min Z1/Z2, zondag
```

*Opbouwfase (wk 6-8, alleen GROEN):*
```
Aeroob + strides: 60 min Z2 + 8-10×20s versnellingen (geen sprint, neuromust.)
Lange duur:       100-130 min Z1/Z2
```

*Specifieke fase (wk 9-11, alleen GROEN + 21 dagen symptoomvrij):*
```
Interval 10km:   WU 15 min + 5-8×1000m op 10km pace (4:00/km) + CD 15 min
Tempoloon:       WU 15 min + 20-30 min op drempelpace (4:05-4:10/km) + CD 15 min
Lange duur:      100-120 min Z2
```

**Output (list van session dicts):**
```python
[
    {
        "dag": "dinsdag",
        "type": "aeroob_z2",
        "naam": "Z2 duurloop – 65 min",
        "beschrijving": "Rustig aeroob tempo, hartslag 68-80% max. Praten moet moeiteloos gaan. Geen klokken op tempo.",
        "duur_min": 65,
        "tss_geschat": 65,
        "sport": "Run",
        "intensiteit_zone": "Z2",
        "rehab_reminder": "Glute med activatie voor de run: 3×15 clamshells per kant"
    },
    ...
]
```

---

## Agent 4: Bike Coach (`agents/bike_coach.py`)

**Verantwoordelijkheid:** Ontwerpt de fietssessies. Fiets is jouw primaire intensiteitstool tijdens de revalidatiefase — hier mag je wel zweten.

**Input:**
- Load Manager output (hoeveel fiets-TSS is er nog ruimte voor)
- Injury Guard output (fiets-intensiteit altijd eerder GROEN dan loop-intensiteit)
- FTP uit intervals.icu athlete profiel

**Zone definities (fiets, vermogen):**
```
Z1: <55% FTP    — herstel
Z2: 55-75% FTP  — aeroob
Sweetspot: 88-93% FTP — drempel (hoge trainingsefficiëntie)
Z4: 94-105% FTP — VO2max
```

**Sessie-templates:**

*Sweetspot (basisfase en opbouwfase):*
```
Korte sweetspot: WU 10 min + 2×15 min @ 88-93% FTP (5 min rust) + CD 10 min → ~50 min, TSS ~60
Lang sweetspot:  WU 10 min + 3×15 min @ 88-93% FTP (5 min rust) + CD 10 min → ~65 min, TSS ~80
```

*VO2max fiets (opbouwfase wk 8+):*
```
Short intervals: WU 15 min + 5×4 min @ 108-120% FTP (4 min herstel) + CD 10 min → ~65 min, TSS ~75
```

**Output:** Zelfde formaat als endurance_coach sessie-dicts, sport = "VirtualRide"

---

## Agent 5: Week Planner (`agents/week_planner.py`)

**Verantwoordelijkheid:** Combineert output van alle agents en maakt het definitieve weekschema. Schrijft de events naar intervals.icu. Verwijdert bestaande geplande events voor die week eerst.

**Input:**
- Injury Guard output
- Load Manager output
- Endurance Coach sessies (lijst)
- Bike Coach sessies (lijst)
- Start datum (maandag van de te plannen week)
- Bestaande events deze week (via `get_events`)

**Plannings-regels:**
1. Nooit twee harde sessies achter elkaar
2. Krachttraining: ma/wo/vr OF di/do/za (om de dag), maar niet op de dag van de lange duur
3. Rehab reminder wordt toegevoegd aan ELKE sessie als beschrijving-toevoeging
4. Rustdagen na indicator-signalen (Injury Guard rood)
5. Zondag = lange loop (tenzij Injury Guard rood)
6. Fiets sweetspot bij voorkeur op dag na herstelloopje

**Weekschema voorbeeld (basisfase, Injury Guard geel):**
```
Maandag:   NOTE: Revalidatie-oefeningen (geen run geplanned — rust)
Dinsdag:   Run Z2 65 min (TSS 65) + NOTITIE: krachttraining na
Woensdag:  Fiets sweetspot 50 min (TSS 60)
Donderdag: Run Z2 75 min (TSS 75)
Vrijdag:   Run Z1 herstel 35 min (TSS 30) + NOTITIE: krachttraining na
Zaterdag:  Fiets sweetspot 65 min (TSS 80)
Zondag:    Run lange duur 100 min Z2 (TSS 100)
           Totaal: ~410 TSS
```

**Output:** Events aangemaakt in intervals.icu + console overzicht

---

## Feedback & Aanpassingsscript (`adjust.py`)

Dit is de sleutel tot een adaptief systeem. Draaien als je een sessie hebt gedaan/gemist of pijn hebt.

**Gebruik:**
```bash
# Na een sessie met klachten:
python adjust.py "Kniepijn bij de run van donderdag, run gestopt na 4km"

# Sessie overgeslagen:
python adjust.py "Donderdag overgeslagen door werk"

# Harder gegaan dan gepland:
python adjust.py "Gisteren 15km extra gedaan, voelde me geweldig"

# Goed gevoel:
python adjust.py "Alles goed gegaan, geen klachten, voel me fit"

# Vraag naar status:
python adjust.py --status
```

**Wat het script doet:**
1. Leest de feedback tekst
2. Claude API analyseert de melding en categoriseert:
   - `injury_signal`: welke klacht (knie, rug, heup)
   - `session_impact`: gemist / te zwaar / te licht / normaal
   - `urgency`: direct aanpassen / volgende week meenemen
3. Slaat op in `state.json` → injury_signals
4. Haalt huidige weekevents op uit intervals.icu
5. Bepaalt welke aanpassingen nodig zijn:
   - Kniepijn → verwijder alle intensiteitsessies deze week, voeg extra rust toe
   - Sessie gemist → herberekend TSS-tekort, vul op met lichte sessie indien verantwoord
   - Te zwaar gedaan → komende 2 dagen automatisch verzacht
6. Verwijdert/wijzigt events via intervals.icu API
7. Print duidelijke uitleg van de wijzigingen

---

## State (`state.json`)

Persisterend geheugen van het systeem. Wordt bijgehouden door alle scripts.

```json
{
    "last_updated": "2026-03-15",
    "athlete_id": "i85836",
    "race_date": "2026-06-16",
    "race_goal": "sub 40 min 10km",

    "current_phase": "basis_I",
    "week_number": 1,

    "injury": {
        "active_signals": [],
        "last_signal_date": null,
        "days_symptom_free": 0,
        "run_intensity_unlocked": false,
        "strides_unlocked": false,
        "tempo_unlocked": false,
        "history": []
    },

    "load": {
        "ctl_estimate": 45.0,
        "atl_estimate": 48.0,
        "tsb_estimate": -3.0,
        "last_calculated": "2026-03-15",
        "weekly_tss_target": 380
    },

    "weekly_log": [
        {
            "week": 1,
            "planned_tss": 380,
            "actual_tss": null,
            "notes": ""
        }
    ]
}
```

---

## intervals_client.py — Uitbreidingen nodig

Huidige functies: `get_athlete`, `get_activities`, `get_wellness`, `get_events`, `create_event`

**Toe te voegen:**
```python
def update_event(event_id: str, **kwargs) -> dict:
    """Wijzig een bestaand event (naam, beschrijving, load_target, etc.)"""

def delete_event(event_id: str) -> None:
    """Verwijder een event uit de kalender"""

def get_wellness_today() -> dict:
    """Haal wellness data van vandaag op"""

def bulk_delete_events(start: date, end: date, category: str = "WORKOUT") -> int:
    """Verwijder alle workout-events in een periode (voor herplanning). Geeft aantal terug."""
```

---

## Implementatievolgorde

### Stap 1 — intervals_client.py uitbreiden
- `update_event`, `delete_event`, `bulk_delete_events`, `get_wellness_today`
- Test met echte API

### Stap 2 — state.json aanmaken
- Initialiseer met startwaarden (huidig CTL schatten op basis van activiteiten)

### Stap 3 — agents/injury_guard.py
- Stoplicht logica, leest state.json
- Test: geef injury-signaal → verwacht ROOD output

### Stap 4 — agents/load_manager.py
- CTL/ATL/TSB berekening op basis van echte activiteitendata
- Test: print huidige CTL/ATL/TSB

### Stap 5 — agents/endurance_coach.py
- Sessie-templates per fase
- Test: genereer sessies voor week 1

### Stap 6 — agents/bike_coach.py
- Sweetspot sessies
- Test: genereer 2 fietssessies

### Stap 7 — agents/week_planner.py
- Combineert alles, schrijft naar intervals.icu
- **DRY RUN eerst** (print zonder schrijven) voor review

### Stap 8 — plan_week.py
- Orchestrator die alles aanroept
- Vraagt bevestiging voor het schrijven naar intervals.icu

### Stap 9 — adjust.py
- Feedback parser
- Claude API integratie voor interpretatie
- Event-aanpassingen in intervals.icu

### Stap 10 — Testen & kalibreren
- Draaien, bekijken wat intervals.icu toont
- Finetunen op basis van jouw werkelijke data

---

## Technische keuzes

- **Python 3**, geen async (sequentieel volstaat)
- **Claude API** voor `adjust.py` feedback-interpretatie (Haiku = goedkoop)
- **Rule-based** voor de planning-agents (geen Claude API nodig = gratis draaien)
- **Geen database** — `state.json` + intervals.icu is de bron van waarheid
- **Dry-run modus** in `plan_week.py` (voorkomt per ongeluk inplannen)
- **Confirmatie prompt** voor schrijven naar intervals.icu
