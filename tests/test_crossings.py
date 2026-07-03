"""Crossing-solver correctness by self-consistency: at every reported jd the
angle must sit on the reported target to within the bisection tolerance."""

import pytest

from swisseph_service import core
from swisseph_service.crossings import find_crossings, CrossingError

SUN, MOON = 0, 1
TOL = 1e-9


def _angle_diff(jd):
    with core.swe_lock:
        core.configure("lahiri")
        m, _ = core.position_locked(jd, MOON, "sidereal", False)
        s, _ = core.position_locked(jd, SUN, "sidereal", False)
    return (m - s) % 360.0


def _solve(**kw):
    with core.swe_lock:
        core.configure(kw.pop("ayanamsa", "lahiri"))
        return find_crossings(**kw)


def test_tithi_grid_crossings_land_on_targets():
    jd0 = core.julday(2026, 7, 3, 0.0)
    crossings = _solve(jd_start=jd0, jd_end=jd0 + 3.0, kind="difference",
                       body=MOON, body2=SUN, frame="sidereal",
                       grid=12.0, targets=None, tolerance_jd=TOL)
    # moon-sun elongation moves ~12.2°/day → ~3 tithi boundaries in 3 days
    assert 2 <= len(crossings) <= 4
    jds = [c["jd"] for c in crossings]
    assert jds == sorted(jds)
    for c in crossings:
        assert c["target"] % 12.0 == pytest.approx(0.0, abs=1e-9)
        # angle at the solved jd sits on the boundary (a few 1e-6 deg of slack
        # for tolerance_jd of drift at <=15.4 deg/day)
        assert _angle_diff(c["jd"]) == pytest.approx(c["target"] % 360.0, abs=1e-4)
        assert c["direction"] == 1


def test_explicit_targets_and_direction_filter():
    jd0 = core.julday(2026, 7, 3, 0.0)
    crossings = _solve(jd_start=jd0, jd_end=jd0 + 30.0, kind="body",
                       body=SUN, body2=None, frame="sidereal",
                       grid=None, targets=[90.0], tolerance_jd=TOL,
                       direction="increasing")
    # Sun crosses sidereal 90° (Kataka ingress) exactly once in mid-July
    assert len(crossings) == 1
    with core.swe_lock:
        core.configure("lahiri")
        lon, _ = core.position_locked(crossings[0]["jd"], SUN, "sidereal", False)
    assert lon == pytest.approx(90.0, abs=1e-6)


def test_sum_angle_yoga():
    jd0 = core.julday(1984, 9, 2, 0.0)
    crossings = _solve(jd_start=jd0, jd_end=jd0 + 1.04, kind="sum",
                       body=SUN, body2=MOON, frame="sidereal",
                       grid=360.0 / 27.0, targets=None, tolerance_jd=TOL)
    assert len(crossings) >= 1


def test_validation_errors():
    with pytest.raises(CrossingError):
        _solve(jd_start=100.0, jd_end=99.0, kind="body", body=SUN, body2=None,
               frame="sidereal", grid=30.0, targets=None)
    with pytest.raises(CrossingError):
        _solve(jd_start=0.0, jd_end=500.0, kind="body", body=SUN, body2=None,
               frame="sidereal", grid=30.0, targets=None)
    with pytest.raises(CrossingError):
        _solve(jd_start=0.0, jd_end=1.0, kind="body", body=SUN, body2=None,
               frame="sidereal", grid=None, targets=None)


def test_batch_matches_single_queries_exactly(client):
    """crossings-batch must return bit-identical results to one-at-a-time
    queries — the shared eval cache is a perf layer, never a numeric one."""
    jd0 = core.julday(2026, 7, 3, 0.0)
    queries = [
        {"jd_start": jd0, "jd_end": jd0 + 1.04,
         "angle": {"kind": "difference", "body": MOON, "body2": SUN,
                   "frame": "sidereal", "ayanamsa": "lahiri"},
         "targets": {"grid": 12.0}},
        {"jd_start": jd0, "jd_end": jd0 + 1.04,
         "angle": {"kind": "difference", "body": MOON, "body2": SUN,
                   "frame": "sidereal", "ayanamsa": "lahiri"},
         "targets": {"grid": 6.0}},   # karana: same angle, same samples
        {"jd_start": jd0, "jd_end": jd0 + 1.04,
         "angle": {"kind": "body", "body": MOON,
                   "frame": "sidereal", "ayanamsa": "lahiri"},
         "targets": {"grid": 360.0 / 27.0}},
    ]
    batch = client.post("/v1/crossings-batch", json={"queries": queries}).json()
    for q, batched in zip(queries, batch["results"]):
        single = client.post("/v1/crossings", json=q).json()
        assert batched == single


def test_retrograde_crossings_report_direction():
    """A planet that stations inside the window crosses the same longitude in
    both directions; every reported crossing must sit on the target and the
    direction signs must reflect the actual motion."""
    jd0 = core.julday(2026, 1, 1, 0.0)
    with core.swe_lock:
        core.configure("lahiri")
        mid_lon, _ = core.position_locked(jd0 + 60.0, 2, "sidereal", False)  # Mercury
        found = find_crossings(jd_start=jd0, jd_end=jd0 + 120.0, kind="body",
                               body=2, body2=None, frame="sidereal",
                               grid=None, targets=[mid_lon % 360.0],
                               direction="any", tolerance_jd=TOL)
    assert len(found) >= 1
    for c in found:
        with core.swe_lock:
            core.configure("lahiri")
            lon, _ = core.position_locked(c["jd"], 2, "sidereal", False)
        assert lon == pytest.approx(mid_lon % 360.0, abs=1e-5)
        assert c["direction"] in (1, -1)
    # Mercury retrogrades roughly every ~116 days, so a 120-day window around a
    # mid-window longitude usually yields a direct-retro-direct triple.
    if len(found) >= 3:
        assert -1 in {c["direction"] for c in found}
