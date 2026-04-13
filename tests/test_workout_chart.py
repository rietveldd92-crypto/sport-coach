"""Tests voor viz.workout_chart parser + render-guard."""
from __future__ import annotations

from viz.workout_chart import parse_workout_structure, render_workout_chart


SIMPLE = """Warmup
- 10m ramp 50-80% 90rpm

Main Set
2x
- 20m 97% 85rpm
- 5m 55% 95rpm

Cooldown
- 10m ramp 75-50%
"""


def test_parse_warmup_main_cooldown():
    ivs = parse_workout_structure(SIMPLE)
    # warmup(1) + 2x(20m + 5m) + cooldown(1) = 1 + 4 + 1 = 6
    assert len(ivs) == 6
    # Eerste = warmup ramp
    assert ivs[0].duration_min == 10
    assert ivs[0].is_ramp
    assert ivs[0].start_pct == 50
    assert ivs[0].end_pct == 80
    # Laatste = cooldown ramp
    assert ivs[-1].is_ramp
    assert ivs[-1].start_pct == 75
    assert ivs[-1].end_pct == 50


def test_parse_repetitions_expanded():
    ivs = parse_workout_structure(SIMPLE)
    # Middelste 4 steps: 20-5-20-5
    middel = ivs[1:5]
    durations = [iv.duration_min for iv in middel]
    assert durations == [20, 5, 20, 5]
    # Intensiteiten: 97-55-97-55
    ints = [iv.intensity_pct for iv in middel]
    assert ints == [97, 55, 97, 55]


def test_empty_description():
    assert parse_workout_structure("") == []
    assert parse_workout_structure("   \n\n") == []


def test_no_steps_returns_empty():
    junk = "Dit is een workout zonder structuur."
    ivs = parse_workout_structure(junk)
    assert ivs == []


def test_render_chart_smoke():
    """Render met geldige structuur → figuur met traces."""
    fig = render_workout_chart({"beschrijving": SIMPLE})
    assert fig is not None
    # Meerdere traces (1 per interval, zone-gekleurd)
    assert len(fig.data) >= 6


def test_render_empty_returns_fallback():
    """Lege workout-beschrijving → fallback-figuur, geen crash."""
    fig = render_workout_chart({"beschrijving": ""})
    assert fig is not None
    # Fallback heeft geen data-traces
    assert len(fig.data) == 0


def test_render_with_actual_overlay():
    fig = render_workout_chart(
        {"beschrijving": SIMPLE},
        actual_samples=[(0, 50), (10, 80), (20, 97), (40, 97)],
    )
    # +1 trace t.o.v. basis
    assert len(fig.data) >= 7


def test_total_duration_matches():
    ivs = parse_workout_structure(SIMPLE)
    total = sum(iv.duration_min for iv in ivs)
    # 10 + 20 + 5 + 20 + 5 + 10 = 70
    assert total == 70
