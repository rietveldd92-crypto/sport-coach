from datetime import date

from agents.day_assigner import assign_days
from agents.week_skeleton import SkeletonSlot


WEEK_START = date(2026, 7, 13)
DAYS_NL = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag",
           "zaterdag", "zondag"]


def _run(name, type_, minutes=60):
    return {
        "naam": name,
        "type": type_,
        "duur_min": minutes,
        "tss_geschat": minutes,
        "sport": "Run",
        "beschrijving": "test",
    }


def _bike(name="Bike fill", type_="endurance_ride", minutes=60):
    return {
        "naam": name,
        "type": type_,
        "duur_min": minutes,
        "tss_geschat": minutes,
        "sport": "VirtualRide",
        "beschrijving": "test",
    }


def _base_skeleton():
    return [
        SkeletonSlot(_run("Interval A", "run_threshold_short"), "interval_a", 1),
        SkeletonSlot(_run("Interval B", "run_threshold_long"), "interval_b", 1),
        SkeletonSlot(_run("Long run", "long_run", 120), "long_run", 1),
    ]


def _day_map(placed):
    return {s["_skeleton_role"]: s["dag"] for s in placed}


def test_long_op_meeste_tijd_tiebreak_richting_zondag():
    skeleton = [SkeletonSlot(_run("Long run", "long_run", 120), "long_run", 1)]
    availability = {d: 60 for d in DAYS_NL}
    availability["vrijdag"] = 180
    availability["zondag"] = 180

    placed, warnings = assign_days(skeleton, availability, week_start=WEEK_START)

    assert not [w for w in warnings if w["code"] != "available_day_left_empty"]
    assert placed[0]["dag"] == "zondag"
    assert "meeste beschikbare tijd" in placed[0]["plaatsing_reden"]


def test_intervallen_gespreid_en_niet_naast_long():
    availability = {d: 90 for d in DAYS_NL}
    availability["zondag"] = 180

    placed, warnings = assign_days(_base_skeleton(), availability, week_start=WEEK_START)
    by_role = _day_map(placed)

    assert not [w for w in warnings if w["code"] != "available_day_left_empty"]
    assert by_role["long_run"] == "zondag"
    assert abs(DAYS_NL.index(by_role["interval_a"]) - DAYS_NL.index(by_role["interval_b"])) >= 2
    assert all(
        abs(DAYS_NL.index(by_role[role]) - DAYS_NL.index("zondag")) >= 2
        for role in ("interval_a", "interval_b")
    )


def test_krappe_week_plaatst_zoveel_mogelijk_met_warnings_en_max_een_per_dag():
    availability = {d: 0 for d in DAYS_NL}
    availability.update({"maandag": 60, "dinsdag": 60, "woensdag": 60})

    placed, warnings = assign_days(_base_skeleton(), availability, week_start=WEEK_START)

    assert len(placed) == 3
    assert len({s["dag"] for s in placed}) == len(placed)
    assert any(w["code"] == "interval_spacing_compromised" for w in warnings)


def test_commute_blijft_vast_ook_zonder_availability():
    skeleton = [
        SkeletonSlot(_bike("Forenzen-rit", "commute", 100), "commute", 2, vaste_dag="dinsdag")
    ]
    availability = {d: 0 for d in DAYS_NL}

    placed, warnings = assign_days(skeleton, availability, week_start=WEEK_START)

    assert warnings == []
    assert placed[0]["dag"] == "dinsdag"
    assert "niet verplaatsbaar" in placed[0]["plaatsing_reden"]


def test_geen_sessie_op_dag_zonder_avail_behalve_commute():
    skeleton = _base_skeleton() + [
        SkeletonSlot(_bike("Forenzen-rit", "commute", 100), "commute", 2, vaste_dag="dinsdag")
    ]
    availability = {d: 0 for d in DAYS_NL}
    availability.update({"maandag": 60, "woensdag": 60, "vrijdag": 180})

    placed, _ = assign_days(skeleton, availability, week_start=WEEK_START)

    for sessie in placed:
        if sessie["_skeleton_role"] == "commute":
            continue
        assert availability[sessie["dag"]] > 0


def test_lege_beschikbare_dag_krijgt_zichtbare_reden():
    skeleton = _base_skeleton()
    availability = {d: 90 for d in DAYS_NL}

    placed, warnings = assign_days(skeleton, availability, week_start=WEEK_START)

    used = {s["dag"] for s in placed}
    empty_available = [d for d in DAYS_NL if d not in used and availability[d] >= 45]
    assert empty_available
    warned_days = {w["dag"] for w in warnings if w["code"] == "available_day_left_empty"}
    assert set(empty_available) <= warned_days


def test_elke_geplaatste_sessie_heeft_reden_en_output_is_deterministisch():
    skeleton = _base_skeleton() + [SkeletonSlot(_bike(), "bike_fill", 3)]
    availability = {d: 90 for d in DAYS_NL}
    availability["zondag"] = 180

    first = assign_days(skeleton, availability, week_start=WEEK_START)
    second = assign_days(skeleton, availability, week_start=WEEK_START)

    assert first == second
    placed, _ = first
    assert all(s.get("plaatsing_reden") for s in placed)


def test_availability_wordt_begrensd_op_zes_uur():
    skeleton = [SkeletonSlot(_run("Long run", "long_run", 120), "long_run", 1)]
    availability = {d: 0 for d in DAYS_NL}
    availability["vrijdag"] = 18 * 60

    placed, warnings = assign_days(skeleton, availability, week_start=WEEK_START)

    assert placed[0]["dag"] == "vrijdag"
    assert any(w["code"] == "availability_clamped" for w in warnings)
    assert "360 min" in placed[0]["plaatsing_reden"]


def test_bike_fill_past_duur_op_de_dag():
    """Een 165-min rit hoort niet op een 60-min dag; een kortere vulling wel."""
    skeleton = [
        SkeletonSlot(_bike("Long endurance", minutes=165), "bike_fill", 3),
        SkeletonSlot(_bike("Duurrit 60", minutes=60), "bike_fill", 3),
    ]
    availability = {"maandag": 60, "zaterdag": 180}

    placed, _ = assign_days(skeleton, availability, week_start=WEEK_START)

    by_day = {s["dag"]: s["naam"] for s in placed}
    assert by_day.get("zaterdag") == "Long endurance"
    assert by_day.get("maandag") == "Duurrit 60"


def test_niet_passende_fill_wordt_overgeslagen_niet_geforceerd():
    skeleton = [
        SkeletonSlot(_bike("Long endurance", minutes=165), "bike_fill", 3),
        SkeletonSlot(_bike("Duurrit 75", minutes=75), "bike_fill", 3),
    ]
    availability = {"woensdag": 90}

    placed, _ = assign_days(skeleton, availability, week_start=WEEK_START)

    assert [s["naam"] for s in placed] == ["Duurrit 75"]
