# REN (Run with Ren) / De Loopschool: afgeleide trainingsrequirements

Onderzoek van 26 okt 2026. De makers van de app zijn Michel Butter (ex-topmarathonloper), Guido Hartensveld (coach, bureau TwoZeroNine) en Jim van den Berg (bewegingswetenschapper, maker van de fiets-app JOIN). Uitgever is Ren Sports B.V.

## (a) Bronnen

**Transcripties.** Er zijn geen officiële transcripties gevonden: niet in de RSS-feed, niet op runwithren.com en niet op Podengine (daar alleen tegen betaling). Daarom zijn 16 afleveringen zelf getranscribeerd uit de mp3's in de RSS-feed (https://anchor.fm/s/10a80badc/podcast/rss), met faster-whisper (model small, NL). De transcripties zijn automatisch gemaakt en bevatten fouten: namen worden verhaspeld ("2-0-9"/"Join" i.p.v. REN) en getallen zijn soms onzeker. Timestamps staan als [mm:ss]. De ruwe transcripties staan in `scratchpad\dl\epNN.txt`.

Deze afleveringen zijn volledig gelezen:
- #2 Train de loper, niet de tijd (29-12-2025)
- #13 Luisteraarsvragen (16-03-2026)
- #15 Wielrennen & Hardlopen (30-03-2026)
- #16 Complexe Systemen (06-04-2026)
- #17 Rennen met REN (13-04-2026), de aflevering over de app zelf
- #19 VO2max (27-04-2026)
- #23 Luisteraarsvragen II (01-06-2026)
- #24 Intensiteitscontrole (08-06-2026)
- #27 De (on)zin van zones (29-06-2026)
- #28 Hoe heilig is tempo? (06-07-2026)
- #30 Verplaatsen van trainingen (20-07-2026)
- #34 Strides (17-08-2026)
- #35 Luisteraarsvragen III, met app-vragen (24-08-2026)
- #40 Taperen (28-09-2026)
- #43 Herstel na een marathon (19-10-2026)
- #44 Aerobe Drempel (26-10-2026)

De overige 28 afleveringen zijn alleen via de shownotes in de RSS-feed bekeken: hitte, voeding, carbon, blessures, slaap, pacing, botgezondheid, recovery tools enzovoort. Ze bevatten geen app-logica.

**Overige bronnen:**
- App Store: https://apps.apple.com/app/id6753206434 (beschrijving + release notes t/m v2.6.0)
- https://runwithren.com, /how-it-works, /why-ren, /de-loopschool-podcast, /race-time-predictor (formule niet zichtbaar)
- Artikelen: https://runwithren.com/articles/critical-speed-training, /articles/individual-athlete-profiles, /articles/peaking-on-race-day
- Niet bereikbaar: het helpcenter https://runwithren.zendesk.com (403) en Google Play (pagina leeg)
- Podengine-overzicht: https://www.podengine.ai/podcasts/de-loopschool

Legenda: **[app]** betekent expliciet over het gedrag van de REN-app. **[visie]** betekent coachingvisie van de hosts, niet aantoonbaar zo in de app gebouwd.

## (b) Requirements

### Intensiteit, ankerpunten en kalibratie

**REN-01 [app]: drie aparte ankers.** De app werkt met drie losse ankers: aerobe drempel (AeT), critical speed (CS) en vVO2max-pace. Er zijn geen genummerde zones en geen ankers als vaste percentages van één drempel. Elke training hangt aan één ankerpunt.
- Onderbouwing: artikel "individual athlete profiles" ("why REN works with three separate thresholds"); /why-ren ("Separate thresholds: AeT, CS, VO₂max"); #27 [1:52–3:07, 39:54–40:16]; #19 [29:04–29:49] ("onderscheidende factor"); #2 [12:39–13:19].
- Zekerheid: hoog.

**REN-02 [app]: de verhouding tussen de ankers is individueel.** De verhouding AeT:CS:vVO2max verschilt per profiel, dus wordt elk anker apart getest. Een "diesel" heeft AeT dicht bij CS; anderen hebben een groot gat, en voor hen mag easy niet van CS afgeleid worden.
- Onderbouwing: #44 [16:54–17:14, 18:27–19:37]; artikel athlete profiles.
- Zekerheid: hoog.

**REN-03 [app]: vVO2max via een 6-minutentest.** vVO2max wordt bepaald met een 6-minuten-all-outtest op een vlak parcours uit de wind, gemeten met GPS. VO2max in ml/kg/min of de horloge-VO2max wordt niet gebruikt; die horlogewaarde wordt genegeerd (~5% fout).
- Onderbouwing: #2 [36:35]; #19 [5:46–6:12, 26:51–27:34]; artikel athlete profiles.
- Zekerheid: hoog.

**REN-04 [app]: CS via een kalibratie van ~30 minuten.** Dit is ook de nulmeting bij onboarding, liefst op een beschut parcours in de eigen trainingsomgeving.
- Onderbouwing: #27 [34:31–34:58]; #44 [3:30–3:59].
- Tegenstrijdigheid: #2 [37:14] noemt het "niet all-out, gevoel dat je nog iets door kunt", #27 noemt "all-out". #44 zegt dat CS ~45–60 min vol te houden is.
- Zekerheid: middel.

**REN-05 [app]: AeT-kalibratie via HR:pace-decoupling.** De startwaarde van AeT wordt afgeleid van CS (~30–40 s/km trager). Daarna volgen AeT-kalibratieblokken die steeds langer worden. De efficiëntie (pace/HR) van de eerste helft wordt vergeleken met de tweede helft. Is de HR bij gelijke pace meer dan ~5% gestegen, dan is er verval en wordt de AeT-pace trager gezet. Een "verspringend" AeT-tempo is dus bedoeld gedrag. Hitte en vochtverlies gelden als verstorende context. Hiervoor is een HR-meter nodig, bij voorkeur een borstband.
- Onderbouwing: #44 [17:19–17:40, 30:47–32:34, 38:32]; #24 [20:46–23:46]; #2 [41:34–43:20] ("dat hebben we allemaal in de REN app verwerkt"); #27 [21:39–22:26].
- Zekerheid: hoog. Alleen de exacte startwaarde is middel.

**REN-06 [app]: kalibratieomstandigheden en herhaling.** Kalibreer onder gemiddelde omstandigheden: geen piekdag, geen carbon, geen cafeïne-boost, en op de gewone trainingsschoen. Liefst loop je twee keer hetzelfde rondje vanwege de wind. Een "test" heet in de app bewust "kalibratie", om de prestatiedruk weg te nemen. Kalibraties worden regelmatig herhaald, omdat de drempel een "moving target" is.
- Onderbouwing: #28 [8:17, 25:55–26:09, 36:15–37:57]; #44 [32:49–33:37]; #35 [41:17–41:43]; #2 [39:12–40:03].
- Zekerheid: hoog.

**REN-07 [app]: bij nieuwe gebruikers eerst backfill, dan testen.** De app laadt de historie in (Garmin/Apple Health backfill) en bouwt daarmee een profiel op. Daarna plant hij snel de CS- en 6-minutentest in. Het profiel wordt vollediger met de gedane trainingen en de feedback.
- Onderbouwing: #17 [39:46–39:58]; #19 [40:56–41:39].
- Zekerheid: hoog.

**REN-08 [app]: paces handmatig aanpassen.** De gebruiker kan paces met de hand aanpassen. Na inactiviteit, of na een te scherpe test, adviseren de coaches 10–15 s/km trager te zetten. Lukken de CS-blokken niet, dan klopt de test niet: opnieuw testen of handmatig corrigeren.
- Onderbouwing: #35 [38:33–42:23].
- Zekerheid: hoog.

### Voorschrift en uitvoering

**REN-09 [app]: het voorschrift is pace.** Het voorschrift is "X minuten op pace-range Y". De ranges zijn ±5 s/km, voor easy ±10 s (#27 noemt een easy-range van ~20 s breed). HR, power en lactaat staan bewust niet in het voorschrift, omdat HR vertraagd reageert en beïnvloed wordt door hitte, cafeïne en slaap. Running power gebruiken ze ook niet in de analyse.
- Onderbouwing: #24 [7:18–10:23, 17:50–19:38, 46:39–53:42]; #28 [2:41–4:59]; #23 [8:15–9:40]; #27 [16:01, 48:26].
- Zekerheid: hoog.

**REN-10 [app]: RPE als tweede signaal.** Elke workout heeft ook een RPE-doel (1–10), en na afloop vraagt de app hoe zwaar de training voelde. Er wordt niet primair op RPE gestuurd, omdat RPE oploopt met de duur. De app past aan op RPE-feedback. Daarnaast geldt "reps/time in reserve" als opdracht vooraf ("werk af met X in reserve") en als vraag achteraf ("hoe lang had je nog gekund?").
- Onderbouwing: #24 [27:19–33:20]; #16 [22:31–27:46].
- Zekerheid: middel-hoog. De RIR-feedback in REN zelf is middel.

**REN-11 [app]: HR alleen in de analyse.** HR wordt alleen in de analyse achteraf gebruikt: na de training getoond en gebruikt voor de AeT-kalibratie. Valt de decoupling in AeT-blokken buiten de bandbreedte, dan krijgt de gebruiker het advies die trainingen rustiger te lopen.
- Onderbouwing: #24 [20:46–23:15].
- Zekerheid: middel-hoog.

**REN-12 [app]: CS-intervallen onder de geteste CS.** CS-intervallen worden voorgeschreven 3–5 s/km trager dan de geteste CS, omdat mensen de neiging hebben eroverheen te gaan. Een CS-blok moet "zwaar maar stabiel" voelen, eindigen met 1–2 herhalingen in reserve en nooit als "blij dat ik mag stoppen". De blokken beginnen kort (3–5 min) en worden over de weken langer.
- Onderbouwing: #27 [37:29–37:46]; #35 [39:37–42:23]; #23 [27:47–28:12]; artikel critical speed (RIR 1–2).
- Zekerheid: hoog.

**REN-13 [app]: twee soorten training onder AeT.** Het moderate domein (onder AeT) kent twee trainingssoorten:
- "Easy" ligt duidelijk lager dan AeT, volgens "hoe rustiger hoe beter". De ondergrens mag je negeren.
- De "AeT-duurloop" is de stevigste intensiteit die nog onder AeT valt. Die loop je een paar seconden onder AeT, niet hoog in de range. Voorbeeld uit de app: AeT 4:25, range 4:20–4:30, Jim mikt op 4:30.

Zo moet het voelen: hele zinnen kunnen zeggen; de "stoplichttest" (hoop je stiekem op rood, dan loop je te hard); "ik kan dit eindeloos"; geen focus nodig.
- Onderbouwing: #27 [17:00–19:52]; #44 [8:17–8:33, 15:37–16:51, 28:51–29:23, 33:44–35:30]; #35 [36:23–38:01].
- Zekerheid: hoog.

**REN-14 [app]: VO2max-werk in microintervallen.** VO2max-sessies bestaan uit microintervallen op 6-minutenpace, bijvoorbeeld 2×8×30" opbouwend naar 10–12 herhalingen, of 3×3' met ~3' rust. De vuistregel is ~6 min totaal op intensiteit per sessie. Deze vorm heeft de voorkeur boven 4×4'.
- Onderbouwing: #27 [41:00–43:41]; #19 [33:30–36:46].
- Zekerheid: hoog.

**REN-15 [visie]: één doel per training en binnen de lijntjes blijven.** Elke training heeft één hoofddoel (AeT, CS of VO2max), anders wordt het "ratjetoe". De meest gemaakte amateurfout is CS te hard lopen, waardoor het VO2max-werk wordt. Hoe meer volume, hoe strakker je binnen de lijntjes moet blijven. Bij weinig tijd (bijv. 3×/week) mag je één keer richting of over AeT.
- Onderbouwing: #24 [14:35–15:26, 33:03–35:33]; #2 [34:48–36:02]; #27 [49:16–50:55]; #13 [21:36].
- Zekerheid: hoog.

**REN-16 [visie]: ranges en dagvorm.** Pace is niet heilig. Ben je niet fris, kies dan de onderkant van de range. Pas bij wind, zand of heuvels aan: tegenwind ~10 s trager, zand 15–20 s trager, heuvels op gevoel. Carbon geeft ~6–8 s/km. Haal je de range vaker dan ~1 op 10 trainingen niet zonder externe oorzaak, dan klopt de drempel niet. Een lage HR terwijl de pace niet lukt is een rode vlag: stoppen of rustig verder.
- Onderbouwing: #28 [6:31–9:16, 14:19–15:09, 18:47–19:56, 24:01–34:05]; #23 [7:24–8:13].
- Zekerheid: middel-hoog.

### Planlogica en progressie

**REN-17 [app]: geen standaardschema's.** Het plan wordt tegelijk bottom-up en top-down gebouwd. Top-down: terugrekenen vanaf het doel naar wat je dan moet kunnen. Bottom-up: de volgende, langere of zwaardere training komt pas als de progressie laat zien dat je eraan toe bent. Is iemand niet klaar voor 30 km, "dan komt hij gewoon niet". Vaste 3-maandenschema's (3×, 4× of 5×/week) bieden ze bewust niet aan.
- Onderbouwing: #17 [37:37–41:00]; #16 [26:10–27:46, 43:04].
- Zekerheid: hoog.

**REN-18 [app]: key sessions met eligibility.** Key sessions zijn individueel geschaald op de doeltijd (3u tegenover 5u) en vereisen dat je er "eligible" voor bent: je moet de belasting eerst opgebouwd hebben. Niet iedereen krijgt evenveel specifieke trainingen.
- Onderbouwing: #17 [26:50–27:06, 41:17–41:58].
- Zekerheid: hoog.

**REN-19 [app]: volume als grondregel.** De grondregel is volume constant uitbouwen op basis van wat iemand nu aankan. Blijft bij een marathondoel de long run achter, dan wordt die geprioriteerd boven andere trainingen. Bij een 10k-doel komt meer HIT en geen 3-uursloop. In een marathonblok wordt HIT "ongeveer geminimaliseerd".
- Onderbouwing: #17 [42:35–43:52]; #43 [43:03–43:14].
- Zekerheid: hoog. De HIT-minimalisatie is laag.

**REN-20 [app]: beschikbaarheid is het trainingsbudget.** De gebruiker geeft per dag zijn beschikbaarheid op, en die is in feite het trainingsbudget: hoeveel tijd wil je aan de sport besteden, niet alleen hoeveel tijd je hebt. Geef je veel beschikbaarheid, dan plant de app ook veel volume. Wie minder wil, zet de beschikbaarheid lager.
- Onderbouwing: #17 [44:21–45:17]; App Store ("scheduling that fits your availability").
- Zekerheid: hoog.

**REN-21 [app]: geen kalenderweken.** De app plant niet in kalenderweken maar op basis van beschikbaarheid, de zwaarte van de laatste training en wanneer de volgende komt. Weekvolumes wisselen daardoor.
- Onderbouwing: #30 [16:49–17:23].
- Zekerheid: hoog.

**REN-22 [app]: herplannen bij overslaan, verplaatsen en pinnen.** Na een voltooide of gemiste training wordt het plan herberekend. Een gebruiker kan trainingen overslaan, verplaatsen of "pinnen" (vastzetten op een dag, zodat de herplanlogica die dag niet verandert). Altijd pinnen of schuiven raden de coaches af: "dan kun je net zo goed een screenshot maken".
- Onderbouwing: #17 [54:42–57:17]; #30 [43:16–43:36]; App Store.
- Zekerheid: hoog.

**REN-23 [visie]: prioriteren en verplaatsen.** Een goed plan zet eerst de intensieve trainingen neer; de easy runs komen eromheen en zijn makkelijk te schuiven of te skippen. Plan nooit twee zware trainingen kort na elkaar. Overslaan is meestal beter dan verplaatsen: haal niets in. Omdraaien mag (zware zondag naar zaterdag). In de laatste ~2 maanden voor een marathon gaan de long run en de AeT-duurloop voor, en VO2max skip je het eerst. Vaak verplaatsen hangt in de data samen met meer blessures en minder progressie.
- Onderbouwing: #30 [6:28–11:21, 19:05–25:06, 28:32–29:35].
- Zekerheid: hoog.

**REN-24 [visie]: twee zware trainingen per week in de marathonfase.** Butter liep er twee: zondag vast en de tweede "met potlood" op woensdag of donderdag. De app noemt geen vast aantal kwaliteitssessies.
- Onderbouwing: #30 [13:49–15:20].
- Zekerheid: hoog als uitspraak over Butters praktijk. Er is geen bron gevonden voor een app-regel over het aantal sessies.

**REN-25 [visie]: VO2max alleen als het plafond beperkt.** Is vVO2max minder dan ~8–10% sneller dan CS, doe dan vroeg in de voorbereiding een blok van 4–6 weken met een 6-minutentest ervoor en erna. Bij ~20% marge is VO2max geen beperking: kies dan voor volume en efficiëntie. Dat geldt voor ~90% van de geteste lopers. Voor HM en marathon is VO2max de minst belangrijke pijler en die met het meeste risico. Microdosering mag wel, bijvoorbeeld een 8e herhaling na een CS-set.
- In de app: "is de marge klein, dan krijg je meer van die trainingen".
- Onderbouwing: #2 [23:38–25:19, 52:19]; #19 [14:44–15:13, 28:40–41:39]; #27 [39:44–40:49].
- Zekerheid: hoog. Het exacte percentage is middel.

**REN-26 [visie]: vier pijlers.** Prestatie rust op vier pijlers: vVO2max, CS, AeT en efficiëntie/economy, plus fatigue resistance/durability. Fatigue resistance meet je als het verval van AeT, CS of vVO2max na een lange belasting. Voorbeeld: CS 4:00 wordt 4:10 na 2 uur. Een andere meting is het verval in HR:pace, of een HM-tempoblok herhalen na ~75 min. Bij 3–5-uursmarathonlopers is AeT dé voorspeller; topatleten lopen de marathon net onder CS. Train de zwakste schakel.
- Onderbouwing: #2 [8:30–20:59, 45:12–46:08]; #19 [6:34–8:49]; #44 [38:49–39:09]; artikel athlete profiles.
- Zekerheid: hoog.

**REN-27 [app + visie]: progressie is niet-lineair.** Plateaus zijn normaal, en als vuistregel is ~60% van de trainingen matig, 20% goed en 20% slecht. CTL en weekvolume zijn terugkijkmaten en geen doel. Bewust NIET in de app: na elke training een "+3 s op je marathonvoorspelling" (zoals Garmin/Strava/Runna), omdat dat een lineair rekenmodel suggereert.
- Onderbouwing: #17 [48:35–49:46]; #16 [20:56–31:47]; #28 [41:43–42:51].
- Zekerheid: hoog.

**REN-28 [app]: racevoorspelling als bandbreedte.** De racevoorspelling is een bandbreedte op basis van opgegeven PR's, de ingeladen historie en het doel. Die band wordt smaller en wordt bijgesteld op kalibratietests (ook negatief) en nieuwe PR's (extrapolatie). De web-predictor noemt de Riegel-formule plus het "trainingsprofiel" en de tijd tot de race (1 week tot 16 maanden), maar de formule zelf is niet gepubliceerd.
- Onderbouwing: #17 [46:46–48:27]; /race-time-predictor.
- Zekerheid: hoog. De formule is onbekend.

### Herstel, signalen en bijsturing

**REN-29 [visie]: rode en oranje vlaggen.** Blessure, pijn, koorts of ziekte zijn rode vlaggen: niet trainen. Bij oranje vlaggen (geen zin, moe, stram bij het inlopen, tempo komt moeilijk, HR blijft laag) maak je van intensief rustig of breek je af. Begin bij twijfel "nieuwsgierig" onderin de range.
- Onderbouwing: #30 [4:13–5:58, 31:17–32:00].
- Zekerheid: hoog.

**REN-30 [visie]: HRV en readiness alleen als trend.** HRV meet de respons op stress, niet de stress zelf. Kijk naar trends over meerdere dagen samen met stemming, ochtendpols en stijfheid; één dag zegt niets. Een afwijkende HRV op wedstrijddag is normale arousal. Garmin-readiness en body battery wantrouwen ze. Uit de gelezen bronnen blijkt niet dat de app op HRV bijstuurt. Wel claimt /why-ren dat REN "adjusts your plan based on your activity, recovery metrics, and available time", zonder toelichting.
- Onderbouwing: #13 [9:08–12:58]; #30 [32:12–33:15]; #43 [20:26–27:04].
- Zekerheid: hoog voor de visie, laag voor het app-gedrag.

**REN-31 [app]: geen automatische herstelfase.** Na een 10k of HM "gaat de app gewoon door" zodra je een nieuw doel instelt. Na een marathon geeft de app "behoorlijk wat dagen rust", en na ~1 week loopt het weer aan als je beschikbaarheid opgeeft. Het advies van de coaches: 5 dagen niet lopen, 2–3 weken ongestructureerd, vanaf week 3 een schema, en de beschikbaarheid de eerste ~4 weken laag zetten.
- Onderbouwing: #43 [5:30–6:31, 37:41–42:26]; #17 [45:17–45:23].
- Zekerheid: hoog.

**REN-32 [app]: automatische taper.** De taper bouwt de app automatisch in, in volume en intensiteit, met een aparte Race Week-weergave. De visie erachter: marathontaper ~2 weken; laatste lange key ~2 weken voor de race (bij recreanten 3); volume ~70% in week −2 en ~50% in week −1; intensiteit gelijk houden; frequentie behouden. In de raceweek woensdag of donderdag nog een kort blok van ~1 uur (bijv. 3 km MP + 2 km HMP + 1 km 10k-pace), daarna korte loopjes met strides.
- Onderbouwing: #40 [4:08–26:23, 41:00–41:19]; runwithren.com ("Race Week plan").
- Zekerheid: hoog voor het bestaan in de app. De exacte percentages in de app zijn onbekend: die gelden als visie.

**REN-33 [app]: fietsen telt mee, maar wordt niet gepland.** De app plant geen fietstrainingen. Fiets- en andere activiteiten tellen wel mee in de totale trainingsbelasting, zodat na een zware rit niet direct een zware run volgt. Deze functie was in april 2026 aangekondigd; de huidige status is niet geverifieerd. Hyrox en kracht upload je als krachttraining met RPE en niet als run, omdat de app een run alleen op pace beoordeelt.
- Onderbouwing: #17 [53:02–53:40]; #15 [36:48–37:00]; #35 [6:35–7:21].
- Zekerheid: middel-hoog.

**REN-34 [visie]: zo zet je de fiets in.** Altijd rustig. Fiets de dag ná een zware run, niet ervoor; ook na een fietsdag liever een rustige run dan intervallen. Fietsen is niet gratis: van 4–5 naar 10+ uur gaat niet straffeloos. Periodiseer: eerst een brede basis met fietsuren, de laatste ~6 weken voor een marathon minder fiets en meer lopen. Hart en mitochondriën zetten over naar het lopen; pezen, excentrische belasting en economy niet. Alternatief trainen is veiliger dan extra loopintensiteit.
- Onderbouwing: #15 [21:30–52:55]; #2 [52:44].
- Zekerheid: hoog.

**REN-35 [app]: strides staan niet in de app.** Strides zitten (nog) niet in de app, omdat ze niet als pace en duur te programmeren zijn; ze willen ze wel beschrijvend toevoegen. Wel plant de app vaak vóór CS-, tempo- of MP-dagen een training met korte speelse versnellingen als "primer". De visie: 8–12 s op 90–95%, volledig herstel, start met 3 en bouw op naar 8, 1×/week bij 3 runs, aan het eind van een easy run, de dag vóór de kwaliteit en nooit de dag na zwaar.
- Onderbouwing: #34 [3:30–44:21]; #13 [26:40–32:46].
- Zekerheid: hoog voor de afwezigheid, middel voor de primer.

**REN-36 [visie]: kracht en snelheid.** Zware kracht met weinig herhalingen geeft neuromusculaire winst. Sprints en strides helpen tegen het verval in de slotfase van de marathon (rekruteren van fast-twitch vezels). Bergaf lopen 1×/week bereidt de bovenbenen voor, en bij 3 runs per week vervangt dat de strides. De app plant geen kracht.
- Onderbouwing: #13 [32:27–37:33]; #23 [18:49–20:32]; #35 [15:39–17:09].
- Zekerheid: middel.

**REN-37 [visie]: wedstrijden in een marathonblok.** Tussen week −12 en −8 voor een marathon kunnen nog kortere wedstrijden. In de laatste 4–5 weken gaan de key-sessies voor wedstrijden. Een wedstrijd vervangt de CS-sessie, niet de long run. Subdoelen (tussenwedstrijden naast een hoofddoel) bestonden in augustus 2026 niet in de app, maar v2.1 meldt "goals and subgoals for a full season". v2.6 voegt clubtraining toe, waar REN de rest van de week omheen bouwt.
- Onderbouwing: #35 [17:41–24:34, 34:35–35:15]; App Store release notes.
- Zekerheid: middel-hoog.

### UX en doelgroep

**REN-38 [app]: eenvoud.** Toon alleen wat ertoe doet en breid stap voor stap uit, in plaats van 100 metrics tegelijk. De terminologie is eenduidig, het doel van elke training is duidelijk en er mag geen misverstand zijn in het voorschrift. De podcast dient als "naslagwerk" en educatie naast de app: de app is geen coach.
- Onderbouwing: #17 [13:52–16:19, 18:12–18:50, 57:22].
- Zekerheid: hoog.

**REN-39 [app]: doelgroep.** De doelgroep is de serieuze recreant (5 km tot marathon) met een horloge, plus beginners via run-walkopbouw (1–2 min lopen afgewisseld met wandelen). Niet bedoeld voor topsport: geen dubbele trainingen per dag, aanvankelijk geen ultra (v2.5 gaat tot 60 km) en geen baanatletiek. Gemiddelde gebruiker (maart 2026): 20,3 km in 2u37 per week, CS 4:48/km, AeT 5:26/km en vVO2max ~4:14/km. Onzeker: dit getal is in het gesprek verward.
- Onderbouwing: #17 [19:00–35:55]; App Store.
- Zekerheid: hoog.

**REN-40 [app]: score en integraties.** Een uitvoeringsscore per run ("how closely each run matches its workout") zit erin vanaf v2.4. Een intervals.icu-koppeling voor automatische workout-sync zit erin vanaf v1.20, ook als route voor COROS, Samsung en Google. Een spierpijn- of readiness-invoer stond in april 2026 op de roadmap; of die er nu is, is onbekend.
- Onderbouwing: App Store release notes; /why-ren; #17 [59:43–60:00].
- Zekerheid: hoog voor wat er in de release notes staat, laag voor de roadmap.

## (c) Opvallend of afwijkend van de mainstream

- **Geen zones en geen 80/20.** Er zijn drie los gekalibreerde ankers (AeT, CS, vVO2max) in plaats van zones afgeleid van één drempel of HRmax. "80-20, daar werken we niet mee": de verdeling hangt af van doel, uren en profiel (#13).
- **HR uit het voorschrift, wel in de analyse.** HR, power en lactaat staan niet in het voorschrift, maar HR is wel de kalibratiebron voor AeT (decoupling >5% → AeT trager). Dit is vrijwel hetzelfde idee als ons pace@145 en HR-drift.
- **CS-intervallen 3–5 s/km onder de geteste CS**, met reps in reserve als kern van de intensiteitscontrole. Bij de AeT-duurloop wordt bewust onderin de range gemikt.
- **VO2max standaard níet trainen.** Alleen in een blok van 4–6 weken als de marge tussen CS en vVO2max klein is (<~10%), en dan in microintervallen van ~6 min totaal in plaats van 4×4'.
- **Geen vaste weekstructuur en geen vaste schema's.** Er wordt niet in kalenderweken gepland en weekvolume en CTL zijn uitdrukkelijk geen sturingsdoel. Key sessions vereisen eligibility, dus de long run komt pas als je eraan toe bent.
- **Beschikbaarheid als trainingsbudget.** De gebruiker stuurt het volume via zijn beschikbaarheid; de app vult die.
- **Geen instant-voorspelling per training.** Bewust geen "+3 s"-gamification; de racevoorspelling verandert op kalibraties en PR's.
- **Bewust niet in de app:** strides (niet te programmeren), fietsen plannen, krachtschema's, een automatische herstelfase na een piekwedstrijd, dubbele trainingen per dag, en HRV als harde stuurvariabele (geen bewijs gevonden dat de app erop stuurt).
- **Herstel na een marathon conservatiever dan de studie die ze zelf aanhalen:** 5 dagen niets, ondanks een studie die geen nadeel vond bij hervatten na 48 u, "om mensen tegen zichzelf te beschermen".
- **Taper behoudt intensiteit en frequentie**: alleen het volume gaat naar ~70% en dan ~50%. Dat is mainstream, maar wordt expliciet zo voorgeschreven.
