"""Sessie-library voor 10k/5k-blokken (PLANLOGICA-V4, W3/W5/W8).

Schrijft sessies in de stijl van het handmatige blok 1 (nov-dec 2026):
reps op TIJD (geen baan), pace-range +-5 s/km leidend, HR alleen als
afbreekregel. Paces komen uit drie los gekalibreerde ankers (REN-01..03):

- AeT  -> easy-range (pace@145 / LT1)
- drempel -> sub-drempel, progressief, racetempo-referentie
- vVO2 -> VO2-reps en snelheidsreserve (vliegers)

Een anker dat nog niet gemeten is valt terug op een afleiding van de
drempel; die terugval staat in ``Anchors.bronnen`` zodat zichtbaar is
welke paces geschat zijn.
"""
from __future__ import annotations

from dataclasses import dataclass, field

PACE_RANGE_SEC = 5
HR_CAP_REP = 168
DRIFT_STOP_BPM = 5

# Terugval-verhoudingen t.o.v. de drempelpace (sec/km). vVO2 ~111% van de
# drempelsnelheid is wat blok 1 met de hand koos (3:50 bij drempel 4:16);
# AeT ~120% sluit aan op de gemeten LT1 van 4:50-5:00 (aug 2026) met wat
# marge, want easy runs zaten in de praktijk boven LT1.
VVO2_FROM_THRESHOLD = 1.11
AET_FROM_THRESHOLD = 1.20


@dataclass(frozen=True)
class Anchors:
    threshold_sec: int
    vvo2_sec: int
    aet_sec: int
    bronnen: dict = field(default_factory=dict)

    @property
    def easy_range(self) -> tuple[int, int]:
        return self.aet_sec - 7, self.aet_sec + 23


def load_anchors(state: dict | None = None) -> Anchors:
    """Lees de drie ankers uit de state; ontbrekende ankers worden afgeleid."""
    if state is None:
        try:
            from shared import load_state
            state = load_state() or {}
        except Exception:
            state = {}
    try:
        from agents.threshold_model import get_threshold_pace
        threshold = int(get_threshold_pace())
    except Exception:
        threshold = int(state.get("threshold_pace_sec_per_km") or 256)

    bronnen = {"drempel": "threshold_model"}
    vvo2 = state.get("vvo2_pace_sec")
    if vvo2:
        bronnen["vvo2"] = "gemeten"
    else:
        vvo2 = round(threshold / VVO2_FROM_THRESHOLD)
        bronnen["vvo2"] = "afgeleid van drempel"
    aet = state.get("aet_pace_sec")
    if aet:
        bronnen["aet"] = "gemeten"
    else:
        aet = round(threshold * AET_FROM_THRESHOLD)
        bronnen["aet"] = "afgeleid van drempel"
    return Anchors(int(threshold), int(vvo2), int(aet), bronnen)


# ── FORMAT-HELPERS ─────────────────────────────────────────────────────────

def pace(sec: int) -> str:
    mm, ss = divmod(int(round(sec)), 60)
    return f"{mm}:{ss:02d}"


def pace_range(sec: int, half_width: int = PACE_RANGE_SEC) -> str:
    return f"{pace(sec - half_width)}-{pace(sec + half_width)}/km Pace"


def _dur(seconds: int) -> str:
    """intervals.icu-duur: 90 -> '90s', 600 -> '10m', 510 -> '8m30s'."""
    if seconds < 120 and seconds % 60:
        return f"{seconds}s"
    mm, ss = divmod(seconds, 60)
    return f"{mm}m{ss}s" if ss else f"{mm}m"


def _dur_label(seconds: int) -> str:
    mm, ss = divmod(seconds, 60)
    if seconds < 120 and ss:
        return f"{seconds}s"
    return f"{mm}:{ss:02d} min" if ss else f"{mm} min"


def _tss(duration_min: float, intensity_factor: float) -> int:
    return round((duration_min / 60) * (intensity_factor ** 2) * 100)


def _easy(a: Anchors) -> str:
    lo, hi = a.easy_range
    return f"{pace(lo)}-{pace(hi)}/km Pace"


def _warmup(a: Anchors, pickup_sec: int) -> str:
    return (
        "Warmup\n"
        f"- 15m {_easy(a)}\n\n"
        "4x\n"
        f"- 20s {pace(pickup_sec)}/km Pace\n"
        "- 40s 5:30/km Pace\n\n"
    )


def _cooldown(a: Anchors, minutes: int = 10) -> str:
    lo, hi = a.easy_range
    return f"Cooldown\n- {minutes}m {pace(lo + 5)}-{pace(hi + 10)}/km Pace"


STURING = (
    "STURING: laatste rep niet sneller dan de eerste - HR-drift "
    f">{DRIFT_STOP_BPM} bpm vanaf rep 3 = klaar, rest uitlopen. "
    "Vooruitgang = eerst langer/meer reps, dan pas pace."
)
OP_TIJD = "Reps op TIJD, geen baan nodig: fietspad/parkrondje, vlak, liefst zacht."


def _session(sport: str, typ: str, naam: str, body: str, duur_min: int,
             intensity: float, zone: str, rol_hint: str | None = None) -> dict:
    out = {
        "type": typ,
        "naam": naam,
        "beschrijving": body,
        "duur_min": int(round(duur_min)),
        "tss_geschat": _tss(duur_min, intensity),
        "sport": sport,
        "zone": zone,
        "intensiteit_factor": intensity,
        "fun": 4,
    }
    if rol_hint:
        out["_block_role"] = rol_hint
    return out


# ── VO2 LOPEND (W3: vo2_run) ──────────────────────────────────────────────
# Ladder: pace vast op vVO2, duur rekken. Pas als de laatste trede schoon
# is mag de pace 2 s omlaag (dat is een anker-bijstelling, niet de ladder).
# Per trede drie varianten: tijd-reps, heuvelreps, 30/30 op gras.

VO2_LADDER: list[list[tuple]] = [
    # (soort, reps, werk_s, rust_s)  |  30/30: (soort, sets, reps_per_set, 0)
    [("tijd", 10, 90, 90), ("heuvel", 8, 60, 120), ("3030", 2, 8, 0)],
    [("tijd", 12, 90, 90), ("heuvel", 8, 75, 120), ("3030", 3, 8, 0)],
    [("tijd", 8, 120, 120), ("heuvel", 10, 75, 120), ("3030", 3, 10, 0)],
    [("tijd", 6, 150, 120), ("heuvel", 10, 90, 150), ("3030", 3, 12, 0)],
    [("tijd", 5, 180, 150), ("heuvel", 8, 120, 150), ("tijd", 6, 180, 150)],
    [("tijd", 5, 230, 150), ("heuvel", 8, 150, 180), ("tijd", 4, 270, 180)],
]


def vo2_run(step: int, variant: int, a: Anchors) -> dict:
    rung = VO2_LADDER[min(max(step, 1), len(VO2_LADDER)) - 1]
    soort, n, werk, rust = rung[variant % len(rung)]
    vo2 = a.vvo2_sec
    kop = (
        "SPICY - VO2max (pijler VO2). Het plafond optillen: pace vast, duur "
        "rekken. Heup: lange warmup.\n"
    )
    if soort == "3030":
        sets, reps = n, werk
        main = "".join(
            f"{reps}x\n- 30s {pace_range(vo2 - 5)}\n- 30s 6:00/km Pace\n\n"
            + ("- 3m 6:30/km Pace\n\n" if s < sets - 1 else "")
            for s in range(sets)
        )
        werk_min = sets * reps * 0.5
        duur = 15 + 4 + sets * reps + (sets - 1) * 3 + 10
        naam = f"Spicy - 30/30 op gras {sets}x{reps}"
        uitleg = "30/30 op GRAS: kort genoeg om de pace schoon te houden, lang genoeg om op VO2 te komen."
    elif soort == "heuvel":
        main = f"{n}x\n- {_dur(werk)} hard heuvel op (inspanning 3k-5k)\n- {_dur(rust)} 6:30/km Pace\n\n"
        werk_min = n * werk / 60
        duur = 15 + 4 + round(n * (werk + rust) / 60) + 10
        naam = f"Spicy - {n}x {_dur_label(werk)} heuvel"
        uitleg = "Heuvelreps op INSPANNING, niet op pace: bos/brug, rustig terug. Spaart de heup en bouwt kracht."
    else:
        main = f"{n}x\n- {_dur(werk)} {pace_range(vo2)}\n- {_dur(rust)} 6:00/km Pace\n\n"
        werk_min = n * werk / 60
        duur = 15 + 4 + round(n * (werk + rust) / 60) + 10
        naam = f"Spicy - {n}x {_dur_label(werk)} @ {pace(vo2)}"
        uitleg = OP_TIJD
    body = (
        f"{kop}{uitleg}\n\n{STURING} HR alleen als rem: >{HR_CAP_REP} op rep 1-2 = tempo eraf.\n\n"
        + _warmup(a, vo2 - 15)
        + "Main Set\n" + main
        + _cooldown(a)
    )
    intensity = 0.88 + min(werk_min, 20) / 200
    return _session("Run", "vo2_run", naam, body, duur, intensity, "Z5 VO2max")


# ── SUB-DREMPEL LOPEND ────────────────────────────────────────────────────
# Zelfde overload-as als de Norwegian-ladder (eerst minuten, dan repduur),
# percentages 95-97% van de drempelsnelheid. Variant 0 per trede is een
# fartlek of een duurloop met sub-T-blok: speelser dan reps.

SUBT_LADDER: list[list[tuple]] = [
    # (soort, reps, werk_s, rust_s, pct)
    [("fartlek", 3, 0, 0, 96), ("reps", 5, 360, 60, 95), ("reps", 4, 420, 75, 95)],
    [("reps", 4, 480, 75, 95), ("reps", 6, 360, 60, 95), ("fartlek", 3, 0, 0, 96)],
    [("reps", 4, 510, 75, 96), ("reps", 3, 720, 90, 96), ("reps", 5, 480, 75, 96)],
    [("reps", 5, 480, 75, 96), ("duur", 25, 5, 0, 96), ("reps", 3, 780, 90, 96)],
    [("reps", 4, 600, 90, 96), ("duur", 25, 8, 0, 96), ("reps", 6, 420, 60, 96)],
    [("reps", 3, 900, 120, 97), ("reps", 5, 540, 75, 97), ("duur", 30, 8, 0, 97)],
]


def pace_from_pct(threshold_sec: int, pct: float) -> int:
    return int(round(threshold_sec / (pct / 100)))


def subthreshold_run(step: int, variant: int, a: Anchors) -> dict:
    rung = SUBT_LADDER[min(max(step, 1), len(SUBT_LADDER)) - 1]
    soort, n, werk, rust, pct = rung[variant % len(rung)]
    subt = pace_from_pct(a.threshold_sec, pct)
    kop = (
        "SUB-DREMPEL (pijler LT). Net ONDER drempel, praten in stukjes. "
        f"Mag nooit een tempoloop worden. HR <={HR_CAP_REP}.\n"
    )
    if soort == "fartlek":
        blok = (
            f"- 4m {pace_range(subt)}\n- 1m 5:00/km Pace\n"
            f"- 3m {pace_range(subt - 3)}\n- 1m 5:00/km Pace\n"
            f"- 2m {pace_range(subt - 6)}\n- 2m 5:30/km Pace\n\n"
        )
        main = f"{n}x\n{blok}"
        werk_min = n * 9
        duur = 15 + 4 + n * 13 + 10
        naam = f"Fartlek bos {n}x (4-3-2 min)"
        uitleg = "FARTLEK op gevoel in bos/park: de pace is indicatie (terrein!)."
    elif soort == "duur":
        lang, kort = n, werk
        lo, hi = a.easy_range
        main = (
            f"- 15m {_easy(a)}\n"
            f"- {lang}m {pace_range(subt + 3)}\n"
            f"- 3m {pace(hi)}/km Pace\n"
            f"- {kort}m {pace_range(subt - 4)}\n\n"
        )
        werk_min = lang + kort
        duur = 15 + 4 + 15 + lang + 3 + kort + 10
        naam = f"Duurloop met sub-T blok {lang} + {kort} min"
        uitleg = "Aaneengesloten sub-T: houdbaarheid op snelheid, het korte blok iets scherper."
    else:
        main = f"{n}x\n- {_dur(werk)} {pace_range(subt)}\n- {_dur(rust)} 6:00/km Pace\n\n"
        werk_min = n * werk / 60
        duur = 15 + 4 + round(n * (werk + rust) / 60) + 10
        naam = f"Sub-drempel - {n}x {_dur_label(werk)} @ {pace(subt)}"
        uitleg = OP_TIJD
    body = (
        f"{kop}{uitleg}\n\n{STURING}\n\n"
        + _warmup(a, a.vvo2_sec - 15)
        + "Main Set\n" + main
        + _cooldown(a)
    )
    intensity = 0.80 + min(werk_min, 40) / 400
    return _session("Run", "run_subthreshold", naam, body, duur, intensity, "Z3 sub-drempel")


# ── RACETEMPO (W3: race_pace) ─────────────────────────────────────────────

RACE_PACE_LADDER = [(3, 480, 120), (4, 480, 120), (3, 720, 150), (2, 960, 180)]


def race_pace_run(step: int, race_pace_sec: int, a: Anchors, race_label: str = "de race") -> dict:
    n, werk, rust = RACE_PACE_LADDER[min(max(step, 1), len(RACE_PACE_LADDER)) - 1]
    body = (
        f"RACETEMPO (pijler LT). Racetempo {race_label} voelen. {OP_TIJD}\n\n"
        f"{STURING}\n\n"
        + _warmup(a, a.vvo2_sec - 15)
        + "Main Set\n"
        f"{n}x\n- {_dur(werk)} {pace_range(race_pace_sec, 2)}\n- {_dur(rust)} 6:00/km Pace\n\n"
        + _cooldown(a)
    )
    duur = 15 + 4 + round(n * (werk + rust) / 60) + 10
    naam = f"Racetempo {n}x {_dur_label(werk)} @ {pace(race_pace_sec)}"
    return _session("Run", "race_pace", naam, body, duur, 0.86, "Z4 racetempo")


# ── EASY + SNELHEIDSRESERVE (W3: asr als aanhangsel) ──────────────────────

def easy_run_asr(minutes: int, variant: int, a: Anchors) -> dict:
    """Easy run met het wekelijkse snelheidsmoment (vliegers/heuvelsprints/loopscholing)."""
    vlieger = round(a.vvo2_sec * 0.86)
    keuze = variant % 3
    if keuze == 0:
        count = 6 if minutes < 50 else 8
        extra = (
            "Snelheid (vliegers op GRAS) - 30 m aanlopen, 100 m vliegend, wandelend terug\n"
            f"{count}x\n- 20s {pace(vlieger - 5)}-{pace(vlieger + 5)}/km Pace\n- 2m 7:00/km Pace\n"
        )
        naam = f"Easy {minutes} min + {count} vliegers"
        asr_min = count * 2.3
    elif keuze == 1:
        count = 4 if minutes < 50 else 6
        extra = (
            "Loopscholing (10 min): skippings, hakken-billen, huppelpas, 2x per oefening 30 m.\n\n"
            f"{count}x\n- 20s {pace(vlieger - 5)}-{pace(vlieger + 5)}/km Pace\n- 2m 7:00/km Pace\n"
        )
        naam = f"Easy {minutes} min + loopscholing + {count} vliegers"
        asr_min = 10 + count * 2.3
    else:
        count = 6 if minutes < 50 else 8
        extra = (
            "Heuvelsprints (X) - steil stuk/brug, volledig herstel, rustig terug\n"
            f"{count}x\n- 15s max heuvel op (ontspannen snel)\n- 2m 7:00/km Pace\n"
        )
        naam = f"Easy {minutes} min + {count} heuvelsprints"
        asr_min = count * 2.25
    easy_min = max(20, round(minutes - asr_min))
    body = (
        "EASY + SNELHEID (support + pijler economy). Het wekelijkse snelheidsmoment: "
        "kort, echt snel, volledig herstel. Geen vermoeidheid opbouwen. Easy deel onder 145 bpm.\n\n"
        f"Main Set\n- {easy_min}m {_easy(a)}\n\n{extra}"
    )
    return _session("Run", "easy_asr", naam, body, minutes, 0.72, "Z2 + snelheid")


# ── LONG RUN (W5) ─────────────────────────────────────────────────────────

LONG_RUN_MINUTES = [75, 80, 85, 90, 90, 90]


def long_run_block(minutes: int, variant: int, a: Anchors) -> dict:
    """Z2 75-90 min, roteert offroad / progressief / heuvelsprints. Geen MP."""
    keuze = variant % 3
    lo, hi = a.easy_range
    if keuze == 0:
        body = (
            "LONG RUN (aerobe basis). OFFROAD: bos, duin of gravel - zachte ondergrond, "
            "op gevoel, onder 145 bpm. Tijd op de benen, geen tempo.\n\n"
            f"Main Set\n- {minutes}m {_easy(a)}"
        )
        naam = f"Long {minutes} min offroad"
        intensity = 0.72
    elif keuze == 1:
        eind1 = pace_from_pct(a.threshold_sec, 100 / 1.15)
        eind2 = pace_from_pct(a.threshold_sec, 100 / 1.10)
        basis = minutes - 20
        body = (
            "LONG RUN (aerobe basis). PROGRESSIEF: de laatste 15 min naar drempel -10%. "
            "Leert versnellen op vermoeide benen.\n\n"
            f"Main Set\n- {basis}m {_easy(a)}\n"
            f"- 8m {pace_range(eind1)}\n"
            f"- 7m {pace_range(eind2)}\n"
            "- 5m 5:30/km Pace"
        )
        naam = f"Long {minutes} min progressief"
        intensity = 0.75
    else:
        count = 6 if minutes < 85 else 8
        sprint_sec = 30 if minutes < 85 else 40
        rest = minutes - 20 - round(count * (sprint_sec + 120) / 60)
        body = (
            "LONG RUN (aerobe basis). Heuvelsprints = snelheidsreserve + heupkracht. Bergaf rustig.\n\n"
            f"Warmup\n- 20m {_easy(a)}\n\n"
            "Heuvelsprints (X) - steil stuk/brug, rustig teruglopen\n"
            f"{count}x\n- {sprint_sec}s {pace(a.vvo2_sec - 15)}-{pace(a.vvo2_sec)}/km Pace\n- 2m 6:30/km Pace\n\n"
            f"Main Set\n- {max(15, rest)}m {_easy(a)}"
        )
        naam = f"Long {minutes} min + {count}x {sprint_sec}s heuvel"
        intensity = 0.74
    return _session("Run", "long_run_block", naam, body, minutes, intensity, "Z2")


# ── KALIBRATIE (REN-06: 6-min vVO2 voor en na elk blok) ──────────────────

def calibration_run(a: Anchors) -> dict:
    body = (
        "KALIBRATIE vVO2 (6 minuten). Geen test om te halen: een meting. Gewone dag, "
        "gewone schoen (geen carbon), vlak parcours zonder bochten of verkeer. 6 minuten zo "
        "hard als je ze GELIJKMATIG volhoudt - de afstand / 360 s is je nieuwe vVO2-pace. "
        "Noteer afstand + gevoel in de feedback.\n\n"
        f"Warmup\n- 20m {_easy(a)}\n\n"
        f"4x\n- 20s {pace(a.vvo2_sec - 10)}/km Pace\n- 40s 6:00/km Pace\n\n"
        "- 3m 6:00/km Pace\n\n"
        f"Main Set\n- 6m {pace_range(a.vvo2_sec)}\n\n"
        + _cooldown(a, 15)
    )
    return _session("Run", "calibration_vvo2", "Kalibratie vVO2 - 6 min", body, 48, 0.82,
                    "Z5 kalibratie")


# ── OPENERS (W7: dag(en) voor een A/B-race) ───────────────────────────────

def openers(race_pace_sec: int, a: Anchors) -> dict:
    body = (
        "EASY (support). Laatste run voor de race: kort, losse benen, racetempo even voelen. "
        "Onder 145 bpm buiten de versnellingen.\n\n"
        f"Main Set\n- 20m {_easy(a)}\n\n"
        f"4x\n- 1m {pace_range(race_pace_sec, 2)}\n- 1m 6:00/km Pace\n\n"
        f"4x\n- 20s {pace(a.vvo2_sec - 5)}/km Pace\n- 40s 6:00/km Pace"
    )
    return _session("Run", "openers", f"Openers 35 min + 4x1 min @ {pace(race_pace_sec)}",
                    body, 35, 0.72, "Z2 + openers")


# ── FIETS SUB-DREMPEL (W4: derde drempelprikkel) ──────────────────────────

BIKE_SUBT_LADDER = [
    (3, 10, 88, 90), (3, 12, 88, 90), (3, 12, 90, 92),
    (2, 18, 88, 90), (3, 14, 90, 92), (2, 20, 90, 92),
]


def bike_subthreshold(step: int, ftp: int, taper: bool = False) -> dict:
    sets, work, lo, hi = BIKE_SUBT_LADDER[min(max(step, 1), len(BIKE_SUBT_LADDER)) - 1]
    if taper:
        sets, work = 2, 12
    w_lo, w_hi = round(ftp * lo / 100 / 5) * 5, round(ftp * hi / 100 / 5) * 5
    body = (
        "FIETS SUB-DREMPEL (3e drempelprikkel, ontziet de heup). "
        f"{sets}x{work} min @ {w_lo}-{w_hi}W (~{lo}-{hi}% FTP). Hoort de dag NA een "
        "lopende kwaliteitssessie, nooit de dag ervoor.\n\n"
        "Warmup\n- 15m 150-200w\n\n"
        f"Main Set\n{sets}x\n- {work}m {w_lo}-{w_hi}w\n- 3m 150w\n\n"
        "Cooldown\n- 10m 140w"
    )
    duur = 15 + sets * (work + 3) + 10
    return _session("VirtualRide", "bike_subt", f"Fiets sub-drempel {sets}x{work} @ {w_lo}-{w_hi}W",
                    body, duur, 0.80, "Z3/Z4 sub-drempel")


def bike_easy(minutes: int, zone: str = "Z2") -> dict:
    if zone == "Z1":
        body = f"Herstel/doorspoelen. Rust mag ook.\n\n- {minutes}m Z1"
        naam = f"Z1 fiets {minutes} min (of rust)"
        intensity = 0.55
    else:
        body = f"Aerobe basis zonder impact.\n\n- 10m Z1\n- {minutes - 15}m Z2\n- 5m Z1"
        naam = f"Z2 fiets {minutes} min (of rust)"
        intensity = 0.65
    return _session("VirtualRide", "bike_easy", naam, body, minutes, intensity, zone)
