"""Regressietests voor intervals.icu step-syntax in run-templates.

intervals.icu parseert een pace-target alleen als de step-regel de vorm
"- <afstand> <m:ss>/km Pace" heeft (keyword "Pace" verplicht, geen "@").
Met "@" of zonder "Pace" valt de rep terug op Z1 en klopt de load niet
(empirisch geverifieerd met probe-events, 2026-07-05).
"""
from __future__ import annotations

import re

import pytest

from agents.endurance_coach import _DREMPEL_PLAN, _drempel_run

# "- 1km 4:20/km Pace" of "- 1.5km 4:15/km Pace" — tekst erachter mag.
_STEP_OK = re.compile(r"^- \d+(?:\.\d+)?km \d:\d{2}/km Pace\b", re.MULTILINE)


@pytest.mark.parametrize("week", sorted(_DREMPEL_PLAN) + [99])
def test_drempel_step_is_intervals_icu_parseable(week):
    desc = _drempel_run(week)["beschrijving"]
    assert _STEP_OK.search(desc), f"wk {week}: geen parseable pace-step:\n{desc[:300]}"
    # Het oude, kapotte formaat mag nooit terugkomen in een step-regel.
    assert not re.search(r"^- .*@", desc, re.MULTILINE), f"wk {week}: '@' in step-regel"


def test_drempel_progressie_pace_en_blokken():
    # De twee assen: pace omlaag en blokduur omhoog richting wk 21/22.
    assert _drempel_run(14)["naam"] == "Drempel – 5×1000m @ 4:20/km"
    assert "2×3km" in _drempel_run(21)["naam"] and "4:15/km" in _drempel_run(21)["naam"]
    assert "4:08/km" in _drempel_run(22)["naam"]


def test_warmup_ramp_niet_op_wandeltempo():
    # 55% van drempelpace = 7:53/km — geen opwarming voor een drempelsessie.
    for wk in sorted(_DREMPEL_PLAN):
        desc = _drempel_run(wk)["beschrijving"]
        assert "55-78%" not in desc and "ramp 65-82%" in desc


def test_cruise_step_is_parseable_en_rustiger_dan_intervallen():
    from agents.endurance_coach import _CRUISE_PLAN, _drempel_cruise

    cruise_step = re.compile(r"^- \d+m \d:\d{2}/km Pace\b", re.MULTILINE)
    for wk in sorted(_CRUISE_PLAN):
        s = _drempel_cruise(wk)
        assert cruise_step.search(s["beschrijving"]), f"wk {wk}: geen parseable cruise-step"
        # Cruise moet rustiger zijn dan de intervalsessie van diezelfde week.
        interval_pace = _DREMPEL_PLAN.get(wk, (0, 0, 0, 255))[3]
        cruise_pace = _CRUISE_PLAN[wk][3]
        assert cruise_pace > interval_pace, f"wk {wk}: cruise niet rustiger dan intervallen"


def test_dubbele_drempel_vanaf_wk17_niet_in_deload():
    from datetime import date, timedelta

    from agents.endurance_coach import plan_sessions

    ig = {"run_intensity_allowed": True, "strides_allowed": True,
          "tempo_allowed": True, "volume_modifier": 1.0}
    lm = {"recommended_weekly_tss": 650}

    def _types(week_nr, deload=False):
        guard = dict(ig, _is_deload_week=deload)
        monday = date(2026, 4, 6) + timedelta(weeks=week_nr - 1)
        from agents import marathon_periodizer as mp
        vol = mp.calculate_weekly_run_volume(week_nr)
        out = plan_sessions(phase=vol["fase"], injury_guard=guard,
                            load_manager=lm, week_start=monday,
                            marathon_volume=vol)
        return [s.get("type") for s in out]

    assert "drempel_cruise" in _types(17)
    assert "drempel_cruise" not in _types(15, deload=True)  # deloadweek: 1 drempel
    assert "drempel_cruise" not in _types(14)               # vóór wk 17: 1 drempel


def test_bike_week_geen_threshold_bij_dubbele_run_drempel():
    from agents.bike_coach import select_bike_sessions_for_week

    sessies = select_bike_sessions_for_week(17, "transformatie_I", {"ftp": 290})
    types = {s.get("type") for s in sessies}
    assert "threshold" not in types, "fiets mag geen 3e LT-dag toevoegen"
    # Wél gewoon aeroob volume blijven leveren.
    assert types & {"long_slow", "fatmax_medium", "fatmax_lang"}
