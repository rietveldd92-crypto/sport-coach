"""Day planner — availability-first dagtoewijzing voor week-sessies.

Harde regels (volgorde van toepassing):
R1. Long sessies (>100 min) op dagen met de meeste beschikbaarheid.
R2. Hard sessies met ≥1 dag afstand van andere hard EN van long.
R3. Easy runs op resterende dagen; nooit 2 runs achter elkaar.
R4. Voorkeur: longs niet back-to-back; toegestaan als het niet anders kan.
R5. Brick (run + bike zelfde dag) op dagen die na initial placement al iets
    hebben én waar ruimte is voor de extra sessie.

Bij onoplosbaar conflict: raise SchedulingConflict met reden + unplaced.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

DAYS_NL = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"]

# Drempels en tolerantie (afgestemd met gebruiker 2026-04-20)
LONG_DUUR_MIN = 100     # duur > 100 min = long
MIN_AVAIL_LONG = 90     # long vereist ≥ 90 min avail
MIN_AVAIL_HARD = 60     # hard vereist ≥ 60 min avail
MIN_AVAIL_EASY = 30     # easy vereist ≥ 30 min avail
AVAIL_TOLERANCE = 10    # sessie mag tot 10 min over de avail gaan (65 op 60 is OK)

HARD_TYPE_KEYWORDS = (
    "threshold", "sweetspot", "sweet_spot", "vo2", "interval",
    "tempo", "over_unders", "over-unders", "cp_intervals", "drempel",
    "pyramide", "pyramid", "microburst", "tabata", "race_sim",
    "marathon_tempo", "tempoduurloop", "tempo_sandwich", "tempo_blocks",
)


class SchedulingConflict(Exception):
    """Kan sessies niet plaatsen binnen harde regels."""

    def __init__(self, reason: str, unplaced: list[dict], partial: list[dict]):
        super().__init__(reason)
        self.reason = reason
        self.unplaced = unplaced
        self.partial = partial


def classify_intensity(session: dict) -> str:
    """Return 'long' | 'hard' | 'easy'.

    Long heeft voorrang op hard: een 120min marathon-tempo-run is functioneel
    een lange sessie voor scheduling-doeleinden (plaatsing op avail-dag).
    """
    duur = session.get("duur_min") or 0
    if duur > LONG_DUUR_MIN:
        return "long"
    blob = f"{(session.get('type') or '').lower()} {(session.get('naam') or '').lower()}"
    if any(k in blob for k in HARD_TYPE_KEYWORDS):
        return "hard"
    return "easy"


def _sport_class(session: dict) -> str:
    sport = (session.get("sport") or "").lower()
    if sport in ("ride", "virtualride"):
        return "bike"
    if sport == "run":
        return "run"
    return "other"


def _fits(session: dict, avail: int) -> bool:
    """True als sessie in de beschikbare tijd past (met tolerantie)."""
    dur = session.get("duur_min") or 0
    return dur <= avail + AVAIL_TOLERANCE


def _min_avail_for(cls: str) -> int:
    return {"long": MIN_AVAIL_LONG, "hard": MIN_AVAIL_HARD, "easy": MIN_AVAIL_EASY}[cls]


def _rank_days(week_avail_by_dag: dict[str, int]) -> list[tuple[str, int]]:
    """Dagen gesorteerd op avail desc, rest-dagen (0) uitgesloten."""
    items = [(d, v) for d, v in week_avail_by_dag.items() if v > 0]
    items.sort(key=lambda x: (-x[1], DAYS_NL.index(x[0])))
    return items


def _day_idx(dag: str) -> int:
    return DAYS_NL.index(dag)


def _adjacent(dag_a: str, dag_b: str) -> bool:
    return abs(_day_idx(dag_a) - _day_idx(dag_b)) == 1


def _space_left(dag: str, placements: dict[str, list[dict]], avail: int) -> int:
    used = sum((s.get("duur_min") or 0) for s in placements.get(dag, []))
    return max(0, avail - used)


def _set_day(session: dict, dag: str, week_start: date) -> dict:
    session = dict(session)
    session["dag"] = dag
    session["datum"] = (week_start + timedelta(days=_day_idx(dag))).isoformat()
    return session


def _has_run(dag: str, placements: dict[str, list[dict]]) -> bool:
    return any(_sport_class(s) == "run" for s in placements.get(dag, []))


def _has_hard(dag: str, placements: dict[str, list[dict]]) -> bool:
    return any(classify_intensity(s) == "hard" for s in placements.get(dag, []))


def _has_long(dag: str, placements: dict[str, list[dict]]) -> bool:
    return any(classify_intensity(s) == "long" for s in placements.get(dag, []))


def _placement_violates_run_adjacency(sessie: dict, dag: str,
                                       placements: dict[str, list[dict]]) -> bool:
    """Runs niet op 2 opeenvolgende dagen én niet 2 runs op dezelfde dag (R3)."""
    if _sport_class(sessie) != "run":
        return False
    if _has_run(dag, placements):
        return True
    idx = _day_idx(dag)
    for n_idx in (idx - 1, idx + 1):
        if 0 <= n_idx < 7 and _has_run(DAYS_NL[n_idx], placements):
            return True
    return False


def _placement_violates_hard_spacing(sessie: dict, dag: str,
                                      placements: dict[str, list[dict]]) -> bool:
    """Hards niet adjacent aan andere hard/long, ook niet same-day (R2)."""
    if classify_intensity(sessie) != "hard":
        return False
    if _has_hard(dag, placements) or _has_long(dag, placements):
        return True
    idx = _day_idx(dag)
    for n_idx in (idx - 1, idx + 1):
        if 0 <= n_idx < 7:
            n = DAYS_NL[n_idx]
            if _has_hard(n, placements) or _has_long(n, placements):
                return True
    return False


def plan_days(
    sessions: list[dict],
    week_avail_by_dag: dict[str, int],
    week_start: date,
    *,
    allow_adjacent_longs: bool = True,
    strict: bool = False,
) -> list[dict]:
    """Plaats sessies op dagen volgens R1–R5.

    Default = best-effort: relaxet regels als strict-placement onmogelijk is.
    Caller (week_planner) moet daarna evt. per-dag cappen want een long kan
    op een krappe dag landen.

    `strict=True` = raise SchedulingConflict zodra een regel niet past
    (behouden voor tests/expliciete validatie).

    Args:
        sessions: run + bike sessies (dag-veld wordt genegeerd/overschreven).
        week_avail_by_dag: {"maandag": 60, ...} — 0 = rustdag, >0 = avail.
        week_start: maandag-datum van de te plannen week.
        allow_adjacent_longs: als False, hardfail bij 2 longs naast elkaar (strict mode).
        strict: raise SchedulingConflict ipv relaxen.

    Returns:
        Sessies met dag + datum ingevuld. Volgorde niet gegarandeerd.
    """
    longs = [s for s in sessions if classify_intensity(s) == "long"]
    hards = [s for s in sessions if classify_intensity(s) == "hard"]
    easys = [s for s in sessions if classify_intensity(s) == "easy"]

    placements: dict[str, list[dict]] = {d: [] for d in DAYS_NL}
    day_avail = dict(week_avail_by_dag)

    # ── R1: longs eerst op hoogst-avail dagen ───────────────────────────────
    # Run-longs eerst zodat bike-longs op evt. adjacent dag landen — runs
    # blokkeren downstream run-plaatsing, bikes niet. Binnen sport: langst eerst.
    longs_sorted = sorted(
        longs,
        key=lambda s: (0 if _sport_class(s) == "run" else 1,
                       -(s.get("duur_min") or 0)),
    )
    ranked = _rank_days(day_avail)

    placed_long: list[dict] = []
    unplaced_long: list[dict] = []
    for lng in longs_sorted:
        # Strict: ≥ min_avail, past, geen 2e long op zelfde dag, niet adjacent.
        strict_pool = [(d, v) for d, v in ranked
                       if _space_left(d, placements, v) >= max(_min_avail_for("long"),
                                                                (lng.get("duur_min") or 0) - AVAIL_TOLERANCE)
                       and _fits(lng, _space_left(d, placements, v))
                       and not _has_long(d, placements)]
        non_adjacent = [
            (d, v) for d, v in strict_pool
            if not any(_adjacent(d, pd) for pd in [s["dag"] for s in placed_long])
        ]
        pool = non_adjacent or (strict_pool if allow_adjacent_longs else [])
        if not pool and strict:
            unplaced_long.append(lng)
            continue
        # Best-effort: laat alleen avail-eis + adjacency los; NOOIT 2 longs same day.
        if not pool:
            pool = [(d, v) for d, v in ranked if not _has_long(d, placements)]
        if not pool:
            # Geen dag zonder long — sla over (betere keuze dan stapelen).
            continue
        dag, _ = pool[0]
        placed = _set_day(lng, dag, week_start)
        placements[dag].append(placed)
        placed_long.append(placed)

    if strict and unplaced_long:
        raise SchedulingConflict(
            reason=(f"Kan {len(unplaced_long)} lange sessie(s) niet plaatsen — "
                    f"onvoldoende dagen met ≥{MIN_AVAIL_LONG} min avail."),
            unplaced=unplaced_long,
            partial=[s for ss in placements.values() for s in ss],
        )

    # ── R2: hards met spacing ───────────────────────────────────────────────
    hards_sorted = sorted(hards, key=lambda s: -(s.get("duur_min") or 0))
    unplaced_hard: list[dict] = []
    for hrd in hards_sorted:
        strict_pool = [(d, v) for d, v in ranked
                       if _space_left(d, placements, v) >= _min_avail_for("hard")
                       and _fits(hrd, _space_left(d, placements, v))
                       and not _placement_violates_hard_spacing(hrd, d, placements)]
        if not strict_pool and strict:
            unplaced_hard.append(hrd)
            continue
        # Best-effort: laat avail-eis + fits los, MAAR spacing blijft harde regel.
        pool = strict_pool or [
            (d, v) for d, v in ranked
            if not _placement_violates_hard_spacing(hrd, d, placements)
        ]
        if not pool:
            # Geen spacing-vrije dag — sla over (betere keuze dan stapelen).
            continue
        pool = sorted(pool, key=lambda x: (len(placements[x[0]]), -x[1]))
        dag = pool[0][0]
        placed = _set_day(hrd, dag, week_start)
        placements[dag].append(placed)

    if strict and unplaced_hard:
        raise SchedulingConflict(
            reason=(f"Kan {len(unplaced_hard)} harde sessie(s) niet plaatsen — "
                    f"geen dagen met ≥{MIN_AVAIL_HARD} min en afstand van long/hard."),
            unplaced=unplaced_hard,
            partial=[s for ss in placements.values() for s in ss],
        )

    # ── R3 + R5: easy sessies; bricks op pre-occupied high-avail dagen ──────
    easys_sorted = sorted(easys, key=lambda s: -(s.get("duur_min") or 0))
    unplaced_easy: list[dict] = []
    for es in easys_sorted:
        strict_pool = [(d, v) for d, v in ranked
                       if _space_left(d, placements, v) >= _min_avail_for("easy")
                       and _fits(es, _space_left(d, placements, v))
                       and not _placement_violates_run_adjacency(es, d, placements)]
        if not strict_pool and strict:
            unplaced_easy.append(es)
            continue
        # Best-effort: laat avail-eis + fits los, MAAR run-adjacency blijft
        # harde regel (nooit 2 runs zelfde dag, nooit runs op opeenvolgende dagen).
        pool = strict_pool or [
            (d, v) for d, v in ranked
            if not _placement_violates_run_adjacency(es, d, placements)
        ]
        if not pool:
            # Geen plek zonder back-to-back runs — sla over.
            continue

        def _brick_score(item):
            d, v = item
            return (0 if placements[d] else 1, len(placements[d]), -v)
        pool = sorted(pool, key=_brick_score)
        dag = pool[0][0]
        placed = _set_day(es, dag, week_start)
        placements[dag].append(placed)

    if strict and unplaced_easy:
        raise SchedulingConflict(
            reason=(f"Kan {len(unplaced_easy)} easy sessie(s) niet plaatsen "
                    f"zonder back-to-back runs."),
            unplaced=unplaced_easy,
            partial=[s for ss in placements.values() for s in ss],
        )

    return [s for ss in placements.values() for s in ss]


def fill_empty_days_with_easy_bikes(
    placed: list[dict],
    week_avail_by_dag: dict[str, int],
    week_start: date,
    ftp: int = 290,
    max_fills: int = 3,
) -> list[dict]:
    """Vul lege dagen (met avail ≥ 30) met een easy Z2 bike-sessie.

    Runs worden niet gebruikt (back-to-back regel + blessurerisico).
    Easy bike op lege dag = extra aerobe volume zonder spacing-conflicten.
    Tot `max_fills` extra sessies per week.

    Returns: placed + eventuele fill-sessies.
    """
    placements: dict[str, list[dict]] = {d: [] for d in DAYS_NL}
    for s in placed:
        placements.setdefault(s.get("dag"), []).append(s)

    # Lege dagen met voldoende avail, gesorteerd op avail desc
    empty = sorted(
        [(d, week_avail_by_dag.get(d, 0)) for d in DAYS_NL
         if not placements.get(d) and week_avail_by_dag.get(d, 0) >= MIN_AVAIL_EASY],
        key=lambda x: -x[1],
    )
    if not empty:
        return placed

    try:
        from agents import workout_library as lib
    except Exception:
        return placed

    additions: list[dict] = []
    for dag, avail in empty[:max_fills]:
        # Op high-avail dagen (≥120min) plaats een langere Z2 duurrit (tot 150min)
        # ipv het wegsmijten van 3 uur avail met een 60min filler.
        dur = min(avail, 150) if avail >= 120 else min(avail, 60)
        try:
            sessie = lib.endurance_ride(max(30, dur))
        except Exception:
            continue
        sessie["dag"] = dag
        sessie["datum"] = (week_start + timedelta(days=_day_idx(dag))).isoformat()
        sessie["naam"] = f"Aerobe vulling – {sessie.get('duur_min', dur)} min Z2"
        sessie["is_fill"] = True
        additions.append(sessie)

    return placed + additions
