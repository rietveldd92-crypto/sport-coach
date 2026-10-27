# Planlogica V4 — van marathon-Norwegian naar plafondblokken

Status: **besloten** (26 okt 2026), klaar voor bouw. Bouwt voort op PLANNER-V3-PLAN.md
(skeleton → day_assigner blijft de architectuur); dit plan verandert *wat* er in het
skelet komt, niet *hoe* het geplaatst wordt.

## 1. Waarom

De planner-code staat op commit `9b5641f` (16 aug): de marathon-Norwegian-lijn.
Sindsdien is de koers drie keer gedraaid en geen ervan zit in de code:

| Besluit | Datum | In code? |
|---|---|---|
| Na Amsterdam een half jaar 5-10k, VO2max lopend | 7 sep | nee |
| Blokopzet Norwegian singles + X-sessie, 3× kwaliteit uit drie verschillende systemen | 6 + 21 sep | nee |
| Om de dag lopen (4-3-4-3), kracht 2×/wk als vaste pijler | 21 okt | deels (kracht-placement bestaat, knie-gericht) |
| Sub-3 = Rotterdam april 2028; 10k-blokken t/m Leiden mei 2027, HM-anker nov/dec 2027 | 21 okt | nee |
| Amsterdam-diagnose: houdbaarheid → later aaneengesloten MP 14-18 km | 21 okt | nee (pas relevant 2028) |

Gevolg nu: blok 1 staat met de hand in intervals.icu (vergrendeld). Zodra de planner
weer een week vult, plant hij marathon-sub-drempel + MP-long runs met VO2 op de fiets —
precies wat we bewust hebben losgelaten. Het actieve A-doel in `goal_engine` is nog
Amsterdam 2026-10-18.

## 2. Huidige logica vs. besloten logica

| Onderdeel | Code nu | Besloten |
|---|---|---|
| A-doel | marathon 18-10-2026 | 10k Leiden eind mei 2027 (A); **eerste B-doel Bruggenloop 15 km 13 dec** (doel 62:00); verder Schoorl 10k 14 feb, CPC 5k 14 mrt, Rotterdam 10k ~11 apr (B); parkrun 14 nov = C (trainingsijkpunt) |
| Kwaliteit per gate | `QUALITY_TOOLKIT_BY_GATE` is doeltype-blind; `race_specifiek` → marathon + sub-drempel | toolkit per **doeltype × gate**; 10k/5k: VO2-run + sub-drempel + ASR/X |
| VO2max | op de fiets (Ronnestad), lopend alleen als swap | **lopend** in 5-10k-blokken ("pace vasthouden, duur rekken") |
| Snelheidsreserve (ASR) | bestaat niet | wekelijks: heuvelsprints 150-200 m of vliegers 100 m, zacht/lange warmup (heup) |
| Kwaliteitsslots | vast 2 (1 in deload) | 2 lopend + 1 fiets-sub-T; ASR telt niet als kwaliteitsslot (metabool goedkoop, <24 u herstel) |
| Max LT-loopdagen | 2 | blijft 2 (VO2 + sub-T); 3e drempelprikkel op de fiets |
| Long run | marathonspecifiek met MP-blokken zodra poort open | 75-90 min easy, roteert offroad/progressief/heuvelsprints; géén MP |
| Runs per week | 3 (+4e via `fourth_run_gate_open`) | 4-3-4-3, nooit twee dagen achtereen |
| Kracht | placement-regels, knie-tekst | 2×/wk vaste pijler, A (zwaar) / B (stabiliteit+pogo), heup-gericht, telt als zware dag |
| Pace-referentie | drempelpace (+ afgeleide MP) | drempelpace **én** 5k-pace als tweede anker (VO2/ASR-paces daarvan afleiden) |
| Race-ankers drempel | race-ankers + drift | idem, plus parkrun alleen tegen dezelfde parkrun (geen gemeten parcours) |
| Raceweken | bug: long run op za vóór zo-race, geen taper | race-dag = key session; dag ervoor easy/rust; mini-taper bij A/B-race |

## 3. Wijzigingen

**W1 — Doel omzetten.** Nieuw A-doel `10k` Leiden (datum tbc, placeholder 30-05-2027,
streeftijd 38:00 — bespreekbaar, zie §5). Eerste B-doel: **Bruggenloop 15 km, zo 13 dec 2026,
62:00, ondergrens = PR** — de planner behandelt die als blokafsluiter van blok 1 (mini-taper, race-anker voor
de drempel). 15 km-PR uit de data: **1:02:32 (4:10/km)**, 15 km-split van de halve van
Antwerpen 19-10-2025 op GPS-afstand (horloge mat 21,43 km = 1,6% te lang → op gemeten
afstand ~1:03:30). Beste van het afgelopen jaar: 1:03:42 (Rotterdam Half 20-09-2026).
Doel 62:00 verbetert beide; PR-grens is <1:02:32. Overige tussendoelen als B/C (parkrun 14 nov = C). Amsterdam op
`status=done`. Herplan via "Herbereken plan". Geen code, wel een migratiescript/
checklist zodat prod-DB en lokale DB gelijk lopen (prod ≠ lokaal, bekende valkuil).

**W2 — Toolkit per doeltype.** `QUALITY_TOOLKIT_BY_GATE` → `QUALITY_TOOLKIT[goal_type][gate]`.
- marathon: huidige mapping (ongewijzigd, voor 2028).
- half: sub-drempel + HM-pace-blokken.
- 10k/5k: `tempoduur` → (subthreshold, vo2_run); `drempel` → (vo2_run, subthreshold);
  `race_specifiek` → (race_pace, subthreshold).
`week_skeleton._quality_categories` krijgt het doeltype mee.

**W3 — Nieuwe run-categorieën in de library** (op `% drempel` én 5k-pace, 6 tredes):
- `vo2_run`: de spicy-reeks van blok 1 als ladder (12×400 → 8×400+4×200 → 2×(1000-600-400)
  → 6×800 → 5×1000 → 4×1200), varianten heuvelreps 75 s / 30-30 gras / tijd-reps.
  Progressieregel: pace vast, duur rekken; pas als de laatste trede schoon is, pace −2 s.
- `race_pace`: 10k-pace-blokken (3×3 km, 2×4 km) voor de laatste 3-4 weken vóór A/B-race.
- `asr` (X-sessie): 6-10× 150-200 m heuvel of 4-8× 100 m vliegers op gras; altijd als
  aanhangsel van de long run of easy run, nooit los.
Alles op **tijd** waar mogelijk (Dennis loopt niet op de baan). Afstanden in intervals.icu
als `0.4km`, nooit `400m` (= 400 minuten).

**W4 — Skelet: 4-3-4-3 en fiets-sub-T.** `fourth_run_gate_open` vervangen door
`run_pattern` (`[4,3]` alternerend, startweek configureerbaar). In een 10k/5k-doel
krijgt de fiets één vaste sub-T-sessie (3×10-12 @ 88-92% FTP) als derde drempelprikkel;
de bestaande filter "geen fiets-threshold bij 2 run-intervallen" maakt hiervoor een
uitzondering op `rol="bike_subt"`.

**W5 — Long run per doeltype.** 10k/5k: Z2 75-90 min, roteert (offroad, progressief
laatste 15 min naar drempel−10%, of met ASR-aanhangsel). Geen MP-blokken, voedt het
drempeldossier niet. Marathon-variant blijft voor 2028.

**W6 — Kracht als pijler.** `pijlers.py` krijgt een vijfde label of kracht hangt onder
fatigue resistance (keuze §5). Placement: 2×/wk, ≥48 u ertussen, niet op de dag vóór
VO2-run, wel na de long run of op een fietsdag. Tekst heup i.p.v. knie.

**W7 — Racewekenfix.** Week met een race: racedag wordt `key`, de dag ervoor rust/easy
30-45 min met strides; een race <15 km vervangt een kwaliteitssessie, ≥15 km ook de
long run (REN-37); weekdoel-TSS telt de race mee; taper volgens REN-32. Lost de bug van 13 sep op; daarna mag de planner raceweken weer vullen.

**W8 — 5k-pace als tweede anker.** `threshold_model` krijgt `vvo2_pace_sec` (uit 5k-race
of beste 5×1000) naast drempelpace; VO2/ASR-paces worden daaruit afgeleid i.p.v. uit
drempel × factor. Bijstelling alleen op gemeten wegwedstrijden; parkrun = trainingsijkpunt.

**W9 — Meerjarige doelketen.** Goal-engine ondersteunt al meerdere doelen; wat ontbreekt
is de keten (10k-blokken → zomerbasis → HM-blok → marathon 2028) als volgorde van A-doelen
met automatische doorschakeling na `done`. Laag prioriteit: kan tot juni 2027 handmatig.

## 4. Run with Ren — requirements en keuzes

Bron: 16 afleveringen De Loopschool, zelf getranscribeerd (Whisper, geen officiële
transcripties), plus App Store-notes en runwithren.com. Volledige lijst REN-01 t/m REN-40
met citaten/timestamps: `docs/ren-requirements.md`. [app] = aantoonbaar app-gedrag,
[visie] = coachingvisie van Butter/Hartensveld/Van den Berg.

### Overnemen

| REN | Wat | Waar bij ons |
|---|---|---|
| 01-03 [app] | **Drie los gekalibreerde ankers**: AeT, CS, vVO2max — geen zones als % van één drempel | W8 wordt drie ankers: AeT (= ons pace@145/LT1), drempel (≈ CS), vVO2 (6-min kalibratie). VO2/ASR-paces uit vVO2, easy uit AeT |
| 05 [app] | AeT bijstellen op HR:pace-decoupling >~5% tussen 1e en 2e helft | `aerobic_efficiency.py` meet dit al; nu ook als bijstelregel voor AeT-pace |
| 06 [app] | "Kalibratie" i.p.v. test; gemiddelde dag, geen carbon, gewone schoen; regelmatig herhalen | Past bij diagnose-i.p.v.-deadline. 6-min kalibratie aan begin en eind van elk 10k-blok |
| 16 [visie] | Range >1 op 10 trainingen niet gehaald zonder externe oorzaak → anker klopt niet | Nieuwe regel in `threshold_model` (naast drift + race-ankers) |
| 10 [app] | Na afloop: RPE + "hoeveel reps had je nog?" (reps in reserve) | Eén extra vraag in `workout_feel`; voedt drempeldossier |
| 18 [app] | Key sessions pas als je "eligible" bent | `race_pace` en langere VO2-tredes pas na schone vorige trede (bestaat deels via `quality_step`) |
| 23 [visie] | Overslaan > inhalen; intensief eerst plaatsen, easy eromheen | day_assigner doet het tweede al; `adapt_week` mag gemiste kwaliteit nooit inhalen |
| 25 [visie] | VO2max alleen trainen als marge CS→vVO2 klein is (<~10%) | Criterium voor het VO2-blok. Schatting Dennis: drempel ~4:06-4:16 vs 6-min-pace ~3:43-3:48 ≈ 8-11% → VO2-blok is terecht, maar herijken na kalibratie |
| 27 [app] | CTL en weekvolume zijn terugkijkmaten, geen doel; geen "+3 s per training" | CTL-doelpad in de generator degraderen tot ramp-bewaking (max +5/mnd); geen CTL-target meer in de UI |
| 28 [app] | Racevoorspelling als bandbreedte, bijgesteld op kalibraties en PR's | Backlog Fase 3.4 (race readiness) wordt een band, bv. Bruggenloop 61:30-63:00 |
| 32 [app+visie] | Taper: volume 70% → 50%, intensiteit en frequentie gelijk; raceweek wo/do kort blok | W7 racewekenfix gebruikt dit (marathon 2 wk, 10k/15k 1 wk) |
| 37 [visie] | Een wedstrijd vervangt de CS-sessie, niet de long run | W7: race <15 km vervangt een kwaliteitssessie; race ≥15 km (Bruggenloop) vervangt ook de long run |

### Hebben we al (bevestiging, niets doen)

12 (sub-drempelreps 3-5 s onder CS, 1-2 reps in reserve = onze sub-T op 95-97%) ·
15 (één doel per training = pijler-label) · 20 (beschikbaarheid = budget) ·
26 (vier pijlers + fatigue resistance) · 38 (eenvoud, doel van elke training zichtbaar) ·
40 (uitvoeringsscore = `adherence.py`; intervals.icu-sync).

### Bewust níet overnemen

| REN | Wat REN doet | Waarom wij niet |
|---|---|---|
| 21 [app] | Geen kalenderweken, plant op laatste training + beschikbaarheid | intervals.icu, week-lock en 4-3-4-3 werken op weken; winst te klein voor de herbouw |
| 33/34 [app] | Fiets niet plannen, en fiets altijd rustig | Fiets is bij Dennis bewust de 3e drempelprikkel en de VO2-ontlasting. Wél overnemen: fiets ná een zware run, nooit ervoor (klopt al met de 8-daagse cyclus) |
| 35 [app] | Strides niet in de app (niet programmeerbaar) | Wij beschrijven ze in tekst; ASR is juist een gat bij Dennis. Wél overnemen: strides de dag vóór kwaliteit, nooit de dag na zwaar |
| 36 [app] | Geen kracht in de app | Heup is het grootste risico van drie blokken intensiteit; kracht blijft pijler (W6) |
| 09 [app] | HR helemaal uit het voorschrift | Voorschrift wordt wel pace-range, maar HR blijft afbreekregel (HR ≤168 per rep, drift >5 bpm = klaar) — zie §5.2 |
| 30 [visie] | HRV alleen als trend | Al zo bij ons ([[feedback_mental_vs_physical_fatigue]]); niets veranderen |

### Later (na blok 2)

22 (per dag pinnen i.p.v. hele week vergrendelen — lost ook de scheduler-ellende structureler op) ·
31 (herstelfase na piekrace automatisch: 5 dagen niets, 2-3 wk ongestructureerd) ·
07 (backfill → profiel, relevant als de app ooit voor andere lopers is).

## 5. Keuzes — BESLOTEN 26 okt 2026 (Dennis akkoord op alle vier)

Samengevat: (1) VO2-ladder houden + 6-min kalibratie vóór/na elk blok; (2) pace-range
±5 s/km leidend, HR alleen afbreekregel; (3) geen CTL-doel meer: de planner vult nooit bij
om een getal te halen, CTL alleen als rem (waarschuwing bij >+5/mnd) en terugkijkmaat —
een CTL-daling naar ~50-55 in het 10k-blok is verwacht en geen achterstand; (4) Leiden als
band 38:00-38:45. Alle overnames/afwijzingen in §4 akkoord.

1. **VO2-dosering.** REN: microintervallen, ~6 min totaal op 6-min-pace per sessie. Onze
   blok-1-ladder zit op 12-20 min (12×400, 5×1000). Advies: ladder houden — het doel is
   een 10k, niet een marathon, en jouw gat is juist duur-op-snelheid — maar 6-min
   kalibratie vóór en na elk blok om te zien of het werkt.
2. **Voorschrift: pace-range of HR-cap leidend?** Advies: pace-range ±5 s/km in het
   voorschrift (REN-09), HR alleen als afbreekregel. Jouw HR-meting is twee keer
   onbetrouwbaar gebleken; pace niet.
3. **CTL loslaten als doel?** Advies: ja (REN-27). Alleen ramp-bewaking houden.
4. **Streeftijd A-doel Leiden:** 38:00 of een band 38:00-38:45? Advies: band, conform REN-28.

## 6. Volgorde

1. W7 (racewekenfix) — blokkeert nu al automatisch plannen.
2. W1 + W2 + W3 + W5 — samen één PR: "planner kent het 10k-blok".
3. W4 + W6 — patroon en kracht.
4. W8 — drie ankers (AeT/drempel/vVO2) + REN-overnames (range-miss-regel, RIR-vraag,
   CTL als guardrail); eerste 6-min kalibratie in de herstelweek na de Bruggenloop.
5. W9 — vóór juni 2027.

Blok 1 (t/m 13 dec) blijft handmatig en vergrendeld; de planner neemt het over vanaf blok 2
(start ~21 dec). Scheduler-risico: Railway-build respecteert de lock niet — eerst redeploy
of `SCHEDULER_ENABLED=0` checken vóór 2 nov.

## 7. Bouwstatus (27 okt 2026)

Gebouwd op branch `feat/planlogica-v4` (bovenop PR #59):

- **Blokpad** voor 10k/5k/half-doelen: `agents/block_planner.py` (skelet + dagplaatsing)
  en `agents/block_library.py` (sessies in de stijl van blok 1). Marathon blijft op het
  bestaande V3-pad.
- W1 doelen: `scripts/migrate_planlogica_v4.py` (Amsterdam/Big 10 → completed, Leiden A,
  Bruggenloop/Schoorl/CPC/Rotterdam B, parkrun C, `run_pattern` + `block_start`), doeltype `15k`.
- W2 toolkit per doeltype × gate, W3 `vo2_run` / `race_pace` / ASR-aanhangsel, W5 long run
  75-90 min roterend, W4 4-3-4-3 + fiets-sub-T de dag ná lopende kwaliteit, W6 kracht A/B
  2×/wk, W7 raceweken (race vervangt sub-T; ≥15 km ook de long; A/B: taper, openers, dag
  ervoor vrij) plus herstelweek met 6-min kalibratie na een A/B-race; blok herstart dan op trede 1.
- W8 deels: drie ankers met terugval (`vvo2_pace_sec`, `aet_pace_sec` in state; ontbreken ze,
  dan afgeleid van de drempel). Nog niet: automatische bijstelling (range-miss-regel, RIR-vraag).
- Tredes volgen de blokweek (sinds `block_start` of na herstelweek), niet het plan-weeknummer.
  Nog niet: "pas door als de vorige trede schoon was" — dat vraagt de RIR/range-data van W8.
- Dry-run naast de kalender: `scripts/compare_block_plan.py 2026-11-09 2026-12-07`.
