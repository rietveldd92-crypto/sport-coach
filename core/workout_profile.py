"""Compact workout-profile parser for generated workout descriptions."""
from __future__ import annotations

import re


_REPEAT_RE = re.compile(r"^(\d+)\s*x$", re.IGNORECASE)
_STEP_RE = re.compile(r"^-\s+(?P<dur>\d+(?:\.\d+)?(?:m|s|km))\s+(?P<body>.+)$", re.IGNORECASE)
_RAMP_RE = re.compile(r"\bramp\s+(?P<lo>\d+(?:\.\d+)?)\s*-\s*(?P<hi>\d+(?:\.\d+)?)\s*%", re.IGNORECASE)
_PCT_RE = re.compile(r"(?P<pct>\d+(?:\.\d+)?)\s*%")
_PACE_RE = re.compile(r"(?P<m>\d+):(?P<s>\d{2})/km", re.IGNORECASE)
_HEADER_RE = re.compile(r"^(warmup|main set|cooldown|cool down)$", re.IGNORECASE)


def parse_profile(
    description: str,
    threshold_pace_sec: int | None = None,
) -> list[dict]:
    """Parse a generated description into compact profile steps.

    Returns [{"sec": int, "pct": float}, ...] in execution order. The pct is
    relative to FTP for bike descriptions or threshold pace for runs.
    """
    if not description:
        return []
    lines = [line.strip() for line in str(description).splitlines()]
    steps: list[dict] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        repeat = _repeat_count(line)
        if repeat:
            block, next_i = _collect_repeat_block(lines, i + 1, threshold_pace_sec)
            if block:
                for _ in range(repeat):
                    steps.extend(block)
                i = next_i
                continue
        parsed = _parse_step(line, threshold_pace_sec)
        if parsed:
            steps.extend(parsed)
        i += 1
    if len(steps) < 2:
        return []
    return [
        {"sec": int(max(1, round(step["sec"]))), "pct": round(float(step["pct"]), 1)}
        for step in steps
    ]


def _collect_repeat_block(
    lines: list[str],
    start: int,
    threshold_pace_sec: int | None,
) -> tuple[list[dict], int]:
    block: list[dict] = []
    i = start
    while i < len(lines):
        line = lines[i].strip()
        if not line or _HEADER_RE.match(line) or _repeat_count(line):
            break
        parsed = _parse_step(line, threshold_pace_sec)
        if parsed:
            block.extend(parsed)
        i += 1
    return block, i


def _repeat_count(line: str) -> int | None:
    match = _REPEAT_RE.match(line.strip())
    if not match:
        return None
    return max(1, min(50, int(match.group(1))))


def _parse_step(line: str, threshold_pace_sec: int | None) -> list[dict]:
    match = _STEP_RE.match(line)
    if not match:
        return []
    duration = match.group("dur").lower()
    body = match.group("body")
    ramp = _RAMP_RE.search(body)
    if ramp:
        sec = _duration_seconds(duration, body, threshold_pace_sec)
        if sec is None:
            return []
        lo = float(ramp.group("lo"))
        hi = float(ramp.group("hi"))
        return [
            {"sec": sec / 4, "pct": lo + (hi - lo) * idx / 3}
            for idx in range(4)
        ]
    pct = _intensity_pct(body, threshold_pace_sec)
    sec = _duration_seconds(duration, body, threshold_pace_sec)
    if pct is None or sec is None:
        return []
    return [{"sec": sec, "pct": pct}]


def _duration_seconds(
    duration: str,
    body: str,
    threshold_pace_sec: int | None,
) -> float | None:
    if duration.endswith("km"):
        km = float(duration[:-2])
        pace_sec = _pace_seconds(body)
        if pace_sec is None:
            pct = _percent(body)
            if threshold_pace_sec and pct:
                pace_sec = threshold_pace_sec / (pct / 100)
        if pace_sec is None:
            return None
        return km * pace_sec
    if duration.endswith("m"):
        return float(duration[:-1]) * 60
    if duration.endswith("s"):
        return float(duration[:-1])
    return None


def _intensity_pct(body: str, threshold_pace_sec: int | None) -> float | None:
    pace_sec = _pace_seconds(body)
    if pace_sec is not None:
        if threshold_pace_sec:
            return max(0, min(130, threshold_pace_sec / pace_sec * 100))
        return 80
    pct = _percent(body)
    if pct is None:
        return None
    return max(0, min(130, pct))


def _pace_seconds(body: str) -> int | None:
    match = _PACE_RE.search(body)
    if not match:
        return None
    return int(match.group("m")) * 60 + int(match.group("s"))


def _percent(body: str) -> float | None:
    matches = list(_PCT_RE.finditer(body))
    if not matches:
        return None
    return float(matches[-1].group("pct"))
