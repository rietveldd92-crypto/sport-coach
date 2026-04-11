"""fitness_trend — Bereken dagelijkse CTL/ATL/TSB curve uit activiteiten.

Gebruikt voor de CTL-curve grafiek (ROADMAP Fase 3.1). Berekent ook
een projectie naar racedag op basis van het huidige opbouwtempo.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta


def calculate_daily_trend(
    activities: list[dict],
    seed_ctl: float = 20.0,
    seed_atl: float = 20.0,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[dict]:
    """Bereken dagelijkse CTL/ATL/TSB uit activiteiten.

    Returns lijst van {date, ctl, atl, tsb, tss} dicts, gesorteerd op datum.
    """
    tss_by_day: dict[date, float] = defaultdict(float)
    for act in activities:
        tss = act.get("icu_training_load") or act.get("training_load") or 0
        if not tss:
            continue
        d_str = (act.get("start_date_local") or "")[:10]
        if not d_str:
            continue
        try:
            tss_by_day[date.fromisoformat(d_str)] += tss
        except ValueError:
            continue

    if not tss_by_day and not start_date:
        return []

    if start_date is None:
        start_date = min(tss_by_day.keys())
    if end_date is None:
        end_date = date.today()

    ctl, atl = seed_ctl, seed_atl
    result = []
    current = start_date
    while current <= end_date:
        tss = tss_by_day.get(current, 0)
        ctl = ctl + (tss - ctl) / 42
        atl = atl + (tss - atl) / 7
        tsb = ctl - atl
        result.append({
            "date": current.isoformat(),
            "ctl": round(ctl, 1),
            "atl": round(atl, 1),
            "tsb": round(tsb, 1),
            "tss": round(tss, 0),
        })
        current += timedelta(days=1)

    return result


def project_ctl(
    current_ctl: float,
    weekly_tss: float,
    weeks: int,
) -> list[dict]:
    """Projecteer CTL vooruit op basis van een constant wekelijks TSS.

    Returns lijst van {date, ctl} dicts per week.
    """
    daily_tss = weekly_tss / 7
    ctl = current_ctl
    result = []
    current = date.today()
    for w in range(weeks):
        for _ in range(7):
            ctl = ctl + (daily_tss - ctl) / 42
            current += timedelta(days=1)
        result.append({
            "date": current.isoformat(),
            "ctl": round(ctl, 1),
        })
    return result
