"""Core Swiss Ephemeris wrapper — the single owner of the pinned conventions.

Ported from the original in-process engine's ephemeris.py. This module owns
the ephe path, the Lahiri (Chitrapaksha) ayanamsa, the sidereal flags, and the
rise/set flags, configuring that state before every operation so it can never
go stale or be forgotten. Everything else in this service calls into here;
no other module imports swisseph for computation.

All functions hold ``swe_lock`` themselves; batch helpers in main.py use the
``*_locked`` variants inside a single lock acquisition instead.
"""
from __future__ import annotations

import math
import os
import threading

import swisseph as swe

# --- Pinned conventions (do not change without golden re-validation in the
# --- consuming engine; see that repo's spec.md) ---

# Sidereal positions: Swiss Ephemeris files + sidereal zodiac.
SIDEREAL_FLAGS = swe.FLG_SWIEPH | swe.FLG_SIDEREAL

# Topocentric variant — only applied when TOPOCENTRIC_MOON_ENABLED is True.
TOPOCENTRIC_FLAGS = SIDEREAL_FLAGS | swe.FLG_TOPOCTR

# Topocentric Moon correction is intentionally DISABLED and should remain so.
#
# Validation (2026-06-06, tools/validate_topocentric.py, SE1 ephemeris data):
#   nandha_1984_09_02 (Chennai, 1984-09-02 10:04 IST):
#     Geocentric  Moon = 223.177036°  Δ from Drik = 0.000136°  pada = 3 ✓
#     Topocentric Moon = 224.022362°  Δ from Drik = 0.845462°  pada = 4 ✗
#     Drik reference   = 223.176900°                           pada = 3
#
# Conclusion: Drik Panchang uses geocentric Moon positions. Our geocentric
# result agrees to 0.000136° (sub-arcminute accuracy). Enabling topocentric
# would introduce 0.845° of error and flip the nakshatra pada — making every
# chart wrong relative to the trusted reference. Do not enable this flag.
TOPOCENTRIC_MOON_ENABLED = False

MOON = swe.MOON
SUN = swe.SUN

AYANAMSA_MODES = {
    "lahiri": swe.SIDM_LAHIRI,
    "raman": swe.SIDM_RAMAN,
    "kp": swe.SIDM_KRISHNAMURTI,
}

swe_lock = threading.Lock()


def configure(ayanamsa: str = "lahiri") -> None:
    """Apply the pinned global conventions. Cheap and idempotent; called before
    every operation (or once per locked batch) so the result never depends on
    call order. Caller must hold ``swe_lock``."""
    swe.set_ephe_path(os.environ.get("SE_EPHE_PATH", "./ephe"))
    sid_mode = AYANAMSA_MODES.get((ayanamsa or "lahiri").lower(), swe.SIDM_LAHIRI)
    swe.set_sid_mode(sid_mode)


def version() -> str:
    with swe_lock:
        return swe.version


def ephe_path_ok() -> bool:
    """True if a position can actually be computed from the configured path."""
    try:
        with swe_lock:
            configure()
            swe.calc_ut(2451545.0, swe.SUN, SIDEREAL_FLAGS)
        return True
    except Exception:
        return False


# --- Calendrical utilities (pure; no conventions, no ephe data) ---

def julday(year: int, month: int, day: int, hour: float) -> float:
    with swe_lock:
        return swe.julday(year, month, day, hour)


def revjul(jd: float) -> tuple[int, int, int, float]:
    with swe_lock:
        return swe.revjul(jd, swe.GREG_CAL)


# --- Locked primitives (caller holds swe_lock and has called configure) ---

def position_locked(jd: float, body: int, frame: str, speed: bool) -> tuple[float, float]:
    """(longitude_deg, speed_deg_per_day) in the requested frame.

    sidereal: ayanamsa-corrected (configure() sets the mode).
    tropical: plain geocentric ecliptic longitude — the ayanamsa offset cancels
    in Sun–planet separations, which is why heliacal checks use it.
    """
    if frame == "sidereal":
        flags = SIDEREAL_FLAGS
    else:
        flags = swe.FLG_SWIEPH
    if speed:
        flags |= swe.FLG_SPEED
    xx, _ = swe.calc_ut(jd, body, flags)
    return xx[0] % 360.0, (xx[3] if speed else 0.0)


def ayanamsa_locked(jd: float) -> float:
    return swe.get_ayanamsa_ut(jd)


def ascendant_locked(jd: float, lat: float, lon: float) -> float:
    _, ascmc = swe.houses_ex(jd, lat, lon, b"A", SIDEREAL_FLAGS)
    return ascmc[0]


def placidus_cusps_locked(jd: float, lat: float, lon: float) -> list[float]:
    """The 12 Placidus house cusps (sidereal longitudes, degrees), house 1..12.

    Placidus is undefined in the polar regions; Swiss Ephemeris raises
    swisseph.Error from inside houses_ex, and/or returns a non-finite cusp.
    Both paths are converted to ValueError here so the API layer can return a
    structured "polar_undefined" error rather than garbage or a 500.
    """
    try:
        cusps, _ascmc = swe.houses_ex(jd, lat, lon, b"P", SIDEREAL_FLAGS)
    except swe.Error as e:
        raise ValueError(
            f"Placidus cusps unavailable at lat={lat} (polar/undefined region)"
        ) from e

    # pyswisseph returns either 12 cusps (index 0 == house 1) or 13 (index 0 is
    # a dummy, houses 1..12 at index 1..12). Normalize to house 1..12.
    houses = list(cusps[1:13]) if len(cusps) == 13 else list(cusps[:12])
    if len(houses) != 12 or any(not math.isfinite(c) for c in houses):
        raise ValueError(
            f"Placidus cusps unavailable at lat={lat} (polar/undefined region)"
        )
    return [c % 360.0 for c in houses]
