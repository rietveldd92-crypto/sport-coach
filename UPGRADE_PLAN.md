# UPGRADE_PLAN — Sport Coach v2

> Doel: van "wonky maar slim" naar een strakke, Join-achtige adaptieve trainingsapp.
> USP blijft: Delahaije-logica + flexibiliteit + intervals.icu als backend-of-record.
>
> Richtingkeuzes (vastgelegd 2026-06-11):
> 1. Frontend migreert naar **React PWA + FastAPI** (agents blijven Python)
> 2. Goal-engine wordt **multi-sport** (run, bike, duatlon/triatlon)
> 3. Beschikbaarheid wordt **tijdvensters + weekpatronen**
> 4. intervals.icu blijft single source of truth voor events & activities

---

## 1. Visie

Drie pijlers, in volgorde van waarde:

1. **Slim inplannen** — de planner kent je echte agenda (tijdvensters, patronen) en plaatst sessies in concrete slots. Bij wijziging schuift hij minimaal, niet alles opnieuw. Dit vervangt de fragiele `_try_shift_before_replan()`-keten in `app.py`.
2. **Trainen naar een doel** — een instelbaar doel (race + streeftijd, of FTP-doel) genereert parametrisch een Delahaije-blokperiodisering. De hardcoded tabellen in `agents/marathon_periodizer.py` worden een generator. Wekelijks herijken op werkelijke CTL/volume: *doel heilig, route flexibel*.
3. **Join-niveau UX** — today-first, kaarten, drag-to-reschedule, vloeiend. Niet haalbaar in Streamlit; wel in een React PWA. Les uit Join-reviews: hun adaptiviteit wordt geprezen, hun navigatie verguisd → wij houden max 4 hoofdschermen.

**Wat blijft:** agents-architectuur, workout_library (300+ templates), injury_guard, load_manager, feedback_engine, intervals_client, TP-sync. Dit is het solide deel.

**Wat vervalt:** Streamlit UI (na pariteit), `state.json` (→ SQLite), hardcoded periodisatietabellen, greedy day_planner-plaatsing.

---

## 2. Doelarchitectuur

```
┌─────────────────────────────────────────────┐
│  React PWA (Vite + TS + Tailwind)           │
│  Today · Week · Season · Settings           │
└──────────────────┬──────────────────────────┘
                   │ REST/JSON (+ SSE voor coach-feedback)
┌──────────────────▼──────────────────────────┐
│  FastAPI (api/)                             │
│  routers: plan, goals, availability,        │
│  checkin, trends, sync                      │
└──────────────────┬──────────────────────────┘
┌──────────────────▼──────────────────────────┐
│  Core (bestaande agents/, geherstructureerd)│
│  goal_engine · periodization_generator ·    │
│  session_generator (endurance/bike_coach) · │
│  slot_solver (nieuw) · injury_guard ·       │
│  load_manager · feedback_engine             │
└────────┬───────────────────┬────────────────┘
   SQLite (history.db,       intervals.icu API
   uitgebreid schema)        (events = waarheid)
```

Principes:

- **Agents worden pure functies/services.** Geen `st.session_state`, geen prints; input → output + Pydantic-modellen. De FastAPI-laag is dun.
- **SQLite wordt de enige lokale store.** `state.json` migreert naar tabellen (zie §3). `history_db.py`'s idempotente migratiesysteem hergebruiken.
- **intervals.icu blijft event-waarheid.** Wij bewaren plan-metadata (slot, goal-link, solver-redenen) lokaal, gekoppeld via event_id.
- **Deployment:** FastAPI + static build in één container (Docker, bestaat al via .devcontainer); Streamlit Cloud vervalt op termijn. PWA installeerbaar op telefoon.

---

## 3. Datamodel (nieuw/gewijzigd)

```sql
-- Doelen
CREATE TABLE goals (
  id INTEGER PRIMARY KEY,
  type TEXT NOT NULL,            -- marathon|half|10k|5k|gran_fondo|ftp|triathlon|custom
  sport TEXT NOT NULL,           -- run|ride|multi
  event_date TEXT NOT NULL,
  target_value TEXT,             -- "2:59:00" | "310W" | NULL
  priority TEXT DEFAULT 'A',     -- A|B|C  (B/C = tussendoel, mini-taper)
  status TEXT DEFAULT 'active',  -- active|completed|abandoned
  created_at TEXT
);

-- Gegenereerd macroplan (1 rij per week per actief A-doel)
CREATE TABLE plan_weeks (
  goal_id INTEGER REFERENCES goals(id),
  week_start TEXT,
  phase TEXT,                    -- accumulatie_1|transformatie_1|...|realisatie
  is_deload INTEGER,
  tss_target_min INTEGER, tss_target_max INTEGER,
  run_km REAL, run_sessions INTEGER, long_run_km REAL,
  bike_sessions INTEGER,
  intensity_gate TEXT,           -- geen|strides|tempoduur|drempel|race_specifiek
  generated_at TEXT,             -- her-generatie overschrijft toekomst, nooit verleden
  PRIMARY KEY (goal_id, week_start)
);

-- Beschikbaarheid: terugkerend weekpatroon
CREATE TABLE availability_pattern (
  weekday INTEGER,               -- 0=ma .. 6=zo
  slot_start TEXT, slot_end TEXT,-- "06:00","07:30"
  context TEXT DEFAULT 'any',    -- any|indoor_only|outdoor_only
  PRIMARY KEY (weekday, slot_start)
);

-- Overrides per datum (vervangt het hele patroon voor die dag)
CREATE TABLE availability_override (
  date TEXT, slot_start TEXT, slot_end TEXT,
  context TEXT DEFAULT 'any',
  PRIMARY KEY (date, slot_start)
);                               -- 0 rijen voor een datum + marker = rustdag

-- Plaatsing: koppelt intervals.icu events aan slots + solver-uitleg
CREATE TABLE placements (
  event_id TEXT PRIMARY KEY,     -- intervals.icu event id
  date TEXT, slot_start TEXT,
  session_kind TEXT,             -- long|hard|easy|strength|rehab
  locked INTEGER DEFAULT 0,      -- user heeft handmatig vastgezet
  solver_score REAL, solver_notes TEXT,
  goal_id INTEGER
);

-- Athlete state (vervangt state.json secties injury/load/progression/build_deload)
CREATE TABLE athlete_state (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT);
```

Migratie: eenmalig script `scripts/migrate_state_json.py` (state.json → tabellen), daarna `shared.load_state()` herimplementeren als DB-reads zodat alle agents ongewijzigd blijven werken tijdens de overgang.

---

## 4. Goal-engine & parametrische periodisatie

### 4.1 Van tabel naar generator

`agents/marathon_periodizer.py` bevat nu hardcoded `RUN_PROGRESSION_TABLE`, `WEEKLY_TSS_TABLE`, `PHASES` voor exact één marathon. Nieuw: `core/periodization_generator.py`.

**Input:** doel (type, datum, streeftijd), atleetprofiel (huidige CTL, recente 6-weeks run-km en sessiefrequentie uit intervals.icu activities, FTP, HRmax, blessurestatus), aantal beschikbare weken.

**Output:** lijst `PlanWeek`-objecten (zie schema) — zelfde contract als de huidige tabellen, dus `load_manager`, `endurance_coach` en `bike_coach` blijven compatibel.

**Algoritme (Issurin-blokken, Delahaije-invulling):**

1. **Blokverdeling.** Weken-tot-doel verdelen over fasen volgens vaste ratio's, geschaald naar horizon:
   - ≥20 wk: Acc-I 25% · Acc-II 25% · Trans-I 15% · Acc-III 14% · Trans-II 11% · Realisatie 10% (≈ de huidige 28-weeks verdeling)
   - 12–19 wk: Acc 40% · Trans-I 25% · Acc-II 15% · Trans-II 12% · Realisatie 8%
   - <12 wk: Acc 45% · Trans 35% · Realisatie 20% + warning "korte aanloop, doel mogelijk niet haalbaar"
2. **Volumecurve.** Startvolume = recent gemiddelde (uit activities); piekvolume = f(doeltype, streeftijd): marathon sub-3 → ~58 run-km + 4-5 sessies; 10k → ~45 km; gran fondo → TSS-gedreven i.p.v. km. Interpolatie met bestaande consistency rules uit `load_manager.enforce_consistency_rules()` (max +15%/+20% groei, long ≤35%, 4e-run-trigger). Deload elke 4e week (3:1), in Trans-blokken 2:1.
3. **Intensiteits-gating per fase** — bestaande logica (`get_run_intensiteit_gating`) wordt fase-gedreven i.p.v. weeknummer-gedreven.
4. **CTL-doelpad.** Doel-CTL op racedag per doeltype (marathon sub-3: 75–85; gran fondo: 70+; FTP-blok: +5–8 punten). TSS-weektargets afgeleid van benodigde CTL-ramp (max ~5 CTL/maand stijging).
5. **Sport-mix.** Per doeltype een mixprofiel: marathon = run-primair + bike-ondersteunend (huidige model); gran fondo = omgekeerd; duatlon = 50/50 met brick-sessies. Mix stuurt welke coach hoeveel sessies levert.
6. **B/C-doelen.** Tussenraces krijgen een 5–7-daagse mini-taper + 3-daagse recovery, lokaal in het macroplan gestanst zonder de blokstructuur te breken.

### 4.2 Rolling re-periodisatie (wekelijks)

Elke zondagavond (of on-demand "Herbereken plan"):

1. Werkelijke CTL + uitgevoerd volume ophalen (bestaat: `load_manager.analyze()`).
2. Afwijking t.o.v. `plan_weeks` bepalen. Binnen ±10%: niets doen. Daarbuiten: generator opnieuw draaien **vanaf volgende week** met huidige werkelijkheid als startpunt; verleden blijft staan.
3. Haalbaarheidscheck: projecteer CTL op racedag; als doel-CTL onhaalbaar → advies in UI ("streeftijd 3:05 realistischer") i.p.v. stiekem forceren. Injury_guard YELLOW/RED drukt automatisch het gegenereerde pad (bestaande gating blijft de poortwachter).

### 4.3 Goal wizard (UI-flow)

Doel kiezen (type + datum + streeftijd) → app toont automatisch: opgehaalde startsituatie, voorgestelde blokken op een tijdlijn, piekweek, haalbaarheidsoordeel → bevestigen → macroplan in `plan_weeks`, eerste week wordt direct gepland.

---

## 5. Slimme planner v2 (slot-solver)

### 5.1 Probleemdefinitie

Per week: n sessies (uit endurance/bike_coach, 4–9 stuks incl. kracht) toewijzen aan beschikbaarheidsslots (uit patroon + overrides). Zoekruimte is klein (≤ ~15 slots × ≤9 sessies) → **exacte optimalisatie is haalbaar**. Implementatie: `core/slot_solver.py` met OR-Tools CP-SAT (pip, pure Python-binding) of branch-and-bound zelfbouw; CP-SAT aanbevolen (declaratief, bewezen, triviaal klein probleem).

### 5.2 Constraints

Hard (huidige Tier 1, wordt CP-SAT constraint):

- Sessieduur ≤ slotduur (+10 min tolerantie voor long)
- Max 1 long per dag; runs niet back-to-back (toggle blijft)
- Indoor-only slots krijgen alleen VirtualRide/kracht
- `locked` placements zijn onaantastbaar
- Injury-gates (YELLOW: geen loopintensiteit, etc.)

Zacht (huidige T2/T3, wordt gewogen kostenterm):

| Term | Gewicht (init) |
|---|---|
| Hard-hard of hard-voor-long op aangrenzende dagen | 50 |
| Long niet op ruimste slot van de week | 30 |
| Long runs op aangrenzende dagen | 20 |
| Brick (run+bike) op dezelfde dag wanneer vermijdbaar | 15 |
| Kracht op dag vóór long/hard | 15 |
| Sessie in slot met <15 min marge | 10 |
| **Verplaatsing t.o.v. bestaand plan (per sessie, per dag verschoven)** | **25** |
| Ochtendslot voor long (voorkeur) | 5 |

De **verplaatsingsterm is de kern van de fix**: bij een beschikbaarheidswijziging draait dezelfde solver opnieuw over de hele week, met het huidige plan als referentie. Minimale verschuiving wint vanzelf; geen aparte shift-logica meer. `agents/shift_day.py`, `reschedule.py` en `_try_shift_before_replan()` vervallen.

### 5.3 Output & uitleg

Solver levert per sessie: datum + starttijd (slot_start) + score + leesbare redenen ("Long op zaterdag: ruimste venster, 2 dagen na drempel"). Starttijd gaat mee in `start_date_local` naar intervals.icu (nu altijd middernacht/dagniveau). Redenen naar `placements.solver_notes` → tooltip in UI. Geen oplossing binnen hard constraints → beste relaxatie tonen + welke sessie sneuvelt (volume_compensation pakt het op, bestaat al).

### 5.4 Tests

`tests/test_slot_solver.py`: alle bestaande tier-cases uit `test_day_planner.py` porten + nieuwe cases: minimale-verschuiving (1 dag wijzigt → max 1 sessie verhuist), locked respecteren, indoor-context, onoplosbare week. Property-based test (hypothesis): output schendt nooit hard constraints.

---

## 6. UI-spec (Join-stijl, React PWA)

Stack: Vite + React + TypeScript, Tailwind, TanStack Query, dnd-kit (drag), Recharts. Design tokens uit `ui_components.py` overnemen: bg `#0E0F12`, accent terracotta `#C4603C`, Fraunces/Inter/JetBrains Mono, dark-first. Max 4 tabs onderin (les van Join): **Today · Week · Season · Jij**.

**Today** — heroka­art met workout van vandaag (naam, duur, TSS, zones, starttijd uit slot), coach-note, knoppen: Done-check, Swap (vergelijkbaar/makkelijker/harder — bestaande categorieën), Sync→Zwift. Ochtend-checkin als bottom-sheet (sliders slaap/energie/soreness/motivatie + blessuresignalen — dit lost het "CLI-only injury logging"-probleem op). Onder de kaart: morgen-preview.

**Week** — verticale dagenlijst met sessiekaarten in hun slot. Drag-to-reschedule: drop op andere dag → solver-call met die sessie als locked op de nieuwe dag → diff-preview ("Drempel schuift naar do") → bevestig. Beschikbaarheid per dag inline aanpasbaar (vensters slepen); wijziging triggert solver met verplaatsingspenalty.

**Season** — horizontale bloktijdlijn (fasen als gekleurde segmenten, deloads gemarkeerd, B-races als vlaggetjes), countdown naar doel, CTL-werkelijk vs. CTL-doelpad als één grafiek, haalbaarheidsbadge. Hier woont ook de goal wizard.

**Jij** — trends (CTL/TSB, weekvolume, HRV — bestaande Altair-charts herbouwen in Recharts), injury-guard status met signaalhistorie (maakt de buffer transparant), instellingen (weekpatroon-editor: 7 dagen × tijdvensters, FTP/HRmax, TP-koppeling).

PWA: installeerbaar, offline cache van vandaag+morgen, push-notificatie voor ochtend-checkin (later).

---

## 7. API-laag (FastAPI)

```
GET  /api/today                 # workout + checkin-status + coach note
GET  /api/week/{week_start}     # placements + events + availability
POST /api/week/{week_start}/plan        # (her)plan week via solver
POST /api/placements/{event_id}/move    # drag → locked solve → diff
POST /api/placements/{event_id}/swap    # workout swap (categorie)
GET/PUT /api/availability/pattern
GET/PUT /api/availability/override/{date}
GET/POST /api/goals             # + DELETE; POST genereert macroplan
POST /api/goals/{id}/regenerate # rolling re-periodisatie
GET  /api/season                # plan_weeks + ctl-pad + haalbaarheid
POST /api/checkin               # wellness + blessuresignalen → injury_guard
GET  /api/trends                # ctl/atl/tsb, volume, hrv series
POST /api/sync/tp/{event_id}    # bestaande tp_sync_service
GET  /api/coach/feedback (SSE)  # streaming Gemini-feedback
```

Single-user: simpele bearer-token uit env. Achtergrondtaken (auto_feedback, zondagse re-periodisatie) via APScheduler in hetzelfde proces.

---

## 8. Fasering

Elke fase is af te ronden en levert direct waarde; de app blijft de hele tijd bruikbaar.

**Fase 0 — Fundament (≈1 week)**
state.json → SQLite (migratiescript + `shared.load_state()` op DB). Agents ontdoen van Streamlit-imports. TP-synclog naar history.db. *DoD: alle 22 testbestanden groen, Streamlit-app werkt ongewijzigd op DB.*

**Fase 1 — Planner v2 (≈2 weken)**
Availability-tabellen + slot_solver (CP-SAT) + placements. Integratie in bestaánde Streamlit-flow (achter feature flag `PLANNER_V2`), zodat het algoritme in de praktijk gevalideerd is vóór er frontend-werk gebeurt. `shift_day`/`reschedule`/`_try_shift_before_replan` verwijderen zodra flag default aan staat. *DoD: test_slot_solver groen incl. minimale-verschuiving-cases; één week echt gebruik zonder handmatige correcties.*

**Fase 2 — Goal-engine (≈2 weken)**
`goals` + `plan_weeks` + periodization_generator + rolling re-periodisatie. Marathon Amsterdam (18 okt 2026) als eerste echte goal invoeren; generator moet het huidige hardcoded plan ±10% reproduceren (snapshot-test — dit is de regressiegarantie). Daarna `marathon_periodizer.py`-tabellen verwijderen. *DoD: snapshot-test groen, gran-fondo- en 10k-profiel genereren plausibele plannen (handmatige review).*

**Fase 3 — API (≈1 week)**
FastAPI-routers over de core, OpenAPI-spec, APScheduler voor auto_feedback + zondagse herijking. *DoD: alle endpoints met integratietests (mock intervals.icu — dit wordt meteen de ontbrekende e2e-test).*

**Fase 4 — React PWA: Today + Week (≈3 weken)**
Vite-project `web/`, design tokens, Today-scherm + checkin, Week-scherm + drag-to-reschedule + availability-editor. Vanaf hier is dagelijks gebruik via PWA. *DoD: telefoon-installatie, checkin + swap + drag werken end-to-end tegen echte intervals.icu.*

**Fase 5 — Season + afronding (≈2 weken)**
Season-scherm + goal wizard + Jij-scherm (trends, injury-historie, patroon-editor). Streamlit-app archiveren. Dockerfile voor gecombineerde deploy. *DoD: alle dagelijkse en wekelijkse flows PWA-only; README/DECISIONS.md bijgewerkt.*

Totaal ≈ 11 weken doorlooptijd solo. Volgorde is bewust: algoritmes eerst (fase 1–2) valideren in de oude UI, dán pas de frontend — het risico zit in de planner, niet in React.

---

## 9. Risico's & mitigatie

| Risico | Mitigatie |
|---|---|
| Generator reproduceert huidig marathonplan niet | Snapshot-test in fase 2 is harde gate; tabellen pas verwijderen na groen |
| CP-SAT-gewichten voelen verkeerd | Gewichten in DB (athlete_state), tunebaar zonder deploy; solver_notes maken keuzes inspecteerbaar |
| Frontend-scope-creep | Fase 4 strikt Today+Week; al het andere is fase 5 |
| Twee UIs onderhouden tijdens overgang | Streamlit bevriezen na fase 1 (alleen bugfixes) |
| TP undocumented API breekt | Ongewijzigd risico; blijft feature-flagged, sync-log nu wel in SQLite |
| Eén persoon, 11 weken motivatie | Elke fase eindigt met iets dat je dagelijks merkt; fase 1 lost de grootste dagelijkse ergernis (replan-chaos) als eerste op |

---

## 10. Buiten scope (bewust)

Multi-user/auth, native apps (PWA volstaat), Google Calendar-koppeling (availability-model is er wel op voorbereid: overrides kunnen later uit GCal gevuld worden), trainingsplannen verkopen, Garmin/Wahoo directe push (intervals.icu doet dit al).
