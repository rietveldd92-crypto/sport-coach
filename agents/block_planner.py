"""Weekplanner voor 10k/5k-blokken (PLANLOGICA-V4, W2/W4/W6/W7).

Pure functie: krijgt de week-context binnen en levert geplaatste sessies
terug. Geen intervals.icu, geen state-writes — plan_week.py levert de
context aan en week_planner.build_week schrijft.

Regels:
- 4-3-4-3: om en om 4 en 3 runs per kalenderweek, NOOIT twee dagen
  achtereen lopen (ook niet over de weekgrens: zondag + maandag).
- Kwaliteit: 2 lopend (4-runweek) of 1 (3-runweek) uit de toolkit van het
  doeltype x gate, plus altijd 1 fiets-sub-drempel de dag NA een lopende
  kwaliteitssessie. ASR (vliegers/heuvelsprints) hangt aan de easy run.
- Long run 75-90 min Z2, roteert offroad / progressief / heuvelsprints.
- Racewoche (W7): de race is een key session en telt als run. Race <15 km
  vervangt een kwaliteitssessie (bij voorkeur sub-T, REN-37), race >=15 km
  ook de long run. A/B-race: taper (volume 70%, intensiteit blijft), de dag
  ervoor geen run, de laatste kwaliteit minstens 3 dagen ervoor.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from itertools import combinations

from agents import block_library as bl

DAYS_NL = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag",
           "zaterdag", "zondag"]
MIN_RUN_AVAIL = 40

# W2 — toolkit per doeltype x gate. Eerste categorie = primaire kwaliteit
# (de enige in een 3-runweek).
QUALITY_TOOLKIT: dict[str, dict[str, tuple[str, str]]] = {
    "10k": {
        "tempoduur": ("subthreshold", "vo2_run"),
        "drempel": ("vo2_run", "subthreshold"),
        "race_specifiek": ("race_pace", "subthreshold"),
    },
    "5k": {
        "tempoduur": ("subthreshold", "vo2_run"),
        "drempel": ("vo2_run", "subthreshold"),
        "race_specifiek": ("race_pace", "vo2_run"),
    },
    "half": {
        "tempoduur": ("subthreshold", "vo2_run"),
        "drempel": ("subthreshold", "vo2_run"),
        "race_specifiek": ("race_pace", "subthreshold"),
    },
}
BLOCK_GOAL_TYPES = tuple(QUALITY_TOOLKIT)

# Hoeveel weken vóór een race racetempo de primaire kwaliteit wordt. A-race:
# laatste 3 weken + de raceweek; B-race: alleen de raceweek; C: nooit.
RACE_SPECIFIC_WEEKS = {"A": 3, "B": 0}


@dataclass
class Race:
    datum: date
    naam: str
    distance_km: float
    priority: str = "C"           # A | B | C
    race_pace_sec: int | None = None


@dataclass
class BlockWeekContext:
    week_start: date
    goal_type: str
    run_count: int                       # 4 of 3 (patroon)
    availability: dict[str, int]         # dagnaam -> minuten
    ftp: int = 290
    macro_gate: str = "drempel"
    steps: dict = field(default_factory=dict)      # vo2/subt/long/bike/race_pace
    variety: int = 0
    races: list[Race] = field(default_factory=list)  # races deze week
    next_race: Race | None = None        # eerstvolgende A/B-race (ook na deze week)
    is_deload: bool = False
    intensity_open: bool = True
    prev_week_sunday_run: bool = False
    next_week_run_count: int = 4
    runs_back_to_back_ok: bool = False
    recovery_week: bool = False          # week na een A/B-race


# ── GATE + SLOTS ──────────────────────────────────────────────────────────

def block_gate(ctx: BlockWeekContext) -> str:
    """Gate van deze week: racetempo vlak voor een A/B-race, anders macroplan."""
    race = ctx.next_race
    if race is not None and race.priority in RACE_SPECIFIC_WEEKS:
        weeks_to = (race.datum - ctx.week_start).days // 7
        if 0 <= weeks_to <= RACE_SPECIFIC_WEEKS[race.priority]:
            return "race_specifiek"
    gate = ctx.macro_gate if ctx.macro_gate in ("tempoduur", "drempel", "race_specifiek") else "drempel"
    if gate == "race_specifiek":
        # Racetempo zonder race in zicht heeft geen doelpace: terug naar drempel.
        return "drempel"
    return gate


@dataclass
class _Slot:
    sessie: dict
    rol: str            # quality | easy | long | bike_subt | bike_fill | race
    categorie: str = ""


def build_slots(ctx: BlockWeekContext, anchors: bl.Anchors) -> tuple[list[_Slot], list[dict]]:
    warnings: list[dict] = []
    if ctx.recovery_week:
        return _recovery_slots(ctx, anchors), warnings
    toolkit = QUALITY_TOOLKIT.get(ctx.goal_type, QUALITY_TOOLKIT["10k"])
    gate = block_gate(ctx)
    categories = list(toolkit[gate])
    ab_race = next((r for r in ctx.races if r.priority in ("A", "B")), None)
    long_race = any(r.distance_km >= 15 for r in ctx.races)

    runs_to_plan = ctx.run_count - len(ctx.races)
    qualities = 1 if (ctx.run_count <= 3 or ctx.is_deload) else 2
    want_long = not long_race
    want_easy = True

    # Race vervangt de sub-T-sessie (REN-37), niet de VO2-run. Zit er geen
    # sub-T in de week, dan vervalt de easy run; >=15 km vervangt ook de long.
    if ab_race is not None:
        # Taper-raceweek: één kort kwaliteitsblok (racetempo) + openers.
        qualities = 1
        categories = ["race_pace"]
    else:
        for race in ctx.races:
            if "subthreshold" in categories[:qualities]:
                categories.remove("subthreshold")
                qualities -= 1
            elif want_easy:
                want_easy = False
            else:
                qualities = max(0, qualities - 1)

    n_other = (1 if want_long else 0) + (1 if want_easy else 0)
    while qualities + n_other > runs_to_plan and qualities > 0:
        qualities -= 1
    if qualities + n_other > runs_to_plan and want_easy:
        want_easy = False
        n_other -= 1
    if qualities + n_other > runs_to_plan and want_long:
        want_long = False

    if not ctx.intensity_open and qualities:
        warnings.append({"code": "block_intensity_closed",
                         "message": "Injury guard: kwaliteit vervangen door easy runs."})

    slots: list[_Slot] = []
    step = dict(ctx.steps)
    if ctx.is_deload:
        step = {k: max(1, int(v) - 1) for k, v in step.items()}
    taper = ab_race is not None

    for i in range(qualities):
        cat = categories[i % len(categories)]
        if not ctx.intensity_open:
            sessie = bl.easy_run_asr(45, ctx.variety + i, anchors)
            slots.append(_Slot(sessie, "easy"))
            continue
        sessie = _quality_session(cat, step, ctx, anchors, taper=taper)
        slots.append(_Slot(sessie, "quality", cat))

    if want_long:
        minutes = bl.LONG_RUN_MINUTES[min(max(int(step.get("long", 1)), 1), len(bl.LONG_RUN_MINUTES)) - 1]
        if ctx.is_deload or taper:
            minutes = round(minutes * 0.7 / 5) * 5
        slots.append(_Slot(bl.long_run_block(minutes, ctx.variety, anchors), "long"))

    if want_easy:
        if ab_race is not None:
            pace = ab_race.race_pace_sec or anchors.threshold_sec
            slots.append(_Slot(bl.openers(pace, anchors), "easy", "openers"))
        else:
            easy_min = 45 + 5 * min(3, max(0, int(step.get("long", 1)) - 1))
            if ctx.is_deload:
                easy_min = 40
            slots.append(_Slot(bl.easy_run_asr(easy_min, ctx.variety, anchors), "easy"))

    bike_step = int(step.get("bike", 1))
    slots.append(_Slot(bl.bike_subthreshold(bike_step, ctx.ftp, taper=taper or ctx.is_deload), "bike_subt"))
    fill = [bl.bike_easy(60, "Z2"), bl.bike_easy(45, "Z1"), bl.bike_easy(60, "Z2"), bl.bike_easy(40, "Z1")]
    if taper:
        fill = [bl.bike_easy(40, "Z1"), bl.bike_easy(30, "Z1")]
    slots.extend(_Slot(s, "bike_fill") for s in fill)
    return slots, warnings


def _recovery_slots(ctx: BlockWeekContext, anchors: bl.Anchors) -> list[_Slot]:
    """Herstelweek na een A/B-race: easy lopen, de 6-min kalibratie voor het
    vVO2-anker (REN-06), geen fiets-sub-T. Het volgende blok start daarna op
    trede 1."""
    slots = [
        _Slot(bl.calibration_run(anchors), "quality", "kalibratie"),
        _Slot(bl.long_run_block(60, 0, anchors), "long"),
    ]
    if ctx.run_count >= 3:
        slots.append(_Slot(bl.easy_run_asr(40, 1, anchors), "easy"))
    slots.extend(_Slot(s, "bike_fill") for s in
                 (bl.bike_easy(60, "Z2"), bl.bike_easy(45, "Z1"), bl.bike_easy(60, "Z2")))
    return slots


def _quality_session(cat: str, step: dict, ctx: BlockWeekContext, anchors: bl.Anchors,
                     *, taper: bool) -> dict:
    if cat == "vo2_run":
        return bl.vo2_run(int(step.get("vo2", 1)), ctx.variety, anchors)
    if cat == "race_pace":
        race = ctx.next_race
        pace = (race.race_pace_sec if race and race.race_pace_sec else anchors.threshold_sec)
        label = race.naam if race else "de race"
        rp_step = 1 if taper else int(step.get("race_pace", 1))
        return bl.race_pace_run(rp_step, pace, anchors, race_label=label)
    return bl.subthreshold_run(int(step.get("subt", 1)), ctx.variety, anchors)


# ── DAGPLAATSING ──────────────────────────────────────────────────────────

def _no_adjacent(days: tuple[int, ...]) -> bool:
    return all(b - a >= 2 for a, b in zip(days, days[1:]))


def choose_run_days(ctx: BlockWeekContext, slots: list[_Slot]) -> tuple[dict[int, _Slot], list[dict]]:
    """Kies de rundagen als set (geen twee aaneen) en verdeel daarna de rollen.

    Eerst de set, dan de rollen: een long run die als eerste op de 'beste'
    dag wordt gezet kan een 4-runweek onmogelijk maken (long op donderdag
    laat geen drie niet-aangrenzende dagen meer over).
    """
    warnings: list[dict] = []
    run_slots = [s for s in slots if (s.sessie.get("sport") or "").lower() == "run"]
    race_idx = {(r.datum - ctx.week_start).days for r in ctx.races}
    ab_race_idx = {(r.datum - ctx.week_start).days for r in ctx.races if r.priority in ("A", "B")}
    avail = [int(ctx.availability.get(d, 0) or 0) for d in DAYS_NL]

    blocked = set(race_idx)
    if ctx.prev_week_sunday_run and not ctx.runs_back_to_back_ok:
        blocked.add(0)
    candidates = [i for i in range(7) if i not in blocked and avail[i] >= MIN_RUN_AVAIL]

    n = len(run_slots)
    best = None
    while n > 0 and best is None:
        for combo in combinations(candidates, n):
            days = tuple(sorted(set(combo) | race_idx))
            if not ctx.runs_back_to_back_ok and not _no_adjacent(days):
                continue
            if any(i - 1 in ab_race_idx for i in combo):
                continue  # dag vóór een A/B-race: geen run
            score = _score_days(combo, ctx, avail, run_slots)
            if best is None or score > best[0]:
                best = (score, combo)
        if best is None:
            dropped = _least_important(run_slots)
            run_slots.remove(dropped)
            warnings.append({"code": "run_dropped_no_days",
                             "message": f"{dropped.sessie['naam']} vervalt: geen dag zonder aangrenzende run."})
            n -= 1
    if best is None:
        return {}, warnings
    return _assign_roles(best[1], run_slots, ctx, avail, race_idx), warnings


def _least_important(run_slots: list[_Slot]) -> _Slot:
    order = {"easy": 0, "quality": 1, "long": 2}
    # De tweede kwaliteit gaat eerder dan de long run, de easy run het eerst.
    qualities = [s for s in run_slots if s.rol == "quality"]
    easy = [s for s in run_slots if s.rol == "easy"]
    if easy:
        return easy[0]
    if len(qualities) > 1:
        return qualities[-1]
    return min(run_slots, key=lambda s: order.get(s.rol, 0))


def _score_days(combo: tuple[int, ...], ctx: BlockWeekContext, avail: list[int],
                run_slots: list[_Slot]) -> float:
    score = 0.0
    long_need = max((s.sessie["duur_min"] for s in run_slots if s.rol == "long"), default=0)
    if long_need:
        score += 3 if max(avail[i] for i in combo) >= long_need else -10
        if 5 in combo or 6 in combo:
            score += 2          # long run in het weekend mogelijk
    score += sum(min(avail[i], 120) for i in combo) / 120
    # Zondag lopen in een week vóór een 4-runweek dwingt volgende week een
    # run eruit (maandag is dan dicht).
    if 6 in combo and ctx.next_week_run_count >= 4 and ctx.run_count < 4:
        score -= 4
    return score


def _assign_roles(days: tuple[int, ...], run_slots: list[_Slot], ctx: BlockWeekContext,
                  avail: list[int], race_idx: set[int]) -> dict[int, _Slot]:
    free = list(days)
    out: dict[int, _Slot] = {}
    long_slot = next((s for s in run_slots if s.rol == "long"), None)
    if long_slot is not None:
        need = long_slot.sessie["duur_min"]
        fits = [d for d in free if avail[d] >= need] or free
        day = max(fits, key=lambda d: (d >= 5, avail[d], d))
        out[day] = long_slot
        free.remove(day)

    anchors = set(out) | race_idx
    for slot in [s for s in run_slots if s.rol == "quality"]:
        def spacing(d: int) -> tuple:
            dist = min((abs(d - o) for o in anchors), default=7)
            pre_race = min((r - d for r in race_idx if r > d), default=7)
            # Bij gelijke spreiding later in de week: dan blijft de dag na de
            # eerste kwaliteit vrij voor de fiets-sub-T (hard-dag-hard).
            return (pre_race >= 3, dist, avail[d], d)
        day = max(free, key=spacing)
        out[day] = slot
        free.remove(day)
        anchors.add(day)

    for slot in [s for s in run_slots if s.rol == "easy"]:
        if not free:
            break
        # Openers zo dicht mogelijk bij de race, gewone easy run met de meeste tijd.
        if slot.categorie == "openers" and race_idx:
            day = max(free, key=lambda d: (d < min(race_idx), d))
        else:
            day = max(free, key=lambda d: avail[d])
        out[day] = slot
        free.remove(day)
    return out


def plan_block_week(ctx: BlockWeekContext, anchors: bl.Anchors | None = None) -> tuple[list[dict], list[dict]]:
    """Bouw en plaats een volledige blokweek. Returnt (sessies, waarschuwingen)."""
    anchors = anchors or bl.load_anchors()
    slots, warnings = build_slots(ctx, anchors)
    run_days, w = choose_run_days(ctx, slots)
    warnings += w

    placed: dict[int, list[dict]] = {}

    def put(day: int, slot: _Slot, reason: str) -> None:
        sessie = dict(slot.sessie)
        sessie["dag"] = DAYS_NL[day]
        sessie["datum"] = (ctx.week_start + timedelta(days=day)).isoformat()
        sessie["plaatsing_reden"] = reason
        sessie["_skeleton_role"] = slot.rol
        placed.setdefault(day, []).append(sessie)

    for day, slot in sorted(run_days.items()):
        put(day, slot, _reason(slot, day))

    race_idx = {(r.datum - ctx.week_start).days for r in ctx.races}
    busy = set(run_days) | race_idx
    avail = [int(ctx.availability.get(d, 0) or 0) for d in DAYS_NL]
    quality_days = sorted(d for d, s in run_days.items() if s.rol == "quality")
    # De long run is Z2: fiets-sub-T ervoor mag. Kwaliteit en races niet.
    hard_run_days = set(quality_days) | race_idx

    subt = next((s for s in slots if s.rol == "bike_subt"), None)
    if subt is not None:
        day = _bike_subt_day(quality_days, busy, hard_run_days, avail, subt.sessie["duur_min"],
                             race_idx)
        if day is None:
            warnings.append({"code": "bike_subt_not_placed",
                             "message": "Fiets sub-drempel past niet: geen vrije dag na een kwaliteitssessie."})
        else:
            put(day, subt, "Fiets sub-T de dag na de lopende kwaliteit (hard-dag-hard).")
            busy.add(day)

    for slot in [s for s in slots if s.rol == "bike_fill"]:
        free = [d for d in range(7) if d not in busy and avail[d] >= 30]
        if not free:
            break
        day = max(free, key=lambda d: (avail[d], -d))
        sessie = dict(slot.sessie)
        if avail[day] < sessie["duur_min"]:
            sessie = bl.bike_easy(max(30, avail[day] // 5 * 5), "Z1" if "Z1" in sessie["naam"] else "Z2")
        put(day, _Slot(sessie, "bike_fill"), "Aerobe vulling op een vrije dag; rust mag ook.")
        busy.add(day)

    sessions = [s for day in sorted(placed) for s in placed[day]]
    return sessions, warnings


def _bike_subt_day(quality_days: list[int], busy: set[int], hard_run_days: set[int],
                   avail: list[int], need: int, race_idx: set[int]) -> int | None:
    def ok(d: int) -> bool:
        return (0 <= d < 7 and d not in busy and avail[d] >= min(need, 60)
                and d + 1 not in race_idx and d + 1 not in hard_run_days)
    for q in quality_days:
        if ok(q + 1):
            return q + 1
    # Terugval: vrije dag die niet vóór een harde run of race ligt.
    rest = [d for d in range(7) if ok(d)]
    return max(rest, key=lambda d: avail[d]) if rest else None


def _reason(slot: _Slot, day: int) -> str:
    dag = DAYS_NL[day]
    return {
        "long": f"Long run op {dag}: de dag met de meeste tijd, geen run ernaast.",
        "quality": f"Kwaliteit op {dag}: maximaal gespreid van long run en race.",
        "easy": f"Easy run op {dag}: om de dag lopen, geen run ernaast.",
    }.get(slot.rol, f"{dag}")


# ── CONTEXT-HELPERS (gebruikt door plan_week) ─────────────────────────────

def run_count_for_week(week_start: date, pattern: dict | None) -> int:
    """4-3-4-3: ``pattern = {"counts": [4, 3], "start": "2026-11-02"}``."""
    pattern = pattern or {}
    counts = pattern.get("counts") or [4, 3]
    start = pattern.get("start")
    if not start:
        return counts[0]
    start_d = date.fromisoformat(start)
    idx = (week_start - start_d).days // 7
    return int(counts[idx % len(counts)])


def effective_block_start(block_start: str | None, last_ab_race: date | None) -> date | None:
    """Een A/B-race sluit een blok af; na de herstelweek start het volgende."""
    start = date.fromisoformat(block_start) if block_start else None
    if last_ab_race is not None:
        race_monday = last_ab_race - timedelta(days=last_ab_race.weekday())
        after = race_monday + timedelta(days=14)
        if start is None or after > start:
            start = after
    return start


def block_steps(week_start: date, block_start: str | None, is_deload: bool = False,
                last_ab_race: date | None = None) -> dict:
    """Trede per ladder = blokweek (1 = eerste week van het blok), max 6.

    Bewust gekoppeld aan de bloksstart en niet aan het plan-weeknummer: dat
    herstart bij elke regeneratie van het macroplan.
    """
    start = effective_block_start(block_start, last_ab_race)
    if start is not None:
        week = (week_start - start).days // 7 + 1
    else:
        week = 1
    week = max(1, min(6, week))
    return {"vo2": week, "subt": week, "long": week, "bike": week, "race_pace": max(1, week - 2)}


def parse_time_seconds(value: str | None) -> int | None:
    """'38:00' -> 2280, '1:02:00' -> 3720; band '38:00-38:45' -> midden."""
    if not value:
        return None
    if "-" in str(value):
        lo, hi = (parse_time_seconds(p.strip()) for p in str(value).split("-", 1))
        if lo and hi:
            return round((lo + hi) / 2)
        return lo or hi
    try:
        parts = [int(p) for p in str(value).split(":")]
    except ValueError:
        return None
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return None


GOAL_DISTANCE_KM = {"5k": 5.0, "10k": 10.0, "15k": 15.0, "half": 21.0975, "marathon": 42.195}


def race_pace_for(goal_type: str, target_value: str | None, distance_km: float | None = None) -> int | None:
    seconds = parse_time_seconds(target_value)
    km = distance_km or GOAL_DISTANCE_KM.get(goal_type)
    if not seconds or not km:
        return None
    return round(seconds / km)
