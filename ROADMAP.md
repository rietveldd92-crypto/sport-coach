# Sport Coach — Roadmap

*Van trainer naar coach. Van spreadsheet naar persoonlijke begeleiding.*

> "Ik ben dertig procent trainer, zeventig procent coach." — Louis Delahaije

---

## Visie

De app moet voelen als een persoonlijke coach die je kent, niet als een dashboard dat je afrekent. Elke interactie moet de atleet helpen om het beste uit zichzelf te halen — niet door harder te pushen, maar door slimmer te trainen, beter te herstellen en meer plezier te hebben.

**Kernprincipes:**
- Gevoel is leidend, niet het horloge
- Een gelukkige atleet is een snelle atleet
- Volume boven intensiteit
- Data ondersteunt het gevoel, vervangt het niet
- De app mag nooit een stressfactor worden

---

## Fase 1 — Het Gevoel (de 70% coach)

### 1.1 Morning Check-in
- 4 vragen bij openen app: slaap, energie, spierpijn, motivatie (slider 1-5)
- 30 seconden, geen gedoe
- Score stuurt de training: laag → makkelijker alternatief voorgesteld
- Opgeslagen als wellness trend over weken

### 1.2 Verwachting vs Werkelijkheid
- **Voor de training:** bij elke workout een korte coaching-noot over hoe die moet voelen
  - Z2 duurloop: "Dit moet conversatietempo zijn. Je moet kunnen praten. Als je hijgt, ga je te hard."
  - Threshold fiets: "De eerste interval voelt makkelijk. De laatste doet pijn. Zo hoort het."
  - Lange duurloop: "Begin bewust langzaam. De eerste 5km zijn opwarming, niet training."
  - Recovery run: "Dit is geen training. Dit is actief herstel. Langzamer dan je denkt."
- **Na de training:** vergelijk het gevoel met de data
  - "Je HR was 78% HRmax bij een Z2 run — dat klopt met 'makkelijk'. Goed geluisterd."
  - "Je zei dat het zwaar voelde, maar je HR was laag. Misschien slechte nacht of stress op werk?"
  - Als het gevoel niet matcht met de data: dat is een signaal, geen fout

### 1.3 Adaptief Schema op Basis van Gevoel
- Check-in score < 3 → swap-suggestie naar makkelijker alternatief
- Niet als "downgrade" maar als slim coachen
- Positieve framing: geen rood bij gemiste workouts, geen "achter op schema"
- Wel: "Goed dat je naar je lichaam luistert"

### 1.4 Kwaliteitstraining Herschikken
- Als een threshold/sweetspot/tempo sessie gemist wordt: niet laten vallen
- Automatisch kijken of die later in de week nog past
  - Check: geen twee harde sessies achter elkaar
  - Check: niet op de dag voor de lange duurloop
  - Check: niet als de week al te zwaar is (TSS-budget)
- Voorstel: "Je hebt dinsdag de sweetspot gemist. Donderdag is een Z2 dag — wil je die swappen?"
- Kwaliteitssessies zijn de belangrijkste trainingen, die bescherm je

### 1.5 Weekreflectie
- Zondag: "Waar genoot je van deze week? Wat kostte energie?"
- Open vraag, AI verwerkt het → persoonlijkere feedback volgende week
- Bouwt een profiel op van wat de atleet motiveert

---

## Fase 2 — De Ervaring (Apple design)

### 2.1 Vandaag-Eerst Scherm
- Single-focus kaart als hoofdscherm: wat is de workout van vandaag?
- Coaching-noot over hoe het moet voelen (zie 1.2)
- Check-in prompt als die nog niet gedaan is
- Weeklijst als secundair tabblad

### 2.2 Data → Menselijke Taal
- "CTL 44.3" → "Je basis groeit gestaag — je lichaam kan meer aan dan drie weken geleden"
- "Fase: herstel_opbouw_I" → "We bouwen je fundament. Nog 28 weken — alle tijd."
- "TSB -8.3" → "Je bent licht vermoeid. Normaal voor een opbouwweek."
- Getallen alleen on-demand (tooltip/expandable)

### 2.3 Coach-Feedback als Gesprek
- Weg met `st.info()` blauwe boxen → warme quote-styling
- Feedback voelt als een bericht van je coach, niet als een systeemmelding
- Witruimte eromheen, typografie: workout naam groot, stats klein en grijs

### 2.4 Visuele Rust
- Emoji's eruit, subtiele kleurindicatoren erin (groene stip = voltooid)
- Witruimte laat de data ademen
- Geen `st.divider()` overal — witruimte doet het werk
- Kleurpalet: zwart/wit basis, groen voor positief, rood alleen voor echte waarschuwingen

---

## Fase 3 — De Trends (data met betekenis)

### 3.1 CTL-Curve met Race Target
- Lijngrafiek CTL over 16 weken
- Target corridor naar racedag (bijv. CTL 70-80)
- Huidige trend geëxtrapoleerd: "als je zo doorgaat, zit je op CTL 74 op racedag"
- Eén blik = weet je of je op koers ligt

### 3.2 Weekvolume Staafdiagram
- Km per week (hardlopen + fietsen apart)
- 10%-opbouwregel als referentielijn
- Periodisering visueel: opbouw-opbouw-opbouw-herstel patroon

### 3.3 Cardiac Decoupling Trend
- Per lange duurloop over tijd
- Dalende trend = aerobe fitness verbetert
- Stoplicht: groen (<3%), oranje (3-5%), rood (>5%)

### 3.4 Race Readiness Samenvatting
- Combineert: CTL trend + decoupling + TSB + weken tot race
- Kwalitatief: "Je fitness bouwt op. Aerobe basis verbetert. Focus: lange duurloop in Z2."
- Race predictor (Riegel-formule + CTL-correctie)

### 3.5 Plan Adherence
- Percentage geplande TSS dat uitgevoerd is, per week (niet per workout)
- 85-100% = prima, <70% = "drukke week gehad?"
- Geen schuld, wel bewustzijn

---

## Fase 4 — De Preventie (proactief)

### 4.1 Composite Recovery Score
- HRV-trend + slaap + trainingslast → één herstelscore
- Simpel: go / easy / rust
- Koppelen aan check-in (fase 1.1)

### 4.2 Asymmetrie-Monitor
- Links/rechts grondcontacttijd en kadansbalans per run
- Alert bij >2% verschuiving richting rechts (compensatie gluteus medius)
- Trend over tijd: verbetert de symmetrie?

### 4.3 Rehab Streak Tracker
- Revalidatie-oefeningen afvinken per dag
- Streak bijhouden (motivatie door consistentie)
- Koppelen aan verbetering: "Je symmetrie is 49/51 sinds je de clamshells consequent doet"

### 4.4 ACWR Alert
- Acute:Chronic Workload Ratio (7-daags / 28-daags)
- Waarschuwen bij ratio >1.3 (injury danger zone)
- Visueel in de recovery score integreren

---

## Fase 5 — Het Fundament (techniek)

### 5.1 SQLite History Database
- `history.db` voor weekly summaries, wellness snapshots, workout evaluations
- Nightly GitHub Action die intervals.icu pollt
- Maakt trend visualisatie mogelijk zonder API-spam

### 5.2 Cache-laag in intervals_client.py
- `diskcache` of SQLite-backed, TTL per endpoint
- CLI en UI profiteren allebei
- Wellness: 1 uur TTL, activities: 5 min, events: 2 min

### 5.3 Consolideer Feedback-generatie
- `app.py`, `coach.py` en `auto_feedback.py` → één gedeelde module
- `workout_analysis.py` als basis, één prompt template, één fallback
- Verwachtings-noten per workout type (fase 1.2) als nieuwe module

### 5.4 Race Predictor
- Riegel-formule op basis van recente tempo/race resultaten
- CTL-correctie voor huidige fitheid
- Rule-based, geen AI nodig

---

## Prioritering

| Prio | Item | Impact | Effort |
|------|------|--------|--------|
| 1 | Verwachting vs werkelijkheid (1.2) | Hoog — kern van coaching | Klein |
| 2 | Kwaliteitstraining herschikken (1.4) | Hoog — beschermt key sessions | Middel |
| 3 | Vandaag-eerst scherm (2.1) | Hoog — eerste indruk | Middel |
| 4 | Data → menselijke taal (2.2) | Hoog — gevoel vs spreadsheet | Klein |
| 5 | Morning check-in (1.1) | Hoog — gevoel als input | Middel |
| 6 | Coach-feedback styling (2.3) | Middel — UX verbetering | Klein |
| 7 | CTL-curve (3.1) | Middel — trend inzicht | Middel |
| 8 | SQLite database (5.1) | Middel — enabler voor trends | Middel |
| 9 | Recovery score (4.1) | Middel — preventie | Middel |
| 10 | Race readiness (3.4) | Middel — motivatie | Middel |
