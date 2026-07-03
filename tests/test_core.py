"""Pinned-convention guards, adapted from the consuming engine's original
in-process ephemeris tests. These numbers are the contract: they must never
change without golden re-validation on the consumer side."""

import pytest

from swisseph_service import core

# Chennai golden chart: 1984-09-02 10:04 IST = 04:34 UT
CHENNAI = (13.0827, 80.2707)
JD_1984 = 2445945.6902777776


def test_julday_revjul_round_trip():
    jd = core.julday(2024, 1, 15, 12.0)
    year, month, day, hour = core.revjul(jd)
    assert (year, month, day) == (2024, 1, 15)
    assert hour == pytest.approx(12.0, abs=1e-6)


def test_birth_jd_matches_known_value():
    jd = core.julday(1984, 9, 2, 10 + 4 / 60 - 5.5)  # IST -> UT
    assert jd == pytest.approx(JD_1984, abs=1e-6)


def test_lahiri_ayanamsa_pinned():
    """Lahiri (Chitrapaksha) at J2000 is ~23.857°; Fagan-Bradley (~24.740°)
    is excluded. The most critical pinned convention."""
    jd = core.julday(2000, 1, 1, 12.0)
    with core.swe_lock:
        core.configure("lahiri")
        value = core.ayanamsa_locked(jd)
    assert 23.85 < value < 23.86


def test_topocentric_moon_still_disabled():
    """Guard: geocentric Moon matches Drik Panchang to 0.000136°; topocentric
    would flip nakshatra padas (see the validation block in core.py)."""
    assert core.TOPOCENTRIC_MOON_ENABLED is False


def test_geocentric_moon_matches_drik_reference():
    """The validation anchor itself: sidereal Moon at the golden birth time.
    Drik reference 223.176900; geocentric Lahiri computes 223.177036."""
    with core.swe_lock:
        core.configure("lahiri")
        lon, _ = core.position_locked(JD_1984, core.MOON, "sidereal", speed=False)
    assert lon == pytest.approx(223.177036, abs=1e-4)


def test_placidus_pinned_cusp1_and_polar_error():
    with core.swe_lock:
        core.configure("kp")
        cusps = core.placidus_cusps_locked(JD_1984, *CHENNAI)
    assert len(cusps) == 12
    assert cusps[0] == pytest.approx(195.672600, abs=1e-4)

    with core.swe_lock:
        core.configure("kp")
        with pytest.raises(ValueError):
            core.placidus_cusps_locked(JD_1984, 78.0, 80.0)
