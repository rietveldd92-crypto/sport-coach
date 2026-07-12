from datetime import date

from core import availability_v2 as av2
from tests.mock_intervals import MockIntervals, install


WEEK_START = date(2026, 7, 13)


def _session(name: str, dag: str, sport: str = "Run", minutes: int = 60) -> dict:
    return {
        "naam": name,
        "type": "long_run" if "Long" in name else "run_threshold_short",
        "duur_min": minutes,
        "tss_geschat": minutes,
        "sport": sport,
        "beschrijving": "testbeschrijving",
        "dag": dag,
        "datum": (WEEK_START).isoformat(),
        "plaatsing_reden": f"{name} op {dag}: testreden.",
    }


def test_build_week_v3_preplanned_houdt_plaatsing_en_reden(monkeypatch):
    install(monkeypatch, MockIntervals())
    for weekday in range(7):
        av2.set_pattern(weekday, [("07:00", "08:00")])

    from agents import week_planner

    run_sessions = [
        _session("Interval A", "maandag", minutes=60),
        _session("Interval B", "donderdag", minutes=60),
        _session("Long run", "zondag", minutes=120),
    ]
    bike_sessions = [
        _session("Forenzen-rit", "dinsdag", "VirtualRide", minutes=100),
    ]
    events = week_planner.build_week(
        WEEK_START,
        run_sessions,
        bike_sessions,
        injury_guard={"status": "groen", "strength_allowed": False},
        load_manager={
            "current_phase": "basis_I",
            "recommended_weekly_tss": 400,
            "ctl": 50,
            "atl": 45,
            "tsb": 5,
        },
        dry_run=True,
        preplanned=True,
        planner_warnings=[{
            "tier": 2,
            "code": "available_day_left_empty",
            "dag": "woensdag",
            "sessie": None,
            "message": "woensdag blijft leeg: geraamte/urenbudget is op.",
        }],
    )

    workouts = [e for e in events if e["categorie"] == "WORKOUT"]
    assert len(workouts) == 4
    assert len({e["datum"] for e in workouts}) == 4
    assert all("Plaatsing:" in e["beschrijving"] for e in workouts)
    assert next(e for e in workouts if e["naam"] == "Long run")["tss"] == 120


def test_e2e_hersteld_plan_geeft_volwaardige_week(monkeypatch):
    """Reproductie van de productie-bug van 2026-07-12 en het herstelpad.

    Situatie: het macroplan in de DB is door de (oude) zondagse herijking
    herstart — accumulatie_I met ~4km-longruns midden in juli. Het herstel:
    force-herijking (racedatum-anker) gevolgd door een V3-weekplanning met
    het beschikbaarheidspatroon van de atleet. De week moet dan weer een
    volwaardige trainingsweek zijn.
    """
    from core import goal_engine, plan_provider
    from core.goal_engine import Goal
    from core.periodization_generator import PlanWeek, persist_plan_weeks
    from core.replan_goal import weekly_recalibration
    from agents.day_assigner import assign_days
    from agents.week_skeleton import build_skeleton_with_warnings

    goal = goal_engine.create_goal(Goal(
        type="marathon", sport="run", event_date=date(2026, 10, 18),
        target_value="2:59:00", priority="A", status="active",
    ))

    # Het kapotte plan zoals prod het had: herstart bij de basis rond juli.
    broken = []
    monday = date(2026, 6, 29)
    for i in range(16):
        km = 8.0 * (1.15 ** i)
        broken.append(PlanWeek(
            week_start=date.fromordinal(monday.toordinal() + 7 * i),
            phase="accumulatie_I", is_deload=False,
            tss_target_min=300, tss_target_max=360,
            run_km=round(km, 1), run_sessions=1,
            long_run_km=round(km * 0.42, 1), bike_sessions=3,
            intensity_gate="geen",
        ))
    persist_plan_weeks(goal.id, broken)

    # Sanity: dit ís de bug — 4km-longrun in de week van 13 juli.
    vol_broken = plan_provider.calculate_weekly_run_volume(
        plan_provider.get_week_number(date(2026, 7, 13)))
    assert vol_broken["lange_duurloop_km"] < 5

    # ── Herstel: force-herijking met werkelijke activiteiten ──
    def _run(day, km):
        return {"type": "Run", "start_date_local": f"{day}T08:00:00",
                "distance": km * 1000}
    activities = [
        _run("2026-06-15", 20), _run("2026-06-17", 14), _run("2026-06-20", 24),
        _run("2026-06-22", 18), _run("2026-06-25", 22), _run("2026-06-29", 9),
    ]
    report = weekly_recalibration(
        today=date(2026, 7, 12), goal=goal, actual_ctl=48.0,
        activities=activities, force=True,
    )
    assert report["status"] == "replanned"

    # ── V3-weekplanning zoals plan_week.run die aanroept ──
    wk = plan_provider.get_week_number(date(2026, 7, 13))
    vol = plan_provider.calculate_weekly_run_volume(wk)
    week_row = plan_provider.get_weekly_plan()[wk - 1]

    assert vol["lange_duurloop_km"] >= 12, "long run moet weer marathonwaardig zijn"
    assert vol["intensity_gate"] in {"tempoduur", "drempel", "race_specifiek"}

    guard = {"run_intensity_allowed": True, "tempo_allowed": True,
             "strides_allowed": True, "bike_intensity_allowed": True,
             "volume_modifier": 1.0}
    skeleton, skel_warnings = build_skeleton_with_warnings(
        wk, vol, guard,
        {"is_deload_week": week_row["is_recovery"]},
        {"progression": {"run_quality_step": 4}}, [],
    )

    # Beschikbaarheid uit het weekpatroon van de atleet (screenshot 2026-07-12).
    availability = {"maandag": 90, "dinsdag": 90, "woensdag": 90,
                    "donderdag": 90, "vrijdag": 120, "zaterdag": 180,
                    "zondag": 180}
    placed, warnings = assign_days(
        skeleton, availability, week_start=date(2026, 7, 13))

    runs = [s for s in placed if s["sport"] == "Run"]
    quality = [s for s in runs if s["type"] in
               {"run_threshold_short", "run_threshold_long", "run_vo2max",
                "run_speed", "run_marathon"}]
    long_runs = [s for s in runs if s["type"].startswith("long_run")]

    if not week_row["is_recovery"]:
        assert len(quality) == 2, "buildweek hoort 2 kwaliteitssessies te hebben"
    assert len(long_runs) == 1
    assert long_runs[0]["duur_min"] >= 70, "long run mag geen 26-minuten-drafje zijn"

    # Intervallen gespreid: ≥2 dagen tussen kwaliteitssessies onderling.
    dagen = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag",
             "zaterdag", "zondag"]
    q_idx = sorted(dagen.index(s["dag"]) for s in quality)
    if len(q_idx) == 2:
        assert q_idx[1] - q_idx[0] >= 2

    # Geen beschikbare dag blijft leeg.
    empty = [w for w in warnings if w["code"] == "available_day_left_empty"]
    assert not empty, f"lege dagen: {empty}"

    # Alles past binnen de dag.
    for s in placed:
        assert s["duur_min"] <= availability[s["dag"]], (
            f"{s['naam']} ({s['duur_min']}m) past niet op {s['dag']}")
