"""Een vastgezette week mag de planner niet meer aanraken."""

from datetime import date

import pytest

from agents import week_lock


def _lock_event(reason: str = "Handmatig samengesteld."):
    return {
        "id": "42",
        "category": "NOTE",
        "name": week_lock.LOCK_NOTE_NAME,
        "description": reason + "\n\nOntgrendelen: ...",
    }


def test_find_lock_herkent_lock_note():
    events = [{"name": "Dagelijkse rehab"}, _lock_event()]
    assert week_lock.is_locked(events)
    assert week_lock.find_lock(events)["id"] == "42"


def test_geen_lock_bij_gewone_week():
    events = [{"name": "Krachttraining"}, {"name": "Lange drempel - 3x12 min @ 4:22/km"}]
    assert not week_lock.is_locked(events)


def test_lock_reason_is_eerste_regel():
    assert week_lock.lock_reason([_lock_event("Consolidatieweek")]) == "Consolidatieweek"


def test_lock_reason_leeg_zonder_lock():
    assert week_lock.lock_reason([{"name": "Krachttraining"}]) == ""


def test_fetch_lock_bij_api_fout_geeft_pseudo_lock(monkeypatch):
    """Onbekend != vrij. Kunnen we het niet checken, dan wissen we niet."""
    import intervals_client

    def _boom(*a, **kw):
        raise RuntimeError("502 Bad Gateway")

    monkeypatch.setattr(intervals_client, "get_events", _boom)
    lock = week_lock.fetch_lock(date(2026, 8, 3))
    assert lock is not None
    assert lock["_unknown"] is True


def test_build_week_wist_niets_op_vergrendelde_week(monkeypatch):
    from agents import week_planner

    geschreven = []
    verwijderd = []

    monkeypatch.setattr(week_planner.api, "get_events",
                        lambda *a, **kw: [_lock_event("Consolidatieweek")])
    monkeypatch.setattr(week_planner.api, "delete_event",
                        lambda eid: verwijderd.append(eid))
    monkeypatch.setattr(week_planner.api, "create_event",
                        lambda **kw: geschreven.append(kw) or {"id": "1"})

    events = week_planner.build_week(
        week_start=date(2026, 8, 3),
        run_sessions=[{"naam": "Easy 10km", "sport": "Run", "duur_min": 55,
                       "tss_geschat": 50, "beschrijving": "- 55m 65% Pace"}],
        bike_sessions=[],
        injury_guard={"status": "groen", "strength_allowed": True},
        load_manager={"current_phase": "transformatie_I",
                      "recommended_weekly_tss": 500},
        dry_run=False,
    )

    assert events == []
    assert verwijderd == [], "vergrendelde week mag niet gewist worden"
    assert geschreven == [], "vergrendelde week mag niet gevuld worden"


def test_lock_vlaggen_botsen_niet_stil_met_planvlaggen(monkeypatch, capsys):
    """--horizon slikte --vastzetten op en startte de planner.

    De lock-vlag bestaat om planning te blokkeren; als hij in combinatie met
    --horizon of --schrijf stil genegeerd wordt, doet het commando precies het
    tegenovergestelde van wat je vroeg.
    """
    import sys as _sys
    import plan_week

    gepland = []
    monkeypatch.setattr(plan_week, "run_horizon",
                        lambda *a, **kw: gepland.append(a))
    monkeypatch.setattr(plan_week, "run", lambda *a, **kw: gepland.append(a))

    for argv in (
        ["plan_week.py", "--horizon", "2", "--vastzetten"],
        ["plan_week.py", "--schrijf", "--vastzetten"],
        ["plan_week.py", "--ontgrendel", "--schrijf"],
    ):
        monkeypatch.setattr(_sys, "argv", argv)
        with pytest.raises(SystemExit) as exc:
            plan_week.main()
        assert exc.value.code == 1, f"{argv} had moeten afbreken"
        assert gepland == [], f"{argv} startte alsnog de planner"


def test_vastzetten_en_ontgrendel_samen_is_een_fout(monkeypatch):
    import sys as _sys
    import plan_week

    monkeypatch.setattr(_sys, "argv",
                        ["plan_week.py", "--vastzetten", "--ontgrendel"])
    with pytest.raises(SystemExit) as exc:
        plan_week.main()
    assert exc.value.code == 1
