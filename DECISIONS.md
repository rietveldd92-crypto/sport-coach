# Sport Coach — Design Decisions

Dit document legt vast welke keuzes er gemaakt zijn en waarom. Bedoeld
voor de atleet (Dennis) om terug te lezen en voor toekomstige Claude-
sessies om context op te halen zonder dezelfde discussie opnieuw te
voeren.

---

## 2026-07-06 - Planner-contract: triatleet zonder zwemmen

**Beslissing:** Beschikbaarheid is een hard contract. Als een week geen
beschikbaarheidsvensters heeft (geen override, geen weekpatroon, geen vorige
week om eerlijk te kopieren), plant de app niets en toont hij een duidelijke
melding. De planner verzint nooit meer standaard 60 minuten per dag.

**Te weinig beschikbaarheid:** De solver plant wat past en laat de rest
zichtbaar vervallen. De bestaande `DROP_COST`-prioriteit bewaakt de volgorde:
vulling sneuvelt eerst, daarna kracht/hard, en lange duurloop als laatste.

**Prikkeldichtheid:** Runs blijven begrensd: maximaal 1 run per dag, standaard
niet back-to-back, en harde sessies krijgen minimaal 1 dag afstand waar de week
dat toelaat. Daarbovenop geldt een harde cap van maximaal 2 sessies per dag,
instelbaar via `preferences.max_sessions_per_day`.

**Weekstructuur:** De sleutelweek blijft: 1 korte intervalprikkel, 1 langere
interval/cruise-prikkel en 1 lange duurloop. De rest is vulling en krijgt via
`agents/adherence.py` het juiste optioneel/verplicht-gewicht; 80-90%
consistentie blijft belangrijker dan alles afvinken.

**Implementatie-context:** De trainingsfilosofie komt uit `PLAN.md`
Trainingsfilosofie (Hartensveld 80/20), de vier pijlers uit
`agents/pijlers.py`, en fiets als aerobe crosstraining uit
`agents/bike_coach.py` (`BIKE_CROSS_NOTE`, Delahaije).

---

## 2026-06-11 — Planner v2: CP-SAT slot-solver (OR-Tools)

**Beslissing:** Sessie-plaatsing is een exact optimalisatieprobleem
geworden: `core/slot_solver.py` met OR-Tools CP-SAT, in plaats van de
greedy `day_planner`-plaatsing + de fragiele
`_try_shift_before_replan()`-keten.

**Waarom:** De zoekruimte is klein (≤ ~15 slots × ≤ 9 sessies), dus exact
oplossen is triviaal goedkoop. Hard constraints (slotduur, max 1 long,
indoor-context, locked, injury-gates) zijn declaratief; zachte voorkeuren
zijn gewogen kostentermen. De **verplaatsingspenalty** t.o.v. het
bestaande plan is de kern: bij een beschikbaarheidswijziging wint
minimale verschuiving vanzelf — geen aparte shift/reschedule-logica meer
(`shift_day.py`, `reschedule.py` vervallen). Solver-redenen gaan als
`solver_notes` mee naar de UI, dus elke plaatsing is uitlegbaar.

---

## 2026-06-11 — Goal-engine: parametrische periodisering

**Beslissing:** De hardcoded marathon-tabellen
(`agents/marathon_periodizer.py`) zijn vervangen door
`core/periodization_generator.py`: doel (type/datum/streeftijd) +
atleetprofiel (CTL, recent volume uit intervals.icu) → `plan_weeks`-rijen.

**Waarom:** Eén generator dekt marathon t/m gran fondo en FTP-blokken
(doeltype-profielen zijn data, geen if-bomen) en maakt wekelijkse
herijking mogelijk: buiten de ±10%-band wordt het plan **vanaf volgende
week** opnieuw gegenereerd, het verleden blijft staan ("doel heilig,
route flexibel"). Regressiegarantie: een snapshot-test die het oude
Amsterdam-plan ±10% reproduceert was de gate vóór het verwijderen van de
tabellen. Haalbaarheid wordt geprojecteerd (max ~5 CTL/maand) en als
advies getoond in plaats van stiekem geforceerd.

---

## 2026-06-11 — Frontend: React PWA (vervangt Streamlit-besluit van 2026-04-09)

**Beslissing:** De UI is een React PWA (`web/`: Vite + TypeScript +
Tailwind + TanStack Query + dnd-kit + Recharts) met vier tabs:
Today · Week · Season · Jij. De Streamlit-app is gearchiveerd in
`legacy_streamlit/` (bevroren).

**Waarom nu wel migreren:** Het Streamlit-besluit was expliciet
"acceptabel tempo, niet elegant" — maar drag-to-reschedule, bottom-sheets,
de goal wizard en een installeerbare app op de telefoon kunnen niet op
Join-niveau in Streamlit. De agents waren inmiddels pure functies (Fase
0), dus de migratie raakte alleen de presentatielaag. Risico beheerst
door volgorde: algoritmes eerst valideren in de oude UI (Fase 1–2), dán
pas frontend (Fase 4–5). Design tokens (terracotta, Fraunces/Inter/
JetBrains Mono, dark-first) zijn 1-op-1 uit `ui_components.py`
overgenomen. Season/Jij worden lazy geladen zodat Today licht blijft.

---

## 2026-06-11 — API-laag: FastAPI over de core, dun gehouden

**Beslissing:** Eén FastAPI-app (`api/`) met routers per domein
(UPGRADE_PLAN §7). Routers doen alleen Pydantic-validatie; alle
samenstelling zit in `core/views.py`. Single-user bearer-token uit env
(`API_TOKEN`), APScheduler in hetzelfde proces (auto_feedback + zondagse
herijking), Gemini-coachfeedback via SSE. intervals.icu-fouten worden
één exception (`IntervalsUnavailable` → 502), zodat de PWA offline
nette fallbacks toont. Deploy: multi-stage Dockerfile; uvicorn serveert
ook `web/dist` met SPA-fallback, dus API + app op één domein en de PWA
service worker werkt zonder CORS-gedoe.

---

## 2026-04-09 — Platformkeuze: Streamlit behouden

**Beslissing:** Streamlit blijft het frontend-platform. Geen migratie
naar Next.js + FastAPI.

**Context:**
De redesign-prompt vraagt om een Runna/JOIN-achtige look: mobile-first,
editorial typografie, warme coach-toon, dark mode, custom animaties.
Streamlit's default widgets kunnen dat niveau niet leveren zonder
agressieve `st.markdown(unsafe_allow_html=True)` + custom CSS. Alternatief
is migratie naar een echte web-stack, maar dat kost 6-10 weken parttime
en legt de huidige werkende app lam.

**Trade-offs:**
- ✅ Bestaande business logic (intervals.icu, TP sync, Gemini feedback,
  workout library, state.json, scheduler) blijft intact. De atleet
  traint voor Amsterdam Marathon op 2026-10-18 — we kunnen ons geen
  6-week stilstand permitteren.
- ✅ Streamlit Community Cloud is gratis, auto-deploy uit Git, secrets
  ingebakken. Geen infra-beheer.
- ✅ Een custom CSS-laag + eigen layout helpers (`coach_card`,
  `today_hero`, `day_card`) kan de visuele kwaliteit dicht bij Runna/
  JOIN brengen — niet helemaal, wel "echt product" level.
- ⚠️ Streamlit's rerun-model vecht met complexe state (session_state
  keys, race conditions bij knop-clicks). Daar loggen we tegen aan via
  `pending_key` guards en zorgvuldige cache-invalidation. Acceptabel
  tempo, niet elegant.
- ⚠️ Animaties en complexe interacties (drag-to-reschedule, swipe-
  gestures) zijn beperkt. We accepteren dat visuele subtiliteit het
  moet winnen van micro-interacties.
- ⚠️ Geen native mobile app. Streamlit op mobiel = PWA via browser.
  Voor de atleet die vooral op desktop plant en op z'n horloge traint
  is dat prima. Een PWA-install prompt kan later.

**Wat dit betekent voor de redesign:**
- `ui_components.py` module met layout helpers (zie Fase 0)
- Globale CSS-injectie via `inject_global_css()` aan het begin van elke
  render (Fase 1)
- Custom dark palette, Google Fonts, mobile-first breakpoints
- Streamlit's default widgets alleen nog voor inputs waar geen goede
  HTML-vervanger is

---

## 2026-04-09 — Persistence: SQLite `history.db`

**Beslissing:** SQLite database `history.db` voor alles wat state.json
niet goed bewaart: wellness history, workout status (synced/swapped),
TP sync state, weekly summaries, morning check-ins.

**Waarom niet Postgres/externe DB:**
- Single-user app. Geen concurrency needs.
- Streamlit Community Cloud heeft persistente filesystem per app.
- SQLite is zero-config, zero-cost, in stdlib.
- Backups = git commit van de .db file is genoeg voor deze use case.

**Waarom niet blijven bij state.json:**
- state.json is een snapshot, geen historie. We willen trendlijnes
  kunnen tekenen (ROADMAP 3.1 CTL curve).
- JSON append voor wellness/workouts wordt onhandelbaar bij groei.
- TP sync state per workout (last_sync_hash, pending_actions) past
  beter in een relationele tabel.

**Schema v1 (migratie 001):**
```sql
CREATE TABLE wellness_daily (
    date TEXT PRIMARY KEY,  -- ISO yyyy-mm-dd
    sleep_score INTEGER,
    energy INTEGER,
    soreness INTEGER,
    motivation INTEGER,
    hrv REAL,
    resting_hr INTEGER,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE workout_tp_sync (
    event_id TEXT PRIMARY KEY,          -- intervals.icu event id
    tp_workout_id TEXT,
    last_sync_hash TEXT,                -- hash van de workout_doc bij sync
    last_synced_at TEXT,
    synced_event_name TEXT              -- naam ten tijde van sync (voor swap-detect)
);

CREATE TABLE weekly_summary (
    week_start TEXT PRIMARY KEY,        -- maandag ISO
    planned_tss REAL,
    actual_tss REAL,
    sessions_planned INTEGER,
    sessions_done INTEGER,
    phase TEXT,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT DEFAULT (datetime('now'))
);
```

**Hoe migraties worden toegepast:**
- `history_db.py` module met `ensure_migrations()` functie
- Aan het begin van elke app-run: check `schema_migrations`, run
  pending migrations idempotent
- Migraties zijn simpelweg Python functies geregistreerd in een list
- Niet Alembic — te zwaar voor deze schaal

---

## 2026-04-09 — TP Sync constraints + swap propagatie

**Beslissing:** Sync-knop is alleen zichtbaar voor workouts van
**vandaag of morgen** in Europe/Amsterdam lokale tijd. Swap-propagatie
gebeurt automatisch bij swap, niet bij next-click.

**Waarom "vandaag of morgen":**
- De atleet gebruikt TP primair als Zwift-target. Zwift-workouts
  worden op de dag zelf geladen; het heeft geen zin om workouts van
  over drie dagen te syncen (die veranderen nog).
- "Morgen" is meegegeven omdat de atleet 's avonds de workout voor de
  volgende ochtend al wil klaarzetten.
- Gister is weg omdat je die niet meer kunt rijden. Vorige week
  helemaal niet.

**Swap-propagatie trigger:**
De trigger is **"er is een swap gebeurd terwijl deze workout al gesynced
was"**, ongeacht of de sync-knop op dat moment zichtbaar is.

Concreet scenario: jij syncte gisteravond de workout van vanochtend
naar Zwift. Vanochtend voel je je slap, opent de app, de sync-knop is
al weg (want gesynced). Je klikt "Wissel → Makkelijker" en kiest een
Z2 rit. Omdat de oude al in TP/Zwift staat, moet de propagatie
automatisch de oude deleten en de nieuwe pushen. Anders staat er in
Zwift nog de oude threshold waar jij al uren geleden nee tegen zei.

**Implementatie:**
- `workout_tp_sync` tabel bewaart `synced_event_name` en `last_sync_hash`
- Bij elke swap in `perform_instant_swap()`: check deze tabel
- Als event_id erin staat en `synced_event_name != huidige_naam`: trigger
  `propagate_swap()` die delete+post doet
- Fout bij delete → log, markeer als stale, toon coach-toelichting
- Fout bij post na geslaagde delete → idempotente retry met exponential
  backoff, laat niet de atleet met een lege plek

**Wat we NIET bouwen (out of scope voor deze sessie):**
- Offline queue met `pending_tp_actions` tabel. Streamlit Cloud is
  altijd online; de atleet gebruikt de app alleen met WiFi. We
  registreren fouten in de flash en laten manual retry aan de atleet.
  Als dit in productie blijkt te vaak misgaan, bouwen we queue-retry
  alsnog.
- Conflict-detectie bij handmatige TP-wijziging door atleet. De
  aanname is: als je lokaal swap, wil je de nieuwe versie in TP.
  Geen confirm-dialog die de flow breekt. Als dit verkeerd blijkt,
  hergebruiken we `last_sync_hash` voor een "TP is afwijkend, toch
  overschrijven?" check.

---

## 2026-04-09 — Fasering: stap voor stap, niet big bang

**Beslissing:** De redesign-prompt beschrijft 21-34 uur werk verspreid
over 5 fases. Die doe ik **niet** in één Claude-sessie. Elke sessie
levert een werkend artefact op dat de atleet kan gebruiken.

**Volgorde:**
1. Sessie 1 (nu): **Fase 0 (foundation) + Fase 3 (TP sync sidequest)**
   - Fase 0 is klein en fundament voor alles daarna
   - Fase 3 is geïsoleerd, eigen module, eigen tests, minimaal
     impact op andere features — kan parallel aan design-werk
   - Fase 3 lost ook een concrete bug op (sync knop op verkeerde
     dagen)
2. Sessie 2: Fase 1 (design system live op homepage)
3. Sessie 3: Fase 2 (today-first + morning check-in + human language)
4. Sessie 4: Fase 4 (scheduler + availability + reschedule)
5. Sessie 5: Fase 5 (polish over de hele app)

**Waarom niet Fase 1 in dezelfde sessie als Fase 0:**
Design system is diep werk. Ik wil Dennis' feedback op Fase 0 + kleur/
font-keuzes zien vóór ik de hele visuele taal vastleg. Eerst het plat,
daarna het mooi.

---

## Nog openstaande beslissingen (te nemen in komende sessies)

- **Exacte kleurkeuze:** ember `#E56A3E` vs terracotta `#C4603C`.
  Wacht op visuele mock-up in sessie 2.
- **Serif keuze:** Fraunces vs Söhne vs Inter tight. Hangt af van
  hoe het voelt op het scherm — eerst Fraunces proberen, die is
  karaktervol en leesbaar op mobile.
- **Morning check-in prompt-timing:** altijd bij openen, of alleen
  's ochtends tussen 6-10 uur? Nadia's voorkeur: alleen 's ochtends,
  zodat het niet een klus wordt elke keer als je de app opent.
- **History.db backup-strategie:** Streamlit Cloud filesystem is
  persistent maar niet gegarandeerd. Optioneel een nightly GitHub
  Action die de db als artifact uploadt.

---

*Dit bestand is levend. Nieuwe beslissingen komen bovenaan.*
