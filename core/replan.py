"""Replan bij beschikbaarheidswijziging — minimale verschuiving via solver.

Vervangt de oude shift-keten (``agents/shift_day.py`` +
``_try_shift_before_replan`` in app.py). Eén mechanisme: de slot-solver
draait opnieuw over de hele week met het huidige plan als referentie;
de verplaatsingsterm (25/sessie/dag) zorgt dat minimale verschuiving
vanzelf wint. Alleen daadwerkelijk verplaatste events worden geüpdatet
(via ``workout_actions.apply_move``), de rest blijft onaangeroerd.

Fase 3 voegt :func:`move_event` toe: drag-to-reschedule via de API —
zelfde solver, met de gesleepte sessie locked op de doeldatum.
"""
from __future__ import annotations

from datetime import date as date_type, timedelta
from typing import Optional


def event_duration_min(event: dict) -> int:
    """Duur in minuten van een intervals.icu event.

    Probeert moving_time → workout_doc.duration → 'NN min' in de naam.
    (Overgenomen uit het verwijderde agents/shift_day.py.)
    """
    mt = event.get("moving_time")
    if mt:
        return round(mt / 60)
    wd = event.get("workout_doc") or {}
    dur_s = wd.get("duration")
    if dur_s:
        return round(dur_s / 60)
    name = (event.get("name") or "").lower()
    if "min" in name:
        for p in name.replace("min", " ").split():
            try:
                v = int(p)
                if 20 <= v <= 300:
                    return v
            except ValueError:
                pass
    return 0


def _movable_workouts(events: list[dict], today: date_type) -> list[dict]:
    """WORKOUT-events vanaf vandaag — het verleden raken we nooit aan."""
    workouts = [
        e for e in events
        if e.get("category") == "WORKOUT" and not e.get("is_note")
    ]
    return [
        e for e in workouts
        if (e.get("start_date_local") or "")[:10] >= today.isoformat()
    ]


def _solver_inputs(movable: list[dict], placements_db: dict) -> tuple[list, dict, set]:
    """(sessions, current_plan, locked) voor slot_solver.solve_week.

    current_plan komt uit de placements-tabel als die er is, anders uit
    de start_date_local van het event zelf.
    """
    sessions: list[dict] = []
    current_plan: dict[str, tuple[str, str]] = {}
    locked: set[str] = set()
    for e in movable:
        eid = str(e.get("id"))
        sdl = e.get("start_date_local") or ""
        cur_date = sdl[:10]
        cur_time = sdl[11:16] if "T" in sdl else "00:00"
        sessions.append({
            "event_id": eid,
            "naam": e.get("name") or "?",
            "duur_min": event_duration_min(e),
            "sport": e.get("type") or "",
            "type": "",
        })
        rec = placements_db.get(eid)
        if rec and rec.get("date"):
            current_plan[eid] = (rec["date"], rec.get("slot_start") or cur_time)
        else:
            current_plan[eid] = (cur_date, cur_time)
        if rec and rec.get("locked"):
            locked.add(eid)
    return sessions, current_plan, locked


def _solver_options():
    from core import slot_solver
    from shared import load_state

    prefs = (load_state() or {}).get("preferences") or {}
    return slot_solver.SolverOptions(
        runs_back_to_back_ok=bool(prefs.get("runs_back_to_back_ok", False)),
    )


def replan_on_availability_change(
    week_start: date_type,
    *,
    events: Optional[list[dict]] = None,
    today: Optional[date_type] = None,
    apply: bool = True,
) -> dict:
    """Herplaats de week met huidige placements als referentie.

    Args:
        week_start: maandag van de week.
        events: intervals.icu events (None = zelf ophalen).
        today: testbaar 'vandaag'; events vóór vandaag blijven onaangeraakt.
        apply: False = alleen het diff berekenen, niets muteren.

    Returns:
        {"moved": [{event_id, event_name, from, to, from_time, to_time}],
         "needs_replan": bool, "errors": [str], "diag": str}
        needs_replan=True → caller moet full replan doen (plan_week.run).
    """
    import history_db
    from core import availability_v2 as av2
    from core import slot_solver

    today = today or date_type.today()
    week_end = week_start + timedelta(days=6)

    if events is None:
        try:
            import intervals_client as api

            events = api.get_events(week_start, week_end)
        except Exception as exc:
            return {"moved": [], "needs_replan": True, "errors": [],
                    "diag": f"events ophalen faalde: {exc}"}

    # Verleden niet aanraken — die sessies zijn al gedaan of gemist.
    movable = _movable_workouts(events, today)
    if not movable:
        return {"moved": [], "needs_replan": False, "errors": [],
                "diag": "geen toekomstige sessies om te herplaatsen"}

    slots = av2.get_slots_for_week(week_start)
    slots = {d: (s if d >= today else []) for d, s in slots.items()}
    if not any(slots.values()):
        return {"moved": [], "needs_replan": False, "errors": [],
                "diag": "geen beschikbaarheid ingesteld voor deze week"}

    placements_db = {
        p["event_id"]: p
        for p in history_db.get_placements(week_start.isoformat(),
                                           week_end.isoformat())
    }

    sessions, current_plan, locked = _solver_inputs(movable, placements_db)

    result = slot_solver.solve_week(
        sessions, slots,
        options=_solver_options(), current_plan=current_plan, locked=locked,
    )

    if result.status == "INFEASIBLE":
        dropped = ", ".join(f"'{d.naam}'" for d in result.dropped) or "?"
        return {"moved": [], "needs_replan": True, "errors": [],
                "diag": f"week past niet meer in de beschikbaarheid "
                        f"(knelpunt: {dropped}) — full replan nodig"}

    moves: list[dict] = []
    for pl in result.placements:
        cur_date, cur_time = current_plan[pl.key]
        if pl.date.isoformat() != str(cur_date):
            moves.append({
                "event_id": pl.key,
                "event_name": pl.naam,
                "from": str(cur_date),
                "to": pl.date.isoformat(),
                "from_time": cur_time,
                "to_time": pl.slot_start,
            })

    errors: list[str] = []
    if apply:
        from agents import workout_actions

        for mv in moves:
            try:
                workout_actions.apply_move(
                    mv["event_id"], mv["to"], mv["to_time"])
            except Exception as exc:
                errors.append(
                    f"Verplaatsen '{mv['event_name']}' → {mv['to']} "
                    f"faalde: {exc}")
        # Placements-tabel bijwerken met de nieuwe (of bevestigde) posities.
        errors.extend(slot_solver.persist_placements(result.placements))

    diag = (f"{len(moves)} sessie(s) verschoven" if moves
            else "plan past nog — geen verschuiving nodig")
    return {"moved": moves, "needs_replan": False,
            "errors": errors, "diag": diag}


def move_event(
    event_id: str,
    target_date: date_type,
    *,
    apply: bool = False,
    events: Optional[list[dict]] = None,
    today: Optional[date_type] = None,
) -> dict:
    """Drag-to-reschedule: solve de week met deze sessie locked op doeldatum.

    De solver draait over de hele week met het huidige plan als referentie;
    de verplaatsingsterm zorgt dat alleen sessies verhuizen die écht moeten
    (UPGRADE_PLAN §6 Week-scherm / §7 POST /api/placements/{id}/move).

    Args:
        event_id: intervals.icu event-id van de te verplaatsen sessie.
        target_date: gewenste nieuwe datum (zelfde week).
        apply: True = wijzigingen doorvoeren (intervals.icu + placements);
            False = alleen het diff teruggeven (preview).
        events: injecteerbaar voor tests (None = ophalen via intervals.icu).
        today: testbaar 'vandaag'.

    Returns dict::

        {status: OPTIMAL|FEASIBLE|INFEASIBLE,
         diff: [{event_id, event_name, from, to, from_time, to_time}],
         placements: [{event_id, naam, date, slot_start, kind, score,
                       moved_days, notes}],
         dropped: [{event_id, naam, reason}],
         applied: bool, errors: [str]}

    Raises:
        LookupError: event niet gevonden in de doelweek.
        ValueError: doeldatum in het verleden, of geen
            beschikbaarheidsvenster op de doeldag.
    """
    import history_db
    from core import availability_v2 as av2
    from core import slot_solver

    event_id = str(event_id)
    today = today or date_type.today()
    week_start = target_date - timedelta(days=target_date.weekday())
    week_end = week_start + timedelta(days=6)

    if target_date < today:
        raise ValueError(f"Doeldatum {target_date} ligt in het verleden.")

    if events is None:
        import intervals_client as api

        events = api.get_events(week_start, week_end)

    movable = _movable_workouts(events, today)
    target_event = next(
        (e for e in movable if str(e.get("id")) == event_id), None)
    if target_event is None:
        raise LookupError(
            f"Event {event_id} niet gevonden als verplaatsbare sessie in de "
            f"week van {week_start} (verleden of andere week?)")

    slots = av2.get_slots_for_week(week_start)
    slots = {d: (s if d >= today else []) for d, s in slots.items()}
    target_slots = slots.get(target_date) or []
    if not target_slots:
        raise ValueError(
            f"Geen beschikbaarheidsvenster op {target_date} — stel eerst "
            f"beschikbaarheid in voor die dag.")

    placements_db = {
        p["event_id"]: p
        for p in history_db.get_placements(week_start.isoformat(),
                                           week_end.isoformat())
    }
    sessions, current_plan, locked = _solver_inputs(movable, placements_db)

    # Origineel plan bewaren voor het diff; de solver krijgt de gewenste
    # positie als 'huidig' + locked zodat de sessie daar MOET landen.
    original_plan = dict(current_plan)
    first_slot = min(target_slots, key=lambda s: s.start_min)
    current_plan[event_id] = (target_date.isoformat(), first_slot.start)
    locked = set(locked) | {event_id}

    result = slot_solver.solve_week(
        sessions, slots,
        options=_solver_options(), current_plan=current_plan, locked=locked,
    )

    diff: list[dict] = []
    for pl in result.placements:
        orig_date, orig_time = original_plan[pl.key]
        if pl.date.isoformat() != str(orig_date):
            diff.append({
                "event_id": pl.key,
                "event_name": pl.naam,
                "from": str(orig_date),
                "to": pl.date.isoformat(),
                "from_time": orig_time,
                "to_time": pl.slot_start,
            })

    dropped = [
        {"event_id": d.key, "naam": d.naam, "reason": d.reason}
        for d in result.dropped
    ]

    errors: list[str] = []
    applied = False
    if apply and result.status != "INFEASIBLE":
        from agents import workout_actions

        for mv in diff:
            try:
                workout_actions.apply_move(
                    mv["event_id"], mv["to"], mv["to_time"])
            except Exception as exc:
                errors.append(
                    f"Verplaatsen '{mv['event_name']}' → {mv['to']} "
                    f"faalde: {exc}")
        errors.extend(slot_solver.persist_placements(result.placements))
        # Handmatige drag = gebruikersbesluit → vastzetten zodat een
        # latere availability-replan dit niet stilletjes terugdraait.
        try:
            history_db.set_placement_locked(event_id, True)
        except Exception as exc:
            errors.append(f"Lock zetten faalde: {exc}")
        applied = not errors

    return {
        "status": result.status,
        "diff": diff,
        "placements": [
            {
                "event_id": pl.key,
                "naam": pl.naam,
                "date": pl.date.isoformat(),
                "slot_start": pl.slot_start,
                "kind": pl.kind,
                "sport": pl.sport,
                "score": pl.score,
                "moved_days": pl.moved_days,
                "notes": pl.notes,
            }
            for pl in result.placements
        ],
        "dropped": dropped,
        "applied": applied,
        "errors": errors,
    }
