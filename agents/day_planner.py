"""Day planner — availability-first dagtoewijzing voor week-sessies.

Regels in tiers (afgestemd met gebruiker 2026-04-21):

TIER 1 — Heilig (nooit breken; in best-effort skip je een sessie liever):
- T1a: Nooit 2 longs op dezelfde dag (overtraining / blessure).
- T1b: Runs nooit back-to-back (alleen als `runs_back_to_back_ok=False`).
       Zodra de atleet weer fit is mag deze op True; dan zakt 'ie naar Tier 3.
- T1c: Long moet binnen avail (incl. tolerance) passen.

TIER 2 — Sterk (in best-effort: plaats tóch + warning; strict raist):
- T2a: Hards ≥1 dag uit elkaar van andere hard/long.
- T2b: Long op hoogste-avail dag (warnen als long op krappe dag landt).

TIER 3 — Voorkeur (stil bijsturen, geen warning):
- T3a: Longs bij voorkeur niet adjacent (allow_adjacent_longs=True default).
- T3b: Brick (run+bike zelfde dag) op pre-occupied dagen.
- T3c: Min avail: hard ≥ 60, easy ≥ 30 (best-effort laat dit los).

TIER 4 — Vulling op lege dagen (zie fill_empty_days_with_easy_bikes).

Bij strict=True raist elke violation SchedulingConflict. Voor dagelijks gebruik
staat strict=False: Tier-1-violations → skip, Tier-2 → place + warn.
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
    """Kan sessies niet plaatsen binnen harde regels (Tier 1/2 in strict mode)."""

    def __init__(self, reason: str, unplaced: list[dict], partial: list[dict],
                 suggestion: Optional[str] = None):
        super().__init__(reason)
        self.reason = reason
        self.unplaced = unplaced
        self.partial = partial
        self.suggestion = suggestion


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
    """Runs op 2 opeenvolgende dagen of 2 runs same-day (T1b / T3c)."""
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
    """Hard adjacent aan andere hard/long of same-day (T2a)."""
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


def suggest_fix(conflict: SchedulingConflict,
                week_avail_by_dag: dict[str, int]) -> str:
    """Stel een pragmatische fix voor bij een SchedulingConflict.

    Kijkt naar unplaced sessies + avail-verdeling en suggereert:
    - schrap easy sessie
    - verhoog avail op rustdag
    - verplaats long naar later in de week
    """
    unplaced = conflict.unplaced or []
    if not unplaced:
        return "Geen actie — partial plan is bruikbaar zoals het is."

    # Avail-overzicht
    zero_days = [d for d in DAYS_NL if not week_avail_by_dag.get(d)]
    top_day, top_val = (_rank_days(week_avail_by_dag) or [("maandag", 0)])[0]

    has_unplaced_long = any(classify_intensity(s) == "long" for s in unplaced)
    has_unplaced_hard = any(classify_intensity(s) == "hard" for s in unplaced)
    has_unplaced_easy = any(classify_intensity(s) == "easy" for s in unplaced)

    tips: list[str] = []
    if has_unplaced_long:
        if zero_days:
            tips.append(
                f"Zet {zero_days[0]} op ≥{MIN_AVAIL_LONG} min — dan past de lange sessie."
            )
        else:
            tips.append(
                f"Maak minstens één dag vrij (avail ≥{MIN_AVAIL_LONG}) voor de lange sessie."
            )
    if has_unplaced_hard:
        tips.append(
            "Kans op te weinig spacing: schrap één easy of schuif hard naar een andere dag."
        )
    if has_unplaced_easy:
        tips.append(
            "Schrap de kortste easy (minst impact op trainingseffect)."
        )
    tips.append(
        f"Top-avail dag nu: {top_day} ({top_val} min). "
        "Check of dat klopt met je agenda."
    )
    return " · ".join(tips)


def plan_days(
    sessions: list[dict],
    week_avail_by_dag: dict[str, int],
    week_start: date,
    *,
    allow_adjacent_longs: bool = True,
    runs_back_to_back_ok: bool = False,
    strict: bool = False,
) -> tuple[list[dict], list[dict]]:
    """Plaats sessies op dagen volgens de tier-regels (zie module docstring).

    Returns:
        (placed_sessions, warnings) tuple.
        - placed_sessions: sessies met dag + datum gezet.
        - warnings: lijst van {"tier", "code", "dag", "sessie", "message"}.
          In best-effort mode bevat deze Tier-2 violations die we toch accepteerden.
          In strict mode is deze lijst meestal leeg (conflicten raisen ipv warnen).

    Args:
        sessions: run + bike sessies (bestaand `dag`-veld wordt overschreven).
        week_avail_by_dag: {"maandag": 60, ...} — 0 = rustdag.
        week_start: maandag-datum van de week.
        allow_adjacent_longs: False = strict hardfail bij 2 longs adjacent.
        runs_back_to_back_ok: True = runs MAG back-to-back (Tier 3, stil).
                              False (default) = runs NOOIT back-to-back (Tier 1, skip).
        strict: True = raise SchedulingConflict bij elke tier-violation.

    Raises:
        SchedulingConflict: alleen in strict mode.
    """
    warnings: list[dict] = []

    longs = [s for s in sessions if classify_intensity(s) == "long"]
    hards = [s for s in sessions if classify_intensity(s) == "hard"]
    easys = [s for s in sessions if classify_intensity(s) == "easy"]

    placements: dict[str, list[dict]] = {d: [] for d in DAYS_NL}

    # ── T1c + T1a: longs eerst op hoogst-avail dagen ────────────────────────
    # Run-longs eerst zodat bike-longs op evt. adjacent dag landen — runs
    # blokkeren downstream run-plaatsing, bikes niet. Binnen sport: langst eerst.
    longs_sorted = sorted(
        longs,
        key=lambda s: (0 if _sport_class(s) == "run" else 1,
                       -(s.get("duur_min") or 0)),
    )
    ranked = _rank_days(week_avail_by_dag)

    placed_long: list[dict] = []
    unplaced_long: list[dict] = []
    for lng in longs_sorted:
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
        # Best-effort: laat avail-eis + adjacency los; NOOIT 2 longs same day (T1a).
        if not pool:
            pool = [(d, v) for d, v in ranked if not _has_long(d, placements)]
        if not pool:
            # Geen dag zonder long — absolute Tier-1: skip.
            continue
        dag, avail_on_dag = pool[0]
        placed = _set_day(lng, dag, week_start)
        placements[dag].append(placed)
        placed_long.append(placed)

        # T2b: long past niet (duur > avail + tol)? Tier-2 warning.
        duur = lng.get("duur_min") or 0
        if duur > avail_on_dag + AVAIL_TOLERANCE:
            warnings.append({
                "tier": 2,
                "code": "long_over_avail",
                "dag": dag,
                "sessie": lng.get("naam"),
                "message": (
                    f"Lange sessie '{lng.get('naam')}' ({duur} min) op {dag} — "
                    f"avail is {avail_on_dag} min. Wordt mogelijk ingekort."
                ),
            })

    if strict and unplaced_long:
        c = SchedulingConflict(
            reason=(f"Kan {len(unplaced_long)} lange sessie(s) niet plaatsen — "
                    f"onvoldoende dagen met ≥{MIN_AVAIL_LONG} min avail."),
            unplaced=unplaced_long,
            partial=[s for ss in placements.values() for s in ss],
        )
        c.suggestion = suggest_fix(c, week_avail_by_dag)
        raise c

    # ── T2a: hards met spacing ──────────────────────────────────────────────
    hards_sorted = sorted(hards, key=lambda s: -(s.get("duur_min") or 0))
    unplaced_hard: list[dict] = []
    for hrd in hards_sorted:
        strict_pool = [(d, v) for d, v in ranked
                       if _space_left(d, placements, v) >= _min_avail_for("hard")
                       and _fits(hrd, _space_left(d, placements, v))
                       and not _placement_violates_hard_spacing(hrd, d, placements)]
        if strict_pool:
            pool = sorted(strict_pool, key=lambda x: (len(placements[x[0]]), -x[1]))
            dag = pool[0][0]
            placed = _set_day(hrd, dag, week_start)
            placements[dag].append(placed)
            continue

        if strict:
            unplaced_hard.append(hrd)
            continue

        # Best-effort Tier-2: probeer spacing-vrije dag (avail-eis gelost).
        relaxed_pool = [
            (d, v) for d, v in ranked
            if not _placement_violates_hard_spacing(hrd, d, placements)
        ]
        if relaxed_pool:
            pool = sorted(relaxed_pool, key=lambda x: (len(placements[x[0]]), -x[1]))
            dag = pool[0][0]
            placed = _set_day(hrd, dag, week_start)
            placements[dag].append(placed)
            continue

        # Geen spacing-vrije dag → T2a warning + plaats op beste resterende.
        any_day_pool = [(d, v) for d, v in ranked]
        if not any_day_pool:
            continue
        any_day_pool = sorted(any_day_pool, key=lambda x: (len(placements[x[0]]), -x[1]))
        dag = any_day_pool[0][0]
        placed = _set_day(hrd, dag, week_start)
        placements[dag].append(placed)
        warnings.append({
            "tier": 2,
            "code": "hard_no_spacing",
            "dag": dag,
            "sessie": hrd.get("naam"),
            "message": (
                f"Harde sessie '{hrd.get('naam')}' op {dag} zonder 1 dag tussen "
                f"andere hard/long — let op herstel of verschuif handmatig."
            ),
        })

    if strict and unplaced_hard:
        c = SchedulingConflict(
            reason=(f"Kan {len(unplaced_hard)} harde sessie(s) niet plaatsen — "
                    f"geen dagen met ≥{MIN_AVAIL_HARD} min en afstand van long/hard."),
            unplaced=unplaced_hard,
            partial=[s for ss in placements.values() for s in ss],
        )
        c.suggestion = suggest_fix(c, week_avail_by_dag)
        raise c

    # ── T1b (of T3c) + T3b: easy sessies; bricks op pre-occupied dagen ──────
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
        # Best-effort: laat avail-eis + fits los.
        pool = strict_pool or [
            (d, v) for d, v in ranked
            if not _placement_violates_run_adjacency(es, d, placements)
        ]
        if not pool and runs_back_to_back_ok and _sport_class(es) == "run":
            # Tier-3 stil: atleet is fit, back-to-back runs mogen.
            pool = [(d, v) for d, v in ranked if not _has_run(d, placements)]
            # Same-day 2 runs blijft wel heilig.
        if not pool:
            # Geen plek zonder back-to-back — skip (T1b heilig bij default).
            continue

        def _brick_score(item):
            d, v = item
            return (0 if placements[d] else 1, len(placements[d]), -v)
        pool = sorted(pool, key=_brick_score)
        dag = pool[0][0]
        placed = _set_day(es, dag, week_start)
        placements[dag].append(placed)

    if strict and unplaced_easy:
        c = SchedulingConflict(
            reason=(f"Kan {len(unplaced_easy)} easy sessie(s) niet plaatsen "
                    f"zonder back-to-back runs."),
            unplaced=unplaced_easy,
            partial=[s for ss in placements.values() for s in ss],
        )
        c.suggestion = suggest_fix(c, week_avail_by_dag)
        raise c

    return [s for ss in placements.values() for s in ss], warnings


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
