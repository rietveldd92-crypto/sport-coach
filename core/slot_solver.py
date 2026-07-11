"""Slot solver — CP-SAT weekplaatsing van sessies in tijdvensters (Fase 1).

Vervangt de greedy tier-plaatsing van ``agents/day_planner.py``
(UPGRADE_PLAN §5). De zoekruimte is klein (≤ ~15 slots × ≤ 9 sessies),
dus exacte optimalisatie met OR-Tools CP-SAT.

Harde constraints (oude Tier 1 + context):
- sessieduur ≤ slotduur (+10 min tolerantie)
- max 1 long per dag; nooit 2 runs op dezelfde dag
- runs niet back-to-back (tenzij ``runs_back_to_back_ok``)
- indoor_only-slots: alleen VirtualRide/kracht; outdoor_only: geen VirtualRide
- ``locked`` placements zijn onaantastbaar
- injury-gate (``no_run_intensity``): harde run-sessies worden geweerd

Zachte kostentermen (oude T2/T3) — gewichten uit athlete_state key
``solver_weights``, defaults in :data:`DEFAULT_WEIGHTS`:

    hard_adjacent            50   hard-hard / hard-naast-long (ook same-day)
    long_not_widest          30   long niet op het ruimste venster
    long_adjacent            20   longs op aangrenzende dagen
    brick_same_day           15   run + bike op dezelfde dag
    strength_before_key_day  15   kracht daags vóór long/hard
    tight_margin             10   < 15 min marge in het venster
    move_per_day             25   verplaatsing t.o.v. current_plan, per dag
    long_not_morning          5   long niet in een ochtendvenster

Geen oplossing zonder een sessie te laten vallen → status INFEASIBLE,
met de beste relaxatie: drop-variabelen met hoge kost (easies sneuvelen
eerst), de overige sessies blijven geplaatst.
"""
from __future__ import annotations

from datetime import date as date_type, timedelta
from typing import Literal, Optional

from ortools.sat.python import cp_model
from pydantic import BaseModel, Field

# Hergebruik van de bestaande classificatie uit het tier-systeem.
from agents.day_planner import classify_intensity, _sport_class
from core.availability_v2 import Slot, to_hhmm, to_minutes

AVAIL_TOLERANCE = 10        # min die een sessie over het venster mag (legacy)
TIGHT_MARGIN_MIN = 15       # < 15 min marge = krap
MORNING_CUTOFF_MIN = 12 * 60
MAX_SOLVE_TIME_S = 5.0

DAYS_NL = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag",
           "zaterdag", "zondag"]

DEFAULT_WEIGHTS: dict[str, int] = {
    "hard_adjacent": 50,
    "long_not_widest": 30,
    "long_adjacent": 20,
    "brick_same_day": 15,
    "strength_before_key_day": 15,
    "tight_margin": 10,
    "move_per_day": 25,
    "long_not_morning": 5,
    # Tie-breaker: vaste opslag per verplaatste sessie, zodat één sessie
    # 2 dagen schuiven (55) wint van twee sessies elk 1 dag (60).
    "move_session_extra": 5,
}

# Drop-kosten: ver boven elke realistische som van zachte termen, zodat
# droppen écht laatste redmiddel is. Easies sneuvelen eerst.
DROP_COST = {"easy": 1000, "strength": 1200, "hard": 1500, "long": 2000}
DEFAULT_MAX_SESSIONS_PER_DAY = 2


def load_weights(state: Optional[dict] = None) -> dict[str, int]:
    """Gewichten: athlete_state key 'solver_weights' over de defaults."""
    weights = dict(DEFAULT_WEIGHTS)
    if state is None:
        try:
            from shared import load_state

            state = load_state()
        except Exception:
            state = {}
    raw = (state or {}).get("solver_weights") or {}
    for key, value in raw.items():
        if key in weights:
            try:
                weights[key] = int(value)
            except (TypeError, ValueError):
                pass
    return weights


def load_max_sessions_per_day(state: Optional[dict] = None) -> int:
    """Hard cap op run+bike-sessies per dag."""
    if state is None:
        try:
            from shared import load_state

            state = load_state()
        except Exception:
            state = {}
    raw = ((state or {}).get("preferences") or {}).get("max_sessions_per_day")
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return DEFAULT_MAX_SESSIONS_PER_DAY


def classify_session(session: dict) -> str:
    """'long' | 'hard' | 'easy' | 'strength' — bestaande logica + kracht."""
    sport = (session.get("sport") or "").lower()
    if sport in ("weighttraining", "strength", "kracht"):
        return "strength"
    return classify_intensity(session)


# ── MODELLEN ────────────────────────────────────────────────────────────────

class SolverOptions(BaseModel):
    strict: bool = False
    runs_back_to_back_ok: bool = False
    allow_adjacent_longs: bool = True
    no_run_intensity: bool = False  # injury-gate (YELLOW)
    max_sessions_per_day: Optional[int] = None
    max_time_s: float = MAX_SOLVE_TIME_S


class Placement(BaseModel):
    key: str
    naam: str
    date: date_type
    slot_start: str          # concrete starttijd "HH:MM"
    slot_end: str            # einde van het venster
    kind: str                # long|hard|easy|strength
    sport: str = ""
    score: float = 0.0       # zachte kosten toegeschreven aan deze sessie
    moved_days: int = 0
    notes: list[str] = Field(default_factory=list)


class DroppedSession(BaseModel):
    key: str
    naam: str
    kind: str
    reason: str


class SolveResult(BaseModel):
    status: Literal["OPTIMAL", "FEASIBLE", "INFEASIBLE"]
    placements: list[Placement]
    dropped: list[DroppedSession] = Field(default_factory=list)
    objective: float = 0.0
    notes: list[str] = Field(default_factory=list)


# ── INTERN ──────────────────────────────────────────────────────────────────

def _context_ok(sport_class: str, sport_raw: str, kind: str, context: str) -> bool:
    if context == "indoor_only":
        # Alleen indoor: VirtualRide en kracht.
        return sport_raw.lower() in ("virtualride", "weighttraining") or kind == "strength"
    if context == "outdoor_only":
        return sport_raw.lower() != "virtualride"
    return True


def _day_name(d: date_type) -> str:
    return DAYS_NL[d.weekday()]


def _and_var(model: cp_model.CpModel, a, b, name: str):
    """p == a AND b via lineaire constraints."""
    p = model.NewBoolVar(name)
    model.Add(p <= a)
    model.Add(p <= b)
    model.Add(p >= a + b - 1)
    return p


def _on_var(model: cp_model.CpModel, count, name: str):
    """b == (count >= 1)."""
    b = model.NewBoolVar(name)
    model.Add(count >= 1).OnlyEnforceIf(b)
    model.Add(count == 0).OnlyEnforceIf(b.Not())
    return b


def solve_week(
    sessions: list[dict],
    slots_by_date: dict[date_type, list[Slot]],
    *,
    options: Optional[SolverOptions] = None,
    weights: Optional[dict] = None,
    max_sessions_per_day: Optional[int] = None,
    current_plan: Optional[dict] = None,
    locked: Optional[set] = None,
) -> SolveResult:
    """Plaats sessies in slots met CP-SAT.

    Args:
        sessions: sessie-dicts (naam, duur_min, sport, type, evt. event_id).
        slots_by_date: output van availability_v2.get_slots_for_week.
        options: harde-regel-toggles (strict, runs b2b, injury-gate).
        weights: zachte gewichten; default uit athlete_state 'solver_weights'.
        current_plan: {key: (date, "HH:MM")} — referentie voor de
            verplaatsingsterm (25/sessie/dag) en voor locked-matching.
        locked: set van keys die op hun current_plan-positie MOETEN blijven.

    Returns:
        SolveResult. Bij INFEASIBLE bevatten ``placements`` de beste
        relaxatie en ``dropped`` de sessie(s) die sneuvelen.
    """
    options = options or SolverOptions()
    weights = {**DEFAULT_WEIGHTS, **(weights if weights is not None else load_weights())}
    max_per_day = (
        max_sessions_per_day
        if max_sessions_per_day is not None
        else options.max_sessions_per_day
    )
    if max_per_day is None:
        max_per_day = load_max_sessions_per_day()
    try:
        max_per_day = max(1, int(max_per_day))
    except (TypeError, ValueError):
        max_per_day = DEFAULT_MAX_SESSIONS_PER_DAY
    current_plan = dict(current_plan or {})
    locked = set(locked or [])

    days = sorted(slots_by_date.keys())
    flat_slots: list[dict] = []
    for d in days:
        for slot in sorted(slots_by_date.get(d) or [], key=lambda s: s.start_min):
            if slot.duration_min <= 0:
                continue
            flat_slots.append({
                "day": d,
                "start_min": slot.start_min,
                "end_min": slot.end_min,
                "dur": slot.duration_min,
                "context": slot.context,
            })
    widest = max((s["dur"] for s in flat_slots), default=0)

    # Sessies normaliseren; injury-gate direct afhandelen.
    prepared: list[dict] = []
    gated_drops: list[DroppedSession] = []
    for i, sess in enumerate(sessions):
        key = str(sess.get("event_id") or sess.get("id") or f"s{i}")
        kind = classify_session(sess)
        sport = _sport_class(sess)
        item = {
            "idx": len(prepared),
            "key": key,
            "naam": sess.get("naam") or sess.get("name") or key,
            "dur": int(sess.get("duur_min") or 0),
            "kind": kind,
            "sport": sport,
            "sport_raw": sess.get("sport") or "",
        }
        if options.no_run_intensity and sport == "run" and kind == "hard":
            gated_drops.append(DroppedSession(
                key=key, naam=item["naam"], kind=kind,
                reason="Injury-gate: loopintensiteit niet toegestaan (YELLOW)",
            ))
            continue
        prepared.append(item)

    if not flat_slots or not prepared:
        return SolveResult(
            status="INFEASIBLE" if (prepared and not flat_slots) else "OPTIMAL",
            placements=[],
            dropped=gated_drops + [
                DroppedSession(key=p["key"], naam=p["naam"], kind=p["kind"],
                               reason="Geen beschikbaarheidsvensters deze week")
                for p in (prepared if not flat_slots else [])
            ],
            notes=(["Geen vensters beschikbaar"] if prepared and not flat_slots else []),
        )

    model = cp_model.CpModel()

    # x[i][j] = sessie i in slot j; alleen aangemaakt voor toegestane paren.
    x: dict[tuple[int, int], cp_model.IntVar] = {}
    allowed: dict[int, list[int]] = {}
    for p in prepared:
        i = p["idx"]
        allowed[i] = []
        for j, slot in enumerate(flat_slots):
            if p["dur"] > slot["dur"] + AVAIL_TOLERANCE:
                continue
            if not _context_ok(p["sport"], p["sport_raw"], p["kind"], slot["context"]):
                continue
            x[(i, j)] = model.NewBoolVar(f"x_{i}_{j}")
            allowed[i].append(j)

    drop = {p["idx"]: model.NewBoolVar(f"drop_{p['idx']}") for p in prepared}
    forced_drop_reasons: dict[int, str] = {}

    for p in prepared:
        i = p["idx"]
        if not allowed[i]:
            model.Add(drop[i] == 1)
            forced_drop_reasons[i] = (
                f"Past in geen enkel venster (duur {p['dur']} min)"
            )
        model.AddExactlyOne([x[(i, j)] for j in allowed[i]] + [drop[i]])

    # Locked: sessie MOET in het venster van zijn current_plan-positie.
    for p in prepared:
        i = p["idx"]
        if p["key"] not in locked:
            continue
        cur = current_plan.get(p["key"])
        target_j = None
        if cur:
            cur_date, cur_time = cur
            if isinstance(cur_date, str):
                cur_date = date_type.fromisoformat(cur_date)
            cur_min = to_minutes(cur_time)
            for j in allowed[i]:
                slot = flat_slots[j]
                if slot["day"] == cur_date and \
                        slot["start_min"] <= cur_min < slot["end_min"]:
                    target_j = j
                    break
        if target_j is not None:
            model.Add(x[(i, target_j)] == 1)
        else:
            model.Add(drop[i] == 1)
            forced_drop_reasons[i] = (
                "Vastgezette plaatsing past niet meer in de beschikbaarheid"
            )

    # Slot-capaciteit: som van duren ≤ slotduur + tolerantie.
    for j, slot in enumerate(flat_slots):
        terms = [p["dur"] * x[(p["idx"], j)] for p in prepared
                 if (p["idx"], j) in x]
        if terms:
            model.Add(sum(terms) <= slot["dur"] + AVAIL_TOLERANCE)

    # Dag-aggregaten.
    def _day_count(d: date_type, pred) -> cp_model.LinearExpr:
        terms = []
        for p in prepared:
            if not pred(p):
                continue
            for j in allowed[p["idx"]]:
                if flat_slots[j]["day"] == d:
                    terms.append(x[(p["idx"], j)])
        return sum(terms) if terms else 0

    long_on, hard_on, run_on, bike_on, strength_on = {}, {}, {}, {}, {}
    for d in days:
        long_c = _day_count(d, lambda p: p["kind"] == "long")
        hard_c = _day_count(d, lambda p: p["kind"] == "hard")
        key_c = _day_count(d, lambda p: p["kind"] in ("long", "hard"))
        run_c = _day_count(d, lambda p: p["sport"] == "run")
        bike_c = _day_count(d, lambda p: p["sport"] == "bike")
        str_c = _day_count(d, lambda p: p["kind"] == "strength")
        total_c = _day_count(d, lambda p: True)

        # T1a: nooit 2 key sessions (long/hard) op één dag.
        if not isinstance(total_c, int):
            model.Add(total_c <= max_per_day)
        if not isinstance(key_c, int):
            model.Add(key_c <= 1)
        if not isinstance(long_c, int):
            model.Add(long_c <= 1)
        if not isinstance(run_c, int):
            model.Add(run_c <= 1)

        long_on[d] = _on_var(model, long_c, f"long_{d}") if not isinstance(long_c, int) else None
        hard_on[d] = _on_var(model, hard_c, f"hard_{d}") if not isinstance(hard_c, int) else None
        run_on[d] = _on_var(model, run_c, f"run_{d}") if not isinstance(run_c, int) else None
        bike_on[d] = _on_var(model, bike_c, f"bike_{d}") if not isinstance(bike_c, int) else None
        strength_on[d] = _on_var(model, str_c, f"str_{d}") if not isinstance(str_c, int) else None
    # T1b: runs niet back-to-back (toggle).
    if not options.runs_back_to_back_ok:
        for d1, d2 in zip(days, days[1:]):
            if (d2 - d1).days == 1 and run_on[d1] is not None and run_on[d2] is not None:
                model.Add(run_on[d1] + run_on[d2] <= 1)

    objective_terms: list = []

    # Zachte (of in strict harde) spacing-termen op dag-niveau.
    for d in days:
        h, lo = hard_on[d], long_on[d]
        if h is not None and lo is not None:
            if options.strict:
                model.Add(h + lo <= 1)
            else:
                p = _and_var(model, h, lo, f"hardlong_{d}")
                objective_terms.append(weights["hard_adjacent"] * p)

    for d1, d2 in zip(days, days[1:]):
        if (d2 - d1).days != 1:
            continue
        pairs = [
            (hard_on[d1], hard_on[d2], "hard_adjacent"),
            (hard_on[d1], long_on[d2], "hard_adjacent"),
            (long_on[d1], hard_on[d2], "hard_adjacent"),
        ]
        for pair_idx, (a, b, wkey) in enumerate(pairs):
            if a is None or b is None:
                continue
            if options.strict:
                model.Add(a + b <= 1)
            else:
                p = _and_var(model, a, b, f"adj_{wkey}_{d1}_{pair_idx}")
                objective_terms.append(weights[wkey] * p)
        # Longs op aangrenzende dagen.
        if long_on[d1] is not None and long_on[d2] is not None:
            if not options.allow_adjacent_longs:
                model.Add(long_on[d1] + long_on[d2] <= 1)
            elif not options.strict:
                p = _and_var(model, long_on[d1], long_on[d2], f"longadj_{d1}")
                objective_terms.append(weights["long_adjacent"] * p)
        # Kracht daags vóór long/hard.
        if strength_on[d1] is not None:
            nxt = [v for v in (long_on[d2], hard_on[d2]) if v is not None]
            if nxt:
                key_day = model.NewBoolVar(f"keyday_{d2}")
                model.AddMaxEquality(key_day, nxt)
                p = _and_var(model, strength_on[d1], key_day, f"strbefore_{d1}")
                objective_terms.append(weights["strength_before_key_day"] * p)

    # Brick: run + bike op dezelfde dag.
    for d in days:
        if run_on[d] is not None and bike_on[d] is not None:
            p = _and_var(model, run_on[d], bike_on[d], f"brick_{d}")
            objective_terms.append(weights["brick_same_day"] * p)

    # Statische kosten per (sessie, slot).
    static_cost: dict[tuple[int, int], int] = {}
    for p in prepared:
        i = p["idx"]
        cur = current_plan.get(p["key"])
        cur_date = None
        if cur:
            cur_date = cur[0]
            if isinstance(cur_date, str):
                cur_date = date_type.fromisoformat(cur_date)
        for j in allowed[i]:
            slot = flat_slots[j]
            cost = 0
            if slot["dur"] - p["dur"] < TIGHT_MARGIN_MIN:
                cost += weights["tight_margin"]
            if p["kind"] == "long":
                if slot["dur"] < widest:
                    cost += weights["long_not_widest"]
                if slot["start_min"] >= MORNING_CUTOFF_MIN:
                    cost += weights["long_not_morning"]
            if cur_date is not None:
                day_diff = abs((slot["day"] - cur_date).days)
                if day_diff:
                    cost += (weights["move_per_day"] * day_diff
                             + weights.get("move_session_extra", 5))
            if cost:
                static_cost[(i, j)] = cost
                objective_terms.append(cost * x[(i, j)])

    # Drop-kosten (hoog; easies eerst).
    for p in prepared:
        objective_terms.append(DROP_COST.get(p["kind"], 1500) * drop[p["idx"]])

    model.Minimize(sum(objective_terms) if objective_terms else 0)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(options.max_time_s)
    solver.parameters.random_seed = 42
    solver.parameters.num_search_workers = 1  # determinisme

    cp_status = solver.Solve(model)
    if cp_status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return SolveResult(
            status="INFEASIBLE",
            placements=[],
            dropped=gated_drops + [
                DroppedSession(key=p["key"], naam=p["naam"], kind=p["kind"],
                               reason="Geen oplossing binnen harde regels")
                for p in prepared
            ],
            notes=["CP-SAT vond geen oplossing binnen de harde regels"],
        )

    # ── UITLEZEN ────────────────────────────────────────────────────────────
    assigned: dict[int, int] = {}
    relax_dropped: list[DroppedSession] = []
    for p in prepared:
        i = p["idx"]
        if solver.Value(drop[i]):
            reason = forced_drop_reasons.get(i)
            if reason is None:
                reason = ("Onoplosbaar binnen harde regels — laagste-impact "
                          f"sessie ({p['kind']}) vervalt")
            relax_dropped.append(DroppedSession(
                key=p["key"], naam=p["naam"], kind=p["kind"], reason=reason))
            continue
        for j in allowed[i]:
            if solver.Value(x[(i, j)]):
                assigned[i] = j
                break

    # Concrete starttijden: sessies in hetzelfde slot stapelen (long eerst).
    kind_order = {"long": 0, "hard": 1, "easy": 2, "strength": 3}
    by_slot: dict[int, list[dict]] = {}
    for p in prepared:
        if p["idx"] in assigned:
            by_slot.setdefault(assigned[p["idx"]], []).append(p)
    start_min_by_idx: dict[int, int] = {}
    for j, items in by_slot.items():
        items.sort(key=lambda p: (kind_order.get(p["kind"], 9), p["idx"]))
        cursor = flat_slots[j]["start_min"]
        for p in items:
            start_min_by_idx[p["idx"]] = cursor
            cursor += p["dur"]

    # Plaatsingen + leesbare notes (NL) + per-sessie score.
    placements: list[Placement] = []
    schedule_kinds: dict[date_type, set] = {}
    for p in prepared:
        if p["idx"] in assigned:
            d = flat_slots[assigned[p["idx"]]]["day"]
            schedule_kinds.setdefault(d, set()).add(p["kind"])

    for p in prepared:
        i = p["idx"]
        if i not in assigned:
            continue
        j = assigned[i]
        slot = flat_slots[j]
        d = slot["day"]
        notes: list[str] = []
        score = float(static_cost.get((i, j), 0))

        cur = current_plan.get(p["key"])
        moved_days = 0
        if cur:
            cur_date = cur[0]
            if isinstance(cur_date, str):
                cur_date = date_type.fromisoformat(cur_date)
            moved_days = abs((d - cur_date).days)
            if p["key"] in locked:
                notes.append("Vastgezet door gebruiker — niet verplaatst")
            elif moved_days == 0:
                notes.append("Ongewijzigd t.o.v. huidig plan")
            else:
                notes.append(
                    f"Verplaatst: {moved_days} dag(en) t.o.v. huidig plan "
                    f"(+{moved_days * weights['move_per_day']})"
                )
        if p["kind"] == "long":
            if slot["dur"] >= widest:
                notes.append(
                    f"Long op {_day_name(d)}: ruimste venster van de week "
                    f"({slot['dur']} min)"
                )
            else:
                notes.append(
                    f"Long niet op het ruimste venster "
                    f"(+{weights['long_not_widest']})"
                )
        margin = slot["dur"] - p["dur"]
        if margin < TIGHT_MARGIN_MIN:
            notes.append(f"Krap venster: {margin} min marge "
                         f"(+{weights['tight_margin']})")
        # Spacing-context in de uitleg.
        if p["kind"] == "hard":
            neighbours = []
            for delta in (-1, 1):
                nd = d + timedelta(days=delta)
                if {"hard", "long"} & schedule_kinds.get(nd, set()):
                    neighbours.append(_day_name(nd))
            if neighbours:
                notes.append(
                    f"Let op: grenst aan zware dag ({', '.join(neighbours)}) "
                    f"(+{weights['hard_adjacent']})"
                )
                score += weights["hard_adjacent"]
            else:
                notes.append("Hard met ≥1 dag afstand van andere zware sessies")

        placements.append(Placement(
            key=p["key"],
            naam=p["naam"],
            date=d,
            slot_start=to_hhmm(start_min_by_idx[i]),
            slot_end=to_hhmm(slot["end_min"]),
            kind=p["kind"],
            sport=p["sport_raw"],
            score=score,
            moved_days=moved_days,
            notes=notes,
        ))

    placements.sort(key=lambda pl: (pl.date, pl.slot_start, pl.key))

    status: str
    if relax_dropped:
        status = "INFEASIBLE"
    else:
        status = "OPTIMAL" if cp_status == cp_model.OPTIMAL else "FEASIBLE"

    result_notes: list[str] = []
    if relax_dropped:
        names = ", ".join(f"'{dr.naam}'" for dr in relax_dropped)
        open_days = sum(1 for day_slots in slots_by_date.values() if day_slots)
        result_notes.append(
            f"Week past niet volledig — voorstel: laat {names} vervallen "
            f"(max {max_per_day} sessies/dag, {open_days} dag(en) met "
            "beschikbaarheid deze week; volume_compensation pakt het gat op)."
        )

    return SolveResult(
        status=status,
        placements=placements,
        dropped=gated_drops + relax_dropped,
        objective=float(solver.ObjectiveValue()),
        notes=result_notes,
    )


# ── PERSISTENTIE ────────────────────────────────────────────────────────────

def persist_placements(placements: list[Placement]) -> list[str]:
    """Schrijf solver-plaatsingen naar de placements-tabel (history.db).

    Eén rij per sessie (keyed op event_id/key): datum, slot-starttijd,
    sessie-soort, score en leesbare solver-uitleg. Returnt een lijst
    foutmeldingen (leeg = alles gelukt) — placements zijn metadata en
    mogen de planner nooit blokkeren.
    """
    import history_db

    errors: list[str] = []
    for pl in placements:
        try:
            history_db.upsert_placement(
                pl.key,
                date=pl.date.isoformat(),
                slot_start=pl.slot_start,
                session_kind=pl.kind,
                solver_score=pl.score,
                solver_notes="; ".join(pl.notes),
            )
        except Exception as exc:
            errors.append(f"Placement-update {pl.key} faalde: {exc}")
    return errors
