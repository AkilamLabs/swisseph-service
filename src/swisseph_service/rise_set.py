"""Rise/set events with parameterizable flags, plus the Sun's true altitude
at the event instant (a heliacal-visibility primitive).

Flag combinations reproduce the two conventions used by the consuming engine:
  - refraction + disc center  (sunrise-anchored panchangam convention)
  - no refraction + disc center (heliacal / combustion convention)
"""
from __future__ import annotations

import swisseph as swe

from . import core


def rise_set_event(
    jd_start: float,
    body: int,
    event: str,
    lat: float,
    lon: float,
    disc_center: bool = True,
    refraction: bool = True,
    sun_altitude_at_event: bool = False,
) -> dict:
    """One rise/set search. Caller must hold core.swe_lock (configure applied).

    Returns {"jd": float, "sun_true_altitude": float?} or {"error": str}.
    """
    flags = swe.CALC_RISE if event == "rise" else swe.CALC_SET
    if disc_center:
        flags |= swe.BIT_DISC_CENTER
    if not refraction:
        flags |= swe.BIT_NO_REFRACTION

    geopos = (lon, lat, 0.0)
    try:
        res, tret = swe.rise_trans(jd_start, body, flags, geopos)
    except Exception:
        return {"error": "circumpolar"}
    if res == -2:  # no rise/set at this latitude/date
        return {"error": "circumpolar"}

    t_event = tret[0]
    out: dict = {"jd": t_event}
    if sun_altitude_at_event:
        sun_eq, _ = swe.calc_ut(t_event, swe.SUN, swe.FLG_SWIEPH | swe.FLG_EQUATORIAL)
        _, alt_true = swe.azalt(t_event, swe.EQU2HOR, geopos, 0.0, 0.0,
                                (sun_eq[0], sun_eq[1], 1.0))[:2]
        out["sun_true_altitude"] = alt_true
    return out
