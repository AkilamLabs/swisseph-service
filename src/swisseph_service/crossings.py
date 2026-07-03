"""Generic longitude-crossing solver.

Finds the times in a window where a scalar angle — a body's longitude, the
difference of two bodies' longitudes, or their sum — crosses target values.
This is pure astronomy (root-finding on ephemeris curves); what the crossings
*mean* (tithi, nakshatra, ingress, ...) is the caller's business.

Method: sample the angle on a body-appropriate step, unwrap to a continuous
curve (steps are far smaller than 180° of angle change, so minimal-signed-delta
unwrapping is exact), bracket each target level between consecutive samples,
then refine by bisection to ``tolerance_jd``.
"""
from __future__ import annotations

import math
from typing import Callable

from . import core

# Fastest relevant angle is Moon-derived (|d(moon-sun)/dt| <= ~15.4 deg/day);
# 0.02 day steps move it <= ~0.31 deg — far below the smallest target gap in
# practice (6 deg karana grid), so no crossing can hide between samples.
STEP_MOON = 0.02
STEP_DEFAULT = 0.25

MAX_WINDOW_DAYS = 400.0
MAX_CROSSINGS = 2000


class CrossingError(ValueError):
    pass


def _make_angle_fn(kind: str, body: int, body2: int | None, frame: str) -> Callable[[float], float]:
    """Angle in degrees at jd. Caller must hold core.swe_lock with configure()
    already applied for the requested ayanamsa."""
    if kind == "body":
        def fn(jd: float) -> float:
            lon, _ = core.position_locked(jd, body, frame, speed=False)
            return lon % 360.0
    elif kind == "difference":
        def fn(jd: float) -> float:
            a, _ = core.position_locked(jd, body, frame, speed=False)
            b, _ = core.position_locked(jd, body2, frame, speed=False)
            return (a - b) % 360.0
    elif kind == "sum":
        def fn(jd: float) -> float:
            a, _ = core.position_locked(jd, body, frame, speed=False)
            b, _ = core.position_locked(jd, body2, frame, speed=False)
            return (a + b) % 360.0
    else:
        raise CrossingError(f"unknown angle kind: {kind}")
    return fn


def _unwrap_step(prev_unwrapped: float, prev_raw: float, raw: float) -> float:
    delta = ((raw - prev_raw + 180.0) % 360.0) - 180.0
    return prev_unwrapped + delta


def find_crossings(
    jd_start: float,
    jd_end: float,
    kind: str,
    body: int,
    body2: int | None,
    frame: str,
    grid: float | None,
    targets: list[float] | None,
    direction: str = "any",
    tolerance_jd: float = 1e-9,
) -> list[dict]:
    if jd_end <= jd_start:
        raise CrossingError("jd_end must be after jd_start")
    if jd_end - jd_start > MAX_WINDOW_DAYS:
        raise CrossingError(f"window exceeds {MAX_WINDOW_DAYS} days")
    if (grid is None) == (targets is None):
        raise CrossingError("provide exactly one of grid / targets")
    if grid is not None and not 0.0 < grid <= 360.0:
        raise CrossingError("grid must be in (0, 360]")

    moon_involved = core.MOON in (body, body2)
    step = STEP_MOON if moon_involved else STEP_DEFAULT

    angle_fn = _make_angle_fn(kind, body, body2, frame)

    # Sample and unwrap.
    n_steps = max(2, math.ceil((jd_end - jd_start) / step) + 1)
    jds = [jd_start + (jd_end - jd_start) * i / (n_steps - 1) for i in range(n_steps)]
    raws = [angle_fn(jd) for jd in jds]
    unwrapped = [raws[0]]
    for i in range(1, n_steps):
        unwrapped.append(_unwrap_step(unwrapped[-1], raws[i - 1], raws[i]))

    # Levels crossed in (u1, u2] (increasing) or [u2, u1) (decreasing).
    def levels_between(u1: float, u2: float) -> list[float]:
        lo, hi = (u1, u2) if u2 >= u1 else (u2, u1)
        out = []
        if grid is not None:
            k = math.floor(lo / grid)
            level = k * grid
            while level <= hi:
                if (lo < level <= hi) if u2 >= u1 else (lo <= level < hi):
                    out.append(level)
                k += 1
                level = k * grid
        else:
            for t in targets:
                n = math.floor((lo - t) / 360.0)
                level = t + n * 360.0
                while level <= hi:
                    if (lo < level <= hi) if u2 >= u1 else (lo <= level < hi):
                        out.append(level)
                    n += 1
                    level = t + n * 360.0
        return out

    crossings: list[dict] = []
    for i in range(1, n_steps):
        jd1, jd2 = jds[i - 1], jds[i]
        u1, u2 = unwrapped[i - 1], unwrapped[i]
        if u1 == u2:
            continue
        sign = 1 if u2 > u1 else -1
        if direction == "increasing" and sign < 0:
            continue
        if direction == "decreasing" and sign > 0:
            continue
        for level in levels_between(u1, u2):
            # Bisect u(jd) = level on [jd1, jd2]; re-unwrap each midpoint
            # relative to the left edge (bracket spans < ~1 deg of angle).
            lo_jd, hi_jd = jd1, jd2
            lo_u, lo_raw = u1, raws[i - 1]
            while hi_jd - lo_jd > tolerance_jd:
                mid = (lo_jd + hi_jd) / 2.0
                mid_raw = angle_fn(mid)
                mid_u = _unwrap_step(lo_u, lo_raw, mid_raw)
                if (mid_u < level) == (sign > 0):
                    lo_jd, lo_u, lo_raw = mid, mid_u, mid_raw
                else:
                    hi_jd = mid
            crossings.append({
                "jd": (lo_jd + hi_jd) / 2.0,
                "target": level % 360.0,
                "direction": sign,
            })
            if len(crossings) > MAX_CROSSINGS:
                raise CrossingError(f"more than {MAX_CROSSINGS} crossings in window")

    crossings.sort(key=lambda c: c["jd"])
    return crossings
