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
