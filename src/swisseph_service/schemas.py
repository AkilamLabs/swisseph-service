"""Request/response models for the /v1 API.

Bodies are Swiss Ephemeris integer ids on the wire (SUN=0, MOON=1, MERCURY=2,
VENUS=3, MARS=4, JUPITER=5, SATURN=6, MEAN_NODE=10, TRUE_NODE=11) — no mapping
tables to drift. Ayanamsa is a string enum; this service owns the SIDM mapping.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Ayanamsa = Literal["lahiri", "raman", "kp"]
Frame = Literal["sidereal", "tropical"]

MAX_POSITION_POINTS = 50_000
MAX_BATCH_ITEMS = 5_000


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    swisseph_version: str
    ephe_path_ok: bool


class PositionsRequest(BaseModel):
    jds: list[float] = Field(min_length=1)
    bodies: list[int] = Field(min_length=1)
    frame: Frame = "sidereal"
    ayanamsa: Ayanamsa = "lahiri"
    speed: bool = False


class PositionValue(BaseModel):
    lon: float
    speed: float = 0.0


class PositionsResponse(BaseModel):
    # results[i][j] corresponds to jds[i] x bodies[j]
    results: list[list[PositionValue]]


class HouseItem(BaseModel):
    jd: float
    lat: float
    lon: float


class HousesRequest(BaseModel):
    items: list[HouseItem] = Field(min_length=1, max_length=MAX_BATCH_ITEMS)
    system: Literal["placidus", "asc_only"] = "asc_only"
    ayanamsa: Ayanamsa = "lahiri"


class HouseResult(BaseModel):
    ascendant: float | None = None
    cusps: list[float] | None = None
    error: str | None = None


class HousesResponse(BaseModel):
    results: list[HouseResult]


class RiseSetEvent(BaseModel):
    jd_start: float
    body: int
    event: Literal["rise", "set"]
    lat: float
    lon: float
    disc_center: bool = True
    refraction: bool = True
    sun_altitude_at_event: bool = False


class RiseSetRequest(BaseModel):
    events: list[RiseSetEvent] = Field(min_length=1, max_length=MAX_BATCH_ITEMS)


class RiseSetResult(BaseModel):
    jd: float | None = None
    sun_true_altitude: float | None = None
    error: str | None = None


class RiseSetResponse(BaseModel):
    results: list[RiseSetResult]


class AngleSpec(BaseModel):
    kind: Literal["body", "difference", "sum"]
    body: int
    body2: int | None = None
    frame: Frame = "sidereal"
    ayanamsa: Ayanamsa = "lahiri"


class TargetSpec(BaseModel):
    grid: float | None = None
    list_: list[float] | None = Field(default=None, alias="list")

    model_config = {"populate_by_name": True}


class CrossingsRequest(BaseModel):
    jd_start: float
    jd_end: float
    angle: AngleSpec
    targets: TargetSpec
    direction: Literal["increasing", "decreasing", "any"] = "any"
    tolerance_jd: float = Field(default=1e-9, ge=1e-12, le=1e-3)


class Crossing(BaseModel):
    jd: float
    target: float
    direction: int


class CrossingsResponse(BaseModel):
    crossings: list[Crossing]


class AyanamsaRequest(BaseModel):
    jds: list[float] = Field(min_length=1, max_length=MAX_POSITION_POINTS)
    ayanamsa: Ayanamsa = "lahiri"


class AyanamsaResponse(BaseModel):
    values: list[float]


class JuldayRequest(BaseModel):
    dates: list[list[float]] = Field(min_length=1, max_length=MAX_POSITION_POINTS,
                                     description="[year, month, day, hour] tuples")


class JuldayResponse(BaseModel):
    jds: list[float]


class RevjulRequest(BaseModel):
    jds: list[float] = Field(min_length=1, max_length=MAX_POSITION_POINTS)


class RevjulResponse(BaseModel):
    dates: list[list[float]]  # [year, month, day, hour]
