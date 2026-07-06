"""Tests voor core/slot_solver — CP-SAT weekplaatsing (UPGRADE_PLAN §5.4).

Port van de tier-cases uit test_day_planner.py naar solver-asserties, plus
de nieuwe Planner v2-cases: minimale verschuiving, locked, indoor-context,
onoplosbare week (drop-suggestie), starttijden binnen slots, determinisme.
"""
from datetime import date, timedelta

from core.availability_v2 import Slot, to_hhmm, to_minutes
from core.slot_solver import (
    SolverOptions,
    classify_session,
    solve_week,
)

WEEK_START = date(2026, 4, 20)  # maandag

DAYS_NL = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag",
           "zaterdag", "zondag"]


# ── Fixtures ────────────────────────────────────────────────────────────────

def _sessie(naam, duur, sport="Run", type_="z2_standard", event_id=None):
    s = {
        "naam": naam,
        "duur_min": duur,
        "sport": sport,
        "type": type_,
        "tss_geschat": duur,
        "beschrijving": "test",
    }
    if event_id:
        s["event_id"] = event_id
    return s


def _day(naam: str) -> date:
    return WEEK_START + timedelta(days=DAYS_NL.index(naam))


def _slot(d: date, minutes: int, start="07:00", context="any") -> Slot:
    return Slot(date=d, start=start,
                end=to_hhmm(to_minutes(start) + minutes), context=context)


def _slots(avail_by_dag: dict, context_by_dag: dict | None = None):
    """Minuten-dict → één slot per dag vanaf 07:00 (0 = rustdag)."""
    out = {}
    for naam in DAYS_NL:
        d = _day(naam)
        minutes = avail_by_dag.get(naam, 0)
        ctx = (context_by_dag or {}).get(naam, "any")
        out[d] = [_slot(d, minutes, context=ctx)] if minutes > 0 else []
    return out


def _dag(pl) -> str:
    return DAYS_NL[pl.date.weekday()]


def _by_name(result, naam):
    return next(pl for pl in result.placements if pl.naam == naam)


# ── Classificatie (incl. kracht) ────────────────────────────────────────────

def test_classify_strength():
    s = _sessie("Krachttraining", 35, sport="WeightTraining", type_="strength")
    assert classify_session(s) == "strength"


def test_classify_long_en_hard_via_bestaande_logica():
    assert classify_session(_sessie("Z2 lang", 120)) == "long"
    assert classify_session(_sessie("Threshold", 60, type_="threshold")) == "hard"
    assert classify_session(_sessie("Herstelrun", 40, type_="recovery")) == "easy"


# ── Long-plaatsing ──────────────────────────────────────────────────────────

def test_long_op_ruimste_dag():
    """Port T2b: long landt op het ruimste venster van de week."""
    avail = {"maandag": 30, "dinsdag": 60, "woensdag": 60, "donderdag": 60,
             "vrijdag": 60, "zaterdag": 240, "zondag": 150}
    result = solve_week([_sessie("Long run 120", 120)], _slots(avail))
    assert result.status == "OPTIMAL"
    assert _dag(result.placements[0]) == "zaterdag"
    assert any("ruimste venster" in n for n in result.placements[0].notes)


def test_twee_longs_op_twee_ruimste_dagen():
    """Port: twee longs → de twee ruimste dagen."""
    avail = {"maandag": 30, "dinsdag": 45, "woensdag": 60, "donderdag": 45,
             "vrijdag": 180, "zaterdag": 180, "zondag": 60}
    sessies = [_sessie("Long run", 120),
               _sessie("Long ride", 150, sport="VirtualRide",
                       type_="endurance_ride")]
    result = solve_week(sessies, _slots(avail))
    assert sorted(_dag(pl) for pl in result.placements) == ["vrijdag", "zaterdag"]


def test_nooit_twee_longs_zelfde_dag():
    """T1a hard: ook als één dag genoeg capaciteit heeft voor beide longs."""
    avail = {"vrijdag": 300, "zaterdag": 200}
    sessies = [_sessie("Long run", 120),
               _sessie("Long ride", 150, sport="VirtualRide",
                       type_="endurance_ride")]
    result = solve_week(sessies, _slots(avail))
    assert len(result.placements) == 2
    dates = [pl.date for pl in result.placements]
    assert dates[0] != dates[1]


# ── Capaciteit & tolerantie ─────────────────────────────────────────────────

def test_capaciteit_tolerantie_accepteert_kleine_overrun():
    avail = {"dinsdag": 60}
    result = solve_week([_sessie("Threshold 65", 65, type_="threshold")],
                        _slots(avail))
    assert result.status == "OPTIMAL"
    assert _dag(result.placements[0]) == "dinsdag"


def test_capaciteit_grote_overrun_geeft_infeasible_met_drop():
    avail = {"dinsdag": 60}
    result = solve_week([_sessie("Threshold 90", 90, type_="threshold")],
                        _slots(avail))
    assert result.status == "INFEASIBLE"
    assert len(result.dropped) == 1
    assert result.dropped[0].naam == "Threshold 90"


# ── Hard-spacing ────────────────────────────────────────────────────────────

def test_twee_hards_niet_aangrenzend():
    avail = {d: 90 for d in DAYS_NL}
    sessies = [_sessie("Threshold", 70, sport="VirtualRide", type_="threshold"),
               _sessie("VO2max", 60, sport="VirtualRide", type_="vo2max")]
    result = solve_week(sessies, _slots(avail))
    idx = sorted(DAYS_NL.index(_dag(pl)) for pl in result.placements)
    assert idx[1] - idx[0] >= 2


def test_hard_niet_naast_long():
    avail = {d: 90 for d in DAYS_NL}
    avail["zaterdag"] = 200
    sessies = [_sessie("Long run", 150),
               _sessie("Threshold", 60, sport="VirtualRide", type_="threshold")]
    result = solve_week(sessies, _slots(avail))
    long_dag = _dag(_by_name(result, "Long run"))
    hard_dag = _dag(_by_name(result, "Threshold"))
    assert long_dag == "zaterdag"
    assert hard_dag not in ("vrijdag", "zaterdag", "zondag")


def test_hard_spacing_best_effort_plaatst_toch():
    """Zacht: geen spacing mogelijk → tóch plaatsen (oude Tier-2 warning)."""
    avail = {"vrijdag": 180, "zaterdag": 180}
    sessies = [_sessie("Long run", 120),
               _sessie("Threshold", 60, sport="VirtualRide", type_="threshold")]
    result = solve_week(sessies, _slots(avail))
    assert result.status == "OPTIMAL"
    assert len(result.placements) == 2
    hard = _by_name(result, "Threshold")
    assert any("zware dag" in n for n in hard.notes)


def test_strict_hard_spacing_wordt_hard():
    """Strict: zelfde scenario → INFEASIBLE (oude SchedulingConflict)."""
    avail = {"vrijdag": 180, "zaterdag": 180}
    sessies = [_sessie("Long run", 120),
               _sessie("Threshold", 60, sport="VirtualRide", type_="threshold")]
    result = solve_week(sessies, _slots(avail),
                        options=SolverOptions(strict=True))
    assert result.status == "INFEASIBLE"
    assert len(result.dropped) == 1


# ── Runs back-to-back ───────────────────────────────────────────────────────

def test_runs_niet_back_to_back_default():
    avail = {d: 60 for d in DAYS_NL}
    sessies = [_sessie("Z2 run", 45), _sessie("Herstelrun", 40, type_="recovery"),
               _sessie("Z2 run 2", 50)]
    result = solve_week(sessies, _slots(avail))
    indices = sorted(DAYS_NL.index(_dag(pl)) for pl in result.placements)
    for a, b in zip(indices, indices[1:]):
        assert b - a >= 2, f"Runs back-to-back: {indices}"


def test_runs_b2b_toggle_aan_staat_aangrenzend_toe():
    avail = {"vrijdag": 60, "zaterdag": 60}
    sessies = [_sessie("Z2 run 1", 45), _sessie("Z2 run 2", 45)]
    result = solve_week(sessies, _slots(avail),
                        options=SolverOptions(runs_back_to_back_ok=True))
    assert result.status == "OPTIMAL"
    assert sorted(_dag(pl) for pl in result.placements) == ["vrijdag", "zaterdag"]


def test_runs_b2b_toggle_uit_dropt_tweede_run():
    avail = {"vrijdag": 60, "zaterdag": 60}
    sessies = [_sessie("Z2 run 1", 45), _sessie("Z2 run 2", 45)]
    result = solve_week(sessies, _slots(avail),
                        options=SolverOptions(runs_back_to_back_ok=False))
    assert result.status == "INFEASIBLE"
    assert len(result.placements) == 1
    assert len(result.dropped) == 1


def test_nooit_twee_runs_zelfde_dag_ook_met_toggle():
    avail = {"zaterdag": 180}
    sessies = [_sessie("Z2 run 1", 45), _sessie("Z2 run 2", 45)]
    result = solve_week(sessies, _slots(avail),
                        options=SolverOptions(runs_back_to_back_ok=True))
    za_runs = [pl for pl in result.placements if _dag(pl) == "zaterdag"]
    assert len(za_runs) == 1


# ── Minimale verschuiving (de kern van Planner v2) ─────────────────────────

def test_minimale_verschuiving_bij_rustdag():
    """Week gepland; woensdag wordt rustdag → ALLEEN de woensdag-sessie
    verhuist, de rest blijft exact staan (datum + starttijd)."""
    sessies = [
        _sessie("Long run", 150, event_id="e_long"),
        _sessie("Threshold bike", 60, sport="VirtualRide", type_="threshold",
                event_id="e_thr"),
        _sessie("Z2 run", 45, event_id="e_run"),
        _sessie("Easy bike", 60, sport="VirtualRide", type_="endurance_ride",
                event_id="e_bike"),
    ]
    current_plan = {
        "e_long": (_day("zaterdag"), "07:00"),
        "e_thr": (_day("dinsdag"), "07:00"),
        "e_run": (_day("donderdag"), "07:00"),
        "e_bike": (_day("woensdag"), "07:00"),
    }
    avail = {"maandag": 90, "dinsdag": 90, "woensdag": 0, "donderdag": 90,
             "vrijdag": 90, "zaterdag": 240, "zondag": 90}
    result = solve_week(sessies, _slots(avail), current_plan=current_plan)
    assert result.status == "OPTIMAL"
    assert not result.dropped

    by_key = {pl.key: pl for pl in result.placements}
    # Onveranderde sessies: exact dezelfde dag + starttijd
    for key in ("e_long", "e_thr", "e_run"):
        assert by_key[key].date == current_plan[key][0], key
        assert by_key[key].slot_start == current_plan[key][1], key
        assert by_key[key].moved_days == 0
    # Alleen de woensdag-sessie is verhuisd
    assert by_key["e_bike"].date != _day("woensdag")
    assert by_key["e_bike"].moved_days >= 1


def test_verplaatsingsterm_houdt_stabiel_plan_intact():
    """Zelfde slots + current_plan uit een eerdere solve → niets beweegt."""
    avail = {"maandag": 90, "dinsdag": 60, "woensdag": 90, "donderdag": 60,
             "vrijdag": 240, "zaterdag": 240, "zondag": 90}
    sessies = [
        _sessie("Long run 120", 120),
        _sessie("Long ride 150", 150, sport="VirtualRide", type_="endurance_ride"),
        _sessie("Threshold 60", 60, type_="threshold"),
        _sessie("Z2 run 45", 45),
    ]
    first = solve_week(sessies, _slots(avail))
    plan = {pl.key: (pl.date, pl.slot_start) for pl in first.placements}
    second = solve_week(sessies, _slots(avail), current_plan=plan)
    assert {pl.key: pl.date for pl in second.placements} == \
        {pl.key: pl.date for pl in first.placements}
    assert all(pl.moved_days == 0 for pl in second.placements)


# ── Locked ──────────────────────────────────────────────────────────────────

def test_locked_placement_blijft_staan():
    """Locked sessie blijft op zijn (suboptimale) dag, ook al is een
    ruimer venster beschikbaar."""
    avail = {"zaterdag": 240, "zondag": 170}
    sessies = [_sessie("Long run", 150, event_id="L1")]
    current_plan = {"L1": (_day("zondag"), "07:00")}
    result = solve_week(sessies, _slots(avail),
                        current_plan=current_plan, locked={"L1"})
    assert result.status == "OPTIMAL"
    assert _dag(result.placements[0]) == "zondag"
    assert any("Vastgezet" in n for n in result.placements[0].notes)


# ── Context (indoor/outdoor) ────────────────────────────────────────────────

def test_indoor_only_slot_krijgt_geen_outdoor_run():
    avail = {"dinsdag": 60, "zaterdag": 180}
    ctx = {"zaterdag": "indoor_only"}
    sessies = [_sessie("Z2 run", 50),
               _sessie("Zwift ride", 90, sport="VirtualRide",
                       type_="endurance_ride")]
    result = solve_week(sessies, _slots(avail, ctx))
    run = _by_name(result, "Z2 run")
    ride = _by_name(result, "Zwift ride")
    assert _dag(run) == "dinsdag"      # run mag niet op het indoor-slot
    assert _dag(ride) == "zaterdag"    # VirtualRide wel


def test_outdoor_only_slot_krijgt_geen_virtualride():
    avail = {"donderdag": 120, "zaterdag": 180}
    ctx = {"zaterdag": "outdoor_only"}
    sessies = [_sessie("Zwift ride", 90, sport="VirtualRide",
                       type_="endurance_ride")]
    result = solve_week(sessies, _slots(avail, ctx))
    assert _dag(result.placements[0]) == "donderdag"


# ── Onoplosbare week → INFEASIBLE + drop-suggestie ─────────────────────────

def test_onoplosbaar_dropt_easy_eerst():
    """Slechts één venster van 60 min voor hard + easy → easy sneuvelt."""
    avail = {"dinsdag": 60}
    sessies = [_sessie("Threshold", 60, sport="VirtualRide", type_="threshold"),
               _sessie("Herstelrun", 50, type_="recovery")]
    result = solve_week(sessies, _slots(avail))
    assert result.status == "INFEASIBLE"
    assert [d.kind for d in result.dropped] == ["easy"]
    assert len(result.placements) == 1
    assert result.placements[0].naam == "Threshold"
    assert result.notes  # leesbare relaxatie-suggestie


def test_max_sessies_per_dag_dropt_vulling_eerst():
    """Een brede open dag absorbeert niet meer de hele week."""
    avail = {"vrijdag": 14 * 60}
    sessies = [
        _sessie("Long run", 150, type_="lange_duur"),
        _sessie("Threshold bike", 60, sport="VirtualRide", type_="threshold"),
        _sessie("Easy bike 1", 45, sport="VirtualRide", type_="endurance_ride"),
        _sessie("Easy bike 2", 45, sport="VirtualRide", type_="endurance_ride"),
        _sessie("Easy bike 3", 45, sport="VirtualRide", type_="endurance_ride"),
    ]
    result = solve_week(
        sessies,
        _slots(avail),
        weights={},
        max_sessions_per_day=2,
    )
    assert result.status == "INFEASIBLE"
    assert len(result.placements) <= 2
    assert {pl.naam for pl in result.placements} == {"Long run", "Threshold bike"}
    assert {dr.naam for dr in result.dropped} == {
        "Easy bike 1",
        "Easy bike 2",
        "Easy bike 3",
    }
    assert result.notes and "max 2 sessies/dag" in result.notes[0]


def test_max_sessies_per_dag_is_explicit_te_verhogen():
    avail = {"vrijdag": 14 * 60}
    sessies = [
        _sessie("Long run", 150, type_="lange_duur"),
        _sessie("Threshold bike", 60, sport="VirtualRide", type_="threshold"),
        _sessie("Easy bike", 45, sport="VirtualRide", type_="endurance_ride"),
    ]
    result = solve_week(
        sessies,
        _slots(avail),
        options=SolverOptions(max_sessions_per_day=3),
        weights={},
    )
    assert result.status == "OPTIMAL"
    assert len(result.placements) == 3


def test_geen_enkel_venster_geeft_infeasible():
    result = solve_week([_sessie("Z2 run", 45)],
                        _slots({d: 0 for d in DAYS_NL}))
    assert result.status == "INFEASIBLE"
    assert result.dropped


# ── Starttijden ─────────────────────────────────────────────────────────────

def test_starttijden_vallen_binnen_slots():
    """Twee sessies in één venster stapelen vanaf de slot-start; alles
    blijft binnen het venster."""
    avail = {"zaterdag": 240}  # 07:00 - 11:00
    sessies = [_sessie("Long run", 150),
               _sessie("Easy bike", 60, sport="VirtualRide",
                       type_="endurance_ride")]
    result = solve_week(sessies, _slots(avail))
    assert result.status == "OPTIMAL"
    long_pl = _by_name(result, "Long run")
    bike_pl = _by_name(result, "Easy bike")
    assert long_pl.slot_start == "07:00"   # long eerst in het venster
    assert bike_pl.slot_start == "09:30"   # gestapeld na de long
    for pl, dur in ((long_pl, 150), (bike_pl, 60)):
        start = to_minutes(pl.slot_start)
        assert to_minutes("07:00") <= start < to_minutes("11:00")
        assert start + dur <= to_minutes(pl.slot_end)


def test_starttijd_volgt_slot_start():
    avail_slots = {_day(d): [] for d in DAYS_NL}
    di = _day("dinsdag")
    avail_slots[di] = [_slot(di, 75, start="18:00")]
    result = solve_week([_sessie("Z2 run", 45)], avail_slots)
    assert result.placements[0].slot_start == "18:00"


# ── Echte week-scenario (port) ──────────────────────────────────────────────

def _real_week():
    avail = {"maandag": 90, "dinsdag": 60, "woensdag": 90, "donderdag": 60,
             "vrijdag": 240, "zaterdag": 240, "zondag": 90}
    sessies = [
        _sessie("Long run 120", 120),
        _sessie("Long ride 150", 150, sport="VirtualRide",
                type_="endurance_ride"),
        _sessie("Threshold 60", 60, type_="threshold"),
        _sessie("VO2max 45", 45, type_="vo2max", sport="VirtualRide"),
        _sessie("Z2 run 45", 45),
        _sessie("Herstel 40", 40, type_="recovery"),
    ]
    return sessies, _slots(avail)


def test_real_week_scenario():
    sessies, slots = _real_week()
    result = solve_week(sessies, slots)
    assert not result.dropped
    assert len(result.placements) == 6

    long_dagen = {_dag(pl) for pl in result.placements if pl.kind == "long"}
    assert long_dagen == {"vrijdag", "zaterdag"}

    hard_idx = sorted(DAYS_NL.index(_dag(pl)) for pl in result.placements
                      if pl.kind == "hard")
    assert hard_idx[1] - hard_idx[0] >= 2
    assert "donderdag" not in {_dag(pl) for pl in result.placements
                               if pl.kind == "hard"}

    run_idx = sorted({DAYS_NL.index(_dag(pl)) for pl in result.placements
                      if (pl.sport or "").lower() == "run"})
    for a, b in zip(run_idx, run_idx[1:]):
        assert b - a >= 2, f"Runs back-to-back: {run_idx}"


# ── Determinisme ────────────────────────────────────────────────────────────

def test_determinisme_zelfde_input_zelfde_output():
    sessies, slots = _real_week()
    r1 = solve_week(sessies, slots)
    r2 = solve_week(sessies, slots)
    assert r1.model_dump() == r2.model_dump()


# ── Gewichten tunebaar via athlete_state ───────────────────────────────────

def test_solver_weights_uit_athlete_state():
    from core.slot_solver import DEFAULT_WEIGHTS, load_weights

    weights = load_weights({"solver_weights": {"move_per_day": 99}})
    assert weights["move_per_day"] == 99
    assert weights["hard_adjacent"] == DEFAULT_WEIGHTS["hard_adjacent"]


# ── Injury-gate ─────────────────────────────────────────────────────────────

def test_injury_gate_weert_harde_run():
    avail = {d: 90 for d in DAYS_NL}
    sessies = [_sessie("Tempoduurloop", 50, type_="tempoloon"),
               _sessie("Herstelrun", 40, type_="recovery")]
    result = solve_week(sessies, _slots(avail),
                        options=SolverOptions(no_run_intensity=True))
    # tempo bevat 'tempo' → hard → geweerd door de gate
    assert result.status == "OPTIMAL"  # gate is geen relaxatie-failure
    assert [pl.naam for pl in result.placements] == ["Herstelrun"]
    assert result.dropped and "Injury-gate" in result.dropped[0].reason


# ── Performantie (UPGRADE_PLAN §5.4: week in < 2 s, assert ruim < 10 s) ─────

def test_solver_lost_volle_week_op_binnen_tijdslimiet():
    import time

    sessies, slots = _real_week()
    sessies = sessies + [
        _sessie("Kracht A", 35, sport="WeightTraining", type_="strength"),
        _sessie("Kracht B", 35, sport="WeightTraining", type_="strength"),
        _sessie("Extra Z2 bike", 60, sport="VirtualRide",
                type_="endurance_ride"),
    ]
    t0 = time.perf_counter()
    result = solve_week(sessies, slots)
    elapsed = time.perf_counter() - t0
    assert result.placements
    assert elapsed < 10.0, f"Solver te traag: {elapsed:.1f}s (richtlijn < 2 s)"


# ── persist_placements helper ───────────────────────────────────────────────

def test_persist_placements_schrijft_naar_db(tmp_path, monkeypatch):
    import history_db
    from core.slot_solver import persist_placements

    monkeypatch.setattr(history_db, "DB_PATH", tmp_path / "test.db")
    avail = {"zaterdag": 240}
    result = solve_week([_sessie("Long run", 150, event_id="ev42")],
                        _slots(avail))
    errors = persist_placements(result.placements)
    assert errors == []
    rec = history_db.get_placement("ev42")
    assert rec is not None
    assert rec["date"] == _day("zaterdag").isoformat()
    assert rec["slot_start"] == "07:00"
    assert rec["session_kind"] == "long"
    assert rec["solver_notes"]


# ── Property-based (hypothesis): hard constraints nooit geschonden ──────────

try:
    from hypothesis import given, settings
    from hypothesis import strategies as hst
    HAS_HYPOTHESIS = True
except ImportError:  # pragma: no cover
    HAS_HYPOTHESIS = False

if HAS_HYPOTHESIS:
    _session_strategy = hst.lists(
        hst.tuples(
            hst.sampled_from(["Run", "VirtualRide", "WeightTraining"]),
            hst.sampled_from(["z2_standard", "recovery", "threshold",
                              "vo2max", "endurance_ride", "strength"]),
            hst.integers(min_value=20, max_value=180),
        ),
        min_size=1, max_size=8,
    )
    _slots_strategy = hst.dictionaries(
        keys=hst.integers(min_value=0, max_value=6),
        values=hst.lists(
            hst.tuples(
                hst.integers(min_value=5 * 60, max_value=18 * 60),  # start
                hst.integers(min_value=30, max_value=300),          # duur
                hst.sampled_from(["any", "indoor_only", "outdoor_only"]),
            ),
            min_size=1, max_size=2,
        ),
        min_size=1, max_size=7,
    )

    @settings(max_examples=40, deadline=None)
    @given(sessions_raw=_session_strategy, slots_raw=_slots_strategy)
    def test_property_hard_constraints_nooit_geschonden(sessions_raw,
                                                        slots_raw):
        sessies = [
            _sessie(f"S{i} {t}", dur, sport=sport, type_=t)
            for i, (sport, t, dur) in enumerate(sessions_raw)
        ]
        slots_by_date = {_day(d): [] for d in DAYS_NL}
        for weekday, slot_list in slots_raw.items():
            d = WEEK_START + timedelta(days=weekday)
            day_slots = []
            for start_min, dur, ctx in slot_list:
                end_min = min(start_min + dur, 23 * 60 + 59)
                if end_min <= start_min:
                    continue
                day_slots.append(Slot(date=d, start=to_hhmm(start_min),
                                      end=to_hhmm(end_min), context=ctx))
            # Niet-overlappend maken: sorteer en laat overlappende vallen.
            day_slots.sort(key=lambda s: s.start_min)
            cleaned, cursor = [], 0
            for s in day_slots:
                if s.start_min < cursor:
                    continue
                cleaned.append(s)
                cursor = s.end_min
            slots_by_date[d] = cleaned

        result = solve_week(sessies, slots_by_date)

        by_key = {f"s{i}": s for i, s in enumerate(sessies)}
        per_day_longs: dict = {}
        per_day_runs: dict = {}
        run_days = set()
        for pl in result.placements:
            sess = by_key[pl.key]
            kind = classify_session(sess)
            # 1. Starttijd binnen een venster; sessie past (duur ≤ slot + 10).
            host = next(
                (s for s in (slots_by_date.get(pl.date) or [])
                 if s.start_min <= to_minutes(pl.slot_start) < s.end_min),
                None,
            )
            assert host is not None, "starttijd buiten elk venster"
            assert sess["duur_min"] <= host.duration_min + 10
            assert (to_minutes(pl.slot_start) + sess["duur_min"]
                    <= host.end_min + 10), "sessie loopt uit het venster"
            # 2. Context-regels.
            sport = (sess["sport"] or "").lower()
            if host.context == "indoor_only":
                assert sport in ("virtualride", "weighttraining")
            if host.context == "outdoor_only":
                assert sport != "virtualride"
            # 3. Tellers voor dag-regels.
            if kind == "long":
                per_day_longs[pl.date] = per_day_longs.get(pl.date, 0) + 1
            if sport == "run":
                per_day_runs[pl.date] = per_day_runs.get(pl.date, 0) + 1
                run_days.add(pl.date)

        assert all(v <= 1 for v in per_day_longs.values()), "2 longs zelfde dag"
        assert all(v <= 1 for v in per_day_runs.values()), "2 runs zelfde dag"
        # 4. Runs nooit back-to-back (default toggle uit).
        for d in run_days:
            assert d + timedelta(days=1) not in run_days, "runs back-to-back"
