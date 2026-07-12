"""Deterministic day assignment for Planner V3."""
from __future__ import annotations

from datetime import date, timedelta

from agents.week_skeleton import SkeletonSlot


DAYS_NL = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag",
           "zaterdag", "zondag"]
MAX_MINUTES_PER_DAY = 6 * 60
MIN_FILL_MINUTES = 45


def assign_days(
    skeleton: list[SkeletonSlot],
    availability: dict[str, int],
    *,
    runs_back_to_back_ok: bool = False,
    week_start: date,
) -> tuple[list[dict], list[dict]]:
    warnings: list[dict] = []
    availability = _normalized_availability(availability, warnings)
    occupied: set[str] = set()
    run_days: set[str] = set()
    placed: list[dict] = []

    def place(slot: SkeletonSlot, dag: str, reason: str) -> None:
        sessie = dict(slot.sessie)
        sessie["dag"] = dag
        sessie["datum"] = (week_start + timedelta(days=DAYS_NL.index(dag))).isoformat()
        sessie["plaatsing_reden"] = reason
        sessie["_skeleton_role"] = slot.rol
        placed.append(sessie)
        occupied.add(dag)
        if _is_run(sessie):
            run_days.add(dag)

    for slot in [s for s in skeleton if s.rol == "commute"]:
        dag = slot.vaste_dag
        if not dag:
            warnings.append({
                "code": "fixed_session_without_day",
                "message": f"Vaste sessie '{slot.sessie.get('naam')}' heeft geen weekdag.",
                "dag": None,
            })
            continue
        if dag in occupied:
            warnings.append({
                "code": "fixed_day_already_used",
                "message": f"Vaste sessie op {dag} botst met een andere vaste sessie.",
                "dag": dag,
            })
            continue
        place(slot, dag, f"Vaste sessie op {dag}: niet verplaatsbaar.")

    long_slot = _first_role(skeleton, "long_run")
    long_day = None
    if long_slot is not None:
        long_day = _best_long_day(availability, occupied)
        if long_day is None:
            warnings.append({
                "code": "long_run_no_available_day",
                "message": "Lange duurloop past nergens: maak een dag beschikbaar.",
                "dag": None,
            })
        else:
            place(
                long_slot,
                long_day,
                f"Long run op {long_day}: meeste beschikbare tijd ({availability[long_day]} min).",
            )

    for slot in [s for s in skeleton if s.rol in ("interval_a", "interval_b")]:
        dag = _best_interval_day(
            availability,
            occupied,
            run_days,
            long_day,
            runs_back_to_back_ok=runs_back_to_back_ok,
        )
        if dag is None:
            dag = _least_bad_day(availability, occupied)
            if dag is None:
                warnings.append({
                    "code": "interval_no_available_day",
                    "message": f"{slot.sessie.get('naam')} past nergens: maak een dag beschikbaar.",
                    "dag": None,
                })
                continue
            warnings.append({
                "code": "interval_spacing_compromised",
                "message": f"{slot.sessie.get('naam')} geplaatst op {dag}, maar spacing is niet ideaal.",
                "dag": dag,
            })
            reason = f"Interval op {dag}: minst slechte beschikbare dag; check herstel."
        else:
            reason = f"Interval op {dag}: maximaal gespreid van long run en andere runs."
            if _min_distance(dag, run_days) < 2:
                warnings.append({
                    "code": "interval_spacing_compromised",
                    "message": f"{slot.sessie.get('naam')} geplaatst op {dag}, maar spacing is niet ideaal.",
                    "dag": dag,
                })
                reason = f"Interval op {dag}: geplaatst met beperkte spacing; check herstel."
        place(slot, dag, reason)

    for slot in [s for s in skeleton if s.rol == "easy_run"]:
        dag = _best_easy_run_day(
            availability,
            occupied,
            run_days,
            runs_back_to_back_ok=runs_back_to_back_ok,
        )
        if dag is None:
            warnings.append({
                "code": "easy_run_not_placed",
                "message": "Extra rustige loop vervalt: geen vrije niet-aangrenzende dag.",
                "dag": None,
            })
            continue
        place(slot, dag, f"Easy run op {dag}: vrije dag zonder run-buren.")

    # Grootste ritten eerst, en alleen op dagen waar de duur echt past —
    # een niet-passende vulling wordt overgeslagen, niet geforceerd.
    fill_slots = sorted(
        [s for s in skeleton if s.rol == "bike_fill"],
        key=lambda s: -(s.sessie.get("duur_min") or 0),
    )
    for slot in fill_slots:
        dag = _best_bike_day(
            availability, occupied,
            min_minutes=max(MIN_FILL_MINUTES, int(slot.sessie.get("duur_min") or 0)),
        )
        if dag is None:
            if not any(
                availability.get(d, 0) >= MIN_FILL_MINUTES and d not in occupied
                for d in DAYS_NL
            ):
                warnings.append({
                    "code": "bike_fill_budget_done",
                    "message": "Geen extra fiets-vulling: urenbudget of vrije dagen zijn op.",
                    "dag": None,
                })
                break
            continue  # deze rit past nergens; probeer een kortere vulling
        place(slot, dag, f"Fiets-vulling op {dag}: resterende dag met >=45 min beschikbaar.")

    _warn_empty_available_days(availability, occupied, warnings)
    placed.sort(key=lambda s: (DAYS_NL.index(s["dag"]), s.get("naam") or ""))
    return placed, warnings


def _normalized_availability(raw: dict[str, int], warnings: list[dict]) -> dict[str, int]:
    out = {}
    for dag in DAYS_NL:
        minutes = int(raw.get(dag, 0) or 0)
        if minutes > MAX_MINUTES_PER_DAY:
            warnings.append({
                "code": "availability_clamped",
                "message": f"{dag} had {minutes} min beschikbaarheid; begrensd op 360 min.",
                "dag": dag,
            })
            minutes = MAX_MINUTES_PER_DAY
        out[dag] = max(0, minutes)
    return out


def _first_role(skeleton: list[SkeletonSlot], role: str) -> SkeletonSlot | None:
    return next((slot for slot in skeleton if slot.rol == role), None)


def _best_long_day(availability: dict[str, int], occupied: set[str]) -> str | None:
    candidates = [
        dag for dag in DAYS_NL
        if dag not in occupied and availability.get(dag, 0) >= MIN_FILL_MINUTES
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda d: (availability[d], -abs(DAYS_NL.index(d) - 6)))


def _best_interval_day(
    availability: dict[str, int],
    occupied: set[str],
    run_days: set[str],
    long_day: str | None,
    *,
    runs_back_to_back_ok: bool,
) -> str | None:
    candidates = [
        dag for dag in DAYS_NL
        if dag not in occupied and availability.get(dag, 0) >= MIN_FILL_MINUTES
    ]
    if not candidates:
        return None

    ideal = [
        dag for dag in candidates
        if _min_distance(dag, run_days) >= 2
        and (long_day is None or abs(_idx(dag) - _idx(long_day)) >= 2)
    ]
    pool = ideal or [
        dag for dag in candidates
        if runs_back_to_back_ok or _min_distance(dag, run_days) >= 2
    ] or candidates
    return max(pool, key=lambda d: (_min_distance(d, run_days | ({long_day} if long_day else set())), availability[d]))


def _best_easy_run_day(
    availability: dict[str, int],
    occupied: set[str],
    run_days: set[str],
    *,
    runs_back_to_back_ok: bool,
) -> str | None:
    candidates = [
        dag for dag in DAYS_NL
        if dag not in occupied and availability.get(dag, 0) >= MIN_FILL_MINUTES
    ]
    if not runs_back_to_back_ok:
        candidates = [dag for dag in candidates if _min_distance(dag, run_days) >= 2]
    if not candidates:
        return None
    return max(candidates, key=lambda d: (availability[d], _min_distance(d, run_days)))


def _best_bike_day(availability: dict[str, int], occupied: set[str],
                   min_minutes: int = MIN_FILL_MINUTES) -> str | None:
    candidates = [
        dag for dag in DAYS_NL
        if dag not in occupied and availability.get(dag, 0) >= min_minutes
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda d: (availability[d], -_idx(d)))


def _least_bad_day(availability: dict[str, int], occupied: set[str]) -> str | None:
    candidates = [
        dag for dag in DAYS_NL
        if dag not in occupied and availability.get(dag, 0) > 0
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda d: availability[d])


def _warn_empty_available_days(
    availability: dict[str, int],
    occupied: set[str],
    warnings: list[dict],
) -> None:
    for dag, minutes in availability.items():
        if minutes >= MIN_FILL_MINUTES and dag not in occupied:
            warnings.append({
                "code": "available_day_left_empty",
                "message": f"{dag} blijft leeg: geraamte/urenbudget is op.",
                "dag": dag,
            })


def _min_distance(dag: str, others: set[str]) -> int:
    if not others:
        return 99
    return min(abs(_idx(dag) - _idx(other)) for other in others if other)


def _idx(dag: str) -> int:
    return DAYS_NL.index(dag)


def _is_run(sessie: dict) -> bool:
    return (sessie.get("sport") or "").lower() == "run"
