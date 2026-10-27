"""PLANLOGICA-V4: blokplanner voor 10k/5k (skelet, plaatsing, raceweken, kracht)."""
from datetime import date

from agents import block_library as bl
from agents import block_planner as bp
from agents import pijlers, week_planner

ANCHORS = bl.Anchors(threshold_sec=256, vvo2_sec=231, aet_sec=307, bronnen={})
FULL = {d: 160 for d in bp.DAYS_NL}
MON = date(2026, 11, 2)


def _ctx(**kw):
    base = dict(week_start=MON, goal_type="10k", run_count=4, availability=dict(FULL),
                steps={"vo2": 1, "subt": 1, "long": 1, "bike": 1, "race_pace": 1})
    base.update(kw)
    return bp.BlockWeekContext(**base)


def _runs(sessions):
    return [s for s in sessions if s["sport"] == "Run"]


def _idx(s):
    return bp.DAYS_NL.index(s["dag"])


def _assert_no_adjacent_runs(sessions, extra_days=()):
    days = sorted({_idx(s) for s in _runs(sessions)} | set(extra_days))
    assert all(b - a >= 2 for a, b in zip(days, days[1:])), days


def test_vier_runweek_heeft_twee_kwaliteiten_long_easy_en_fiets_subt():
    sessions, warnings = bp.plan_block_week(_ctx(), ANCHORS)
    runs = _runs(sessions)
    assert len(runs) == 4
    assert sorted(s["_skeleton_role"] for s in runs) == ["easy", "long", "quality", "quality"]
    assert {s["type"] for s in runs if s["_skeleton_role"] == "quality"} == {"vo2_run", "run_subthreshold"}
    _assert_no_adjacent_runs(sessions)
    subt = next(s for s in sessions if s["type"] == "bike_subt")
    quality_days = {_idx(s) for s in runs if s["_skeleton_role"] == "quality"}
    assert _idx(subt) - 1 in quality_days      # de dag NA een lopende kwaliteit
    assert _idx(subt) + 1 not in quality_days  # nooit de dag ervóór
    assert not warnings


def test_drie_runweek_heeft_een_kwaliteit():
    sessions, _ = bp.plan_block_week(_ctx(run_count=3, next_week_run_count=4), ANCHORS)
    runs = _runs(sessions)
    assert len(runs) == 3
    assert [s["type"] for s in runs if s["_skeleton_role"] == "quality"] == ["vo2_run"]
    # Zondag lopen vóór een 4-runweek zou volgende week een run kosten.
    assert all(s["dag"] != "zondag" for s in runs)


def test_zondag_gelopen_dan_maandag_geen_run():
    sessions, _ = bp.plan_block_week(_ctx(prev_week_sunday_run=True, run_count=3), ANCHORS)
    assert all(s["dag"] != "maandag" for s in _runs(sessions))


def test_c_race_vervangt_sub_t_niet_de_vo2_run():
    race = bp.Race(datum=date(2026, 11, 8), naam="parkrun", distance_km=5, priority="C")
    sessions, _ = bp.plan_block_week(_ctx(races=[race]), ANCHORS)
    runs = _runs(sessions)
    types = [s["type"] for s in runs]
    assert "vo2_run" in types and "run_subthreshold" not in types
    assert len(runs) == 3  # race telt als vierde run
    _assert_no_adjacent_runs(sessions, extra_days=[6])


def test_zaterdagrace_in_vier_runweek_laat_easy_vallen_in_plaats_van_aaneen_lopen():
    race = bp.Race(datum=date(2026, 11, 7), naam="parkrun", distance_km=5, priority="C")
    sessions, warnings = bp.plan_block_week(_ctx(races=[race]), ANCHORS)
    assert len(_runs(sessions)) == 2
    _assert_no_adjacent_runs(sessions, extra_days=[5])
    assert any(w["code"] == "run_dropped_no_days" for w in warnings)


def test_b_race_15km_vervangt_long_en_krijgt_racetempo_plus_openers():
    race = bp.Race(datum=date(2026, 12, 13), naam="Bruggenloop", distance_km=15,
                   priority="B", race_pace_sec=248)
    ctx = _ctx(week_start=date(2026, 12, 7), run_count=3, races=[race], next_race=race)
    sessions, _ = bp.plan_block_week(ctx, ANCHORS)
    runs = _runs(sessions)
    assert sorted(s["type"] for s in runs) == ["openers", "race_pace"]
    assert all(s["dag"] != "zaterdag" for s in runs)       # dag vóór de race vrij
    rp = next(s for s in runs if s["type"] == "race_pace")
    assert "4:08" in rp["naam"]
    assert 6 - _idx(rp) >= 3                                # kwaliteit >=3 dagen voor de race
    assert "2x12" in next(s for s in sessions if s["type"] == "bike_subt")["naam"]  # taper


def test_racetempo_alleen_in_aanloop_naar_a_race():
    a_race = bp.Race(datum=date(2027, 5, 30), naam="Leiden", distance_km=10, priority="A", race_pace_sec=229)
    assert bp.block_gate(_ctx(week_start=date(2027, 5, 10), next_race=a_race)) == "race_specifiek"
    assert bp.block_gate(_ctx(week_start=date(2027, 4, 26), next_race=a_race)) == "drempel"
    b_race = bp.Race(datum=date(2026, 12, 13), naam="B", distance_km=15, priority="B")
    assert bp.block_gate(_ctx(week_start=date(2026, 11, 30), next_race=b_race)) == "drempel"


def test_patroon_vier_drie_wisselt_per_week():
    pattern = {"counts": [4, 3], "start": "2026-11-02"}
    counts = [bp.run_count_for_week(date(2026, 11, 2 + 7 * i), pattern) for i in range(4)]
    assert counts == [4, 3, 4, 3]


def test_tredes_volgen_de_blokweek_en_cappen_op_zes():
    assert bp.block_steps(date(2026, 11, 2), "2026-11-02")["vo2"] == 1
    assert bp.block_steps(date(2026, 11, 16), "2026-11-02")["vo2"] == 3
    assert bp.block_steps(date(2027, 3, 1), "2026-11-02")["vo2"] == 6


def test_tijdband_en_racepace():
    assert bp.parse_time_seconds("38:00-38:45") == 2302
    assert bp.race_pace_for("15k", "1:02:00") == 248
    assert bp.race_pace_for("10k", None) is None


def test_ankers_vallen_terug_op_drempel():
    a = bl.load_anchors({"threshold_pace_sec_per_km": 256})
    assert a.bronnen["vvo2"] == "afgeleid van drempel"
    assert bl.load_anchors({"vvo2_pace_sec": 228}).vvo2_sec == 228


def test_pace_ranges_zijn_plus_min_vijf():
    s = bl.vo2_run(1, 0, ANCHORS)
    assert "3:46-3:56/km Pace" in s["beschrijving"]
    assert "400m" not in s["beschrijving"]


def test_nieuwe_sessies_hebben_een_pijler():
    assert pijlers.classify_pijler(bl.vo2_run(1, 0, ANCHORS)) == "vo2max"
    assert pijlers.classify_pijler(bl.subthreshold_run(1, 0, ANCHORS)) == "lactaatdrempel"
    assert pijlers.classify_pijler(bl.race_pace_run(1, 248, ANCHORS)) == "lactaatdrempel"
    assert pijlers.classify_pijler(bl.easy_run_asr(45, 0, ANCHORS)) == "running_economy"
    assert pijlers.classify_pijler(bl.long_run_block(80, 2, ANCHORS)) == "fatigue_resistance"


def test_kracht_blokweek_twee_keer_niet_voor_kwaliteit():
    sessions, _ = bp.plan_block_week(_ctx(), ANCHORS)
    dagen = week_planner._select_strength_days_block(sessions)
    assert len(dagen) == 2
    idx = [bp.DAYS_NL.index(d) for d in dagen]
    assert idx[1] - idx[0] >= 2
    hard = {_idx(s) for s in sessions if s["type"] in week_planner.BLOCK_QUALITY_TYPES | {"bike_subt"}}
    vo2 = {_idx(s) for s in sessions if s["type"] == "vo2_run"}
    for i in idx:
        assert i not in hard and i + 1 not in vo2


def test_herstelweek_na_ab_race_kalibratie_en_geen_fiets_subt():
    sessions, _ = bp.plan_block_week(_ctx(week_start=date(2026, 12, 14), recovery_week=True), ANCHORS)
    types = [s["type"] for s in sessions]
    assert "calibration_vvo2" in types
    assert "bike_subt" not in types
    assert not {"vo2_run", "run_subthreshold", "race_pace"} & set(types)


def test_blok_herstart_twee_weken_na_ab_race():
    race = date(2026, 12, 13)
    assert bp.effective_block_start("2026-11-02", race) == date(2026, 12, 21)
    assert bp.block_steps(date(2026, 12, 21), "2026-11-02", last_ab_race=race)["vo2"] == 1
    # Een oude race vóór de bloksstart verschuift niets.
    assert bp.effective_block_start("2026-11-02", date(2026, 10, 18)) == date(2026, 11, 2)
