"""Tests voor agents.shift_day.

Scenarios die moeten werken:
- Fit zonder shift (nieuwe avail accomodeert al het geplande)
- Z2 shift: run + bike op dag, avail halveert → Z2 run verhuist
- Hard blijft: threshold session shift niet, wordt overflow
- Injury return: geen 2 runs op opeenvolgende dagen
- Long run op zondag: geen run-shift naar zaterdag
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from agents import shift_day as sd


MONDAY = date(2026, 4, 20)  # willekeurige maandag
WEEK = [MONDAY + timedelta(days=i) for i in range(7)]
WEEK_ISO = [d.isoformat() for d in WEEK]
TUE, WED, THU, FRI, SAT, SUN = (d.isoformat() for d in WEEK[1:])


def _ev(eid: str, date_iso: str, name: str, sport: str = "Run",
        minutes: int = 60, tss: float = 50.0) -> dict:
    return {
        "id": eid,
        "start_date_local": f"{date_iso}T00:00:00",
        "name": name,
        "type": sport,
        "category": "WORKOUT",
        "moving_time": minutes * 60,
        "load_target": tss,
    }


def _full_avail() -> dict[str, int]:
    return {d: 120 for d in WEEK_ISO}


# ── Basis classificatie ───────────────────────────────────────────────────


def test_is_hard_threshold():
    assert sd.is_hard_event({"name": "Threshold 4x10"}) is True


def test_is_hard_long_run_niet_hard():
    """Long run is niet 'hard' in shift-context — het is een volumesessie
    die toevallig op zondag hoort, niet een kwaliteitsinterval."""
    assert sd.is_hard_event({"name": "Lange duurloop 22km"}) is False


def test_is_easy_z2():
    assert sd.is_easy_event({"name": "Z2 duurrit 90min"}) is True
    assert sd.is_easy_event({"name": "Endurance ride 75min"}) is True


def test_easy_niet_hard_tegelijk():
    evt = {"name": "Z2 + marathontempo"}
    assert sd.is_hard_event(evt) is True
    assert sd.is_easy_event(evt) is False  # marathontempo wint


def test_duration_parse():
    assert sd.event_duration_min({"moving_time": 2700}) == 45
    assert sd.event_duration_min({"name": "Z2 90 min easy"}) == 90
    assert sd.event_duration_min({"name": "foo"}) == 0


# ── Fit zonder shift ──────────────────────────────────────────────────────


def test_fit_zonder_shift():
    """60 min workout, avail blijft 120 min → niets hoeft te verhuizen."""
    events = [_ev("e1", TUE, "Z2 run 60 min", minutes=60)]
    avail = _full_avail()
    result = sd.plan_redistribution(
        events, avail, TUE, new_avail_min=120,
        week_start=MONDAY, today=MONDAY,
    )
    assert result["fits"] is True
    assert result["moves"] == []
    assert len(result["kept"]) == 1


# ── Shift Z2 naar andere dag ──────────────────────────────────────────────


def test_z2_run_shifts_naar_vrije_dag():
    """Run 45 min + bike 45 min op dinsdag, avail → 60. Z2 run verhuist."""
    events = [
        _ev("e1", TUE, "Z2 run 45 min", sport="Run", minutes=45),
        _ev("e2", TUE, "Z2 endurance ride 45 min", sport="VirtualRide", minutes=45),
    ]
    avail = _full_avail()
    # Woensdag is leeg, zou kandidaat moeten zijn
    result = sd.plan_redistribution(
        events, avail, TUE, new_avail_min=60,
        week_start=MONDAY, today=MONDAY,
    )
    assert result["fits"] is True
    assert len(result["moves"]) == 1
    # De langste easy (beide 45) wordt als eerste verwerkt; whichever one shifts
    move = result["moves"][0]
    assert move["from"] == TUE
    assert move["to"] != TUE
    # Tijd-behoud: move bevat from_time gelijk aan origineel
    assert move["from_time"] == "00:00:00"  # onze fixture gebruikt T00:00:00


def test_move_bewaart_tijdstip():
    """Event dat om 06:30 staat moet met 06:30 verhuizen, niet middernacht."""
    evt = _ev("e1", TUE, "Z2 run", sport="Run", minutes=60)
    evt["start_date_local"] = f"{TUE}T06:30:00"
    events = [evt]
    avail = _full_avail()
    result = sd.plan_redistribution(
        events, avail, TUE, new_avail_min=0,
        week_start=MONDAY, today=MONDAY,
    )
    assert len(result["moves"]) == 1
    assert result["moves"][0]["from_time"] == "06:30:00"


def test_grotere_overflow_shift_meerdere():
    """3 Z2 sessies van 45 min op een dag, avail → 45 min. Twee verhuizen."""
    events = [
        _ev("e1", TUE, "Z2 easy 45 min", sport="Run", minutes=45),
        _ev("e2", TUE, "Z2 endurance 45 min", sport="VirtualRide", minutes=45),
        _ev("e3", TUE, "Z2 recovery 45 min", sport="VirtualRide", minutes=45),
    ]
    avail = _full_avail()
    result = sd.plan_redistribution(
        events, avail, TUE, new_avail_min=45,
        week_start=MONDAY, today=MONDAY,
    )
    assert result["fits"] is True
    assert len(result["moves"]) == 2
    assert len(result["kept"]) == 1


# ── Hard sessie blijft ────────────────────────────────────────────────────


def test_hard_session_overflow_blijft_staan():
    """Threshold session + Z2 run samen 120 min, avail → 60. Threshold
    mag niet automatisch verhuizen; verschijnt in overflow."""
    events = [
        _ev("e_hard", TUE, "Threshold 4x10 @ 95%", sport="VirtualRide", minutes=60),
        _ev("e_easy", TUE, "Z2 easy 60 min", sport="Run", minutes=60),
    ]
    avail = _full_avail()
    result = sd.plan_redistribution(
        events, avail, TUE, new_avail_min=60,
        week_start=MONDAY, today=MONDAY,
    )
    # Threshold blijft op dinsdag (hard/niet automatisch shiftbaar)
    assert not any(m["event_id"] == "e_hard" for m in result["moves"])
    # Z2 verhuist of zit in overflow
    e_easy_moved = any(m["event_id"] == "e_easy" for m in result["moves"])
    e_easy_overflow = any(o["event_id"] == "e_easy" for o in result["overflow"])
    assert e_easy_moved or e_easy_overflow


# ── Injury return: back-to-back run verbod ────────────────────────────────


def test_injury_return_voorkomt_back_to_back_run():
    """Z2 run op woensdag moet verhuizen, maar woensdag-1 (dinsdag) is
    de source-dag die al geldt als verplaatsing-van; maandag en donderdag
    hebben geen runs. Toch: bij injury_return mag ZATERDAG niet als
    kandidaat als vrijdag óf zondag al een run heeft.
    Hier: long run op zondag → bij injury_return mag run niet op zaterdag.
    """
    events = [
        _ev("e_shift", TUE, "Z2 run 60 min", sport="Run", minutes=60),
        _ev("e_lr", SUN, "Lange duurloop 18km", sport="Run", minutes=120),
    ]
    avail = {d: 120 for d in WEEK_ISO}
    avail[SAT] = 120  # zaterdag heeft genoeg tijd
    result = sd.plan_redistribution(
        events, avail, TUE, new_avail_min=0,
        week_start=MONDAY, today=MONDAY,
        injury_return=True,
    )
    # Shift moet gebeuren maar niet naar zaterdag (long run zondag + injury)
    assert len(result["moves"]) == 1
    assert result["moves"][0]["to"] != SAT


def test_injury_return_non_run_mag_wel_zaterdag():
    """Bike shift mag wel naar zaterdag bij injury return (geen back-to-back
    run)."""
    events = [
        _ev("e_shift", TUE, "Z2 endurance ride 60 min", sport="VirtualRide", minutes=60),
        _ev("e_lr", SUN, "Lange duurloop 18km", sport="Run", minutes=120),
    ]
    avail = {d: 120 for d in WEEK_ISO}
    result = sd.plan_redistribution(
        events, avail, TUE, new_avail_min=0,
        week_start=MONDAY, today=MONDAY,
        injury_return=True,
    )
    assert len(result["moves"]) == 1
    # Welke dag dan ook — belangrijk is dat shift lukt
    assert result["moves"][0]["to"] in WEEK_ISO


# ── Long run op zondag beschermt zaterdag ─────────────────────────────────


def test_long_run_zondag_blokkeert_run_op_zaterdag():
    """Zonder injury maar met long run op zondag: Z2 run mag niet naar
    zaterdag omdat dat back-to-back run + LR geeft."""
    events = [
        _ev("e_shift", TUE, "Z2 run 60 min", sport="Run", minutes=60),
        _ev("e_lr", SUN, "Lange duurloop 20km", sport="Run", minutes=140),
    ]
    # Enige vrije dag is zaterdag (alle andere dagen hebben runs/hard)
    events.extend([
        _ev("e_hard_wed", WED, "Threshold 4x10 @ 95%", sport="VirtualRide", minutes=60),
        _ev("e_hard_fri", FRI, "Sweetspot 3x12", sport="VirtualRide", minutes=60),
    ])
    avail = {d: 120 for d in WEEK_ISO}
    avail[MONDAY.isoformat()] = 0  # rust maandag
    avail[THU] = 0  # rust donderdag
    result = sd.plan_redistribution(
        events, avail, TUE, new_avail_min=0,
        week_start=MONDAY, today=MONDAY,
    )
    # Run mag niet naar zaterdag
    for m in result["moves"]:
        if m["event_id"] == "e_shift":
            assert m["to"] != SAT


# ── Rustdag blokkeert kandidaat ───────────────────────────────────────────


def test_rustdag_wordt_niet_gekozen():
    """0-minuten dag mag geen shift ontvangen."""
    events = [_ev("e1", TUE, "Z2 run 60 min", sport="Run", minutes=60)]
    avail = {d: 60 for d in WEEK_ISO}
    avail[WED] = 0  # rustdag — mag geen shift krijgen
    # Alle andere dagen zijn vol (60 min bezet elders)
    for d_iso in (THU, FRI, SAT, SUN):
        events.append(_ev(f"busy_{d_iso}", d_iso, "Z2 endurance",
                          sport="VirtualRide", minutes=60))
    result = sd.plan_redistribution(
        events, avail, TUE, new_avail_min=0,
        week_start=MONDAY, today=MONDAY,
    )
    # Er mag geen move naar WED zijn
    for m in result["moves"]:
        assert m["to"] != WED


# ── Geen kandidaat → overflow ─────────────────────────────────────────────


def test_geen_kandidaat_dan_overflow():
    """Alle andere dagen vol → event belandt in overflow."""
    events = [_ev("e_shift", TUE, "Z2 run 60 min", sport="Run", minutes=60)]
    # Alle andere dagen 0 min beschikbaar
    avail = {d: 0 for d in WEEK_ISO}
    avail[TUE] = 60
    result = sd.plan_redistribution(
        events, avail, TUE, new_avail_min=0,
        week_start=MONDAY, today=MONDAY,
    )
    assert result["fits"] is False
    assert len(result["overflow"]) == 1
    assert result["overflow"][0]["event_id"] == "e_shift"


# ── Verleden-datum wordt geskipt ──────────────────────────────────────────


def test_verleden_datum_is_geen_kandidaat():
    """Als 'today' woensdag is, mag maandag/dinsdag niet gekozen worden."""
    events = [_ev("e1", THU, "Z2 run 60 min", sport="Run", minutes=60)]
    avail = {d: 120 for d in WEEK_ISO}
    # Verleden (ma/di) moet genegeerd worden; vrij dagen beschikbaar
    result = sd.plan_redistribution(
        events, avail, THU, new_avail_min=0,
        week_start=MONDAY, today=WEEK[2],  # woensdag
    )
    for m in result["moves"]:
        move_to = date.fromisoformat(m["to"])
        assert move_to >= WEEK[2]
