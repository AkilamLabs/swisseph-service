"""swisseph-service — a thin, batch-first HTTP wrapper around Swiss Ephemeris.

Licensed AGPL-3.0 (pyswisseph / Swiss Ephemeris are AGPL-3.0; see LICENSE and
README). Exposes raw astronomy only: positions, houses, rise/set, ayanamsa,
longitude-crossing root-finding, and calendar<->julian-day conversion.

Each batch endpoint executes its whole batch under one swe_lock acquisition
with one configure() call — swisseph keeps global state (ephe path, sid mode),
so this is both the correctness requirement and a performance win.
"""
from __future__ import annotations

import hmac
import logging
import os
import time

from fastapi import FastAPI, HTTPException
from fastapi.responses import ORJSONResponse

from . import core, crossings, rise_set, schemas

logger = logging.getLogger("swisseph_service")

app = FastAPI(
    title="swisseph-service",
    description="Thin AGPL-3.0 HTTP wrapper around Swiss Ephemeris (batch-first).",
    version="0.2.0",
    default_response_class=ORJSONResponse,
)


@app.middleware("http")
async def _timing_log(request, call_next):
    t0 = time.perf_counter()
    response = await call_next(request)
    logger.info("%s %s -> %s in %.1f ms", request.method, request.url.path,
                response.status_code, (time.perf_counter() - t0) * 1000)
    return response

_service_token = os.environ.get("SERVICE_TOKEN")  # optional shared secret

if _service_token:
    from fastapi import Request
    from starlette.middleware.base import BaseHTTPMiddleware

    class _TokenMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            # Constant-time, on bytes: compare_digest rejects non-ASCII str.
            sent = (request.headers.get("x-service-token") or "").encode("utf-8", "surrogateescape")
            if request.url.path != "/v1/health" and \
                    not hmac.compare_digest(sent, _service_token.encode("utf-8")):
                from starlette.responses import JSONResponse
                return JSONResponse({"detail": "invalid service token"}, status_code=401)
            return await call_next(request)

    app.add_middleware(_TokenMiddleware)


@app.get("/v1/health", response_model=schemas.HealthResponse)
def health() -> schemas.HealthResponse:
    ok = core.ephe_path_ok()
    return schemas.HealthResponse(
        status="ok" if ok else "degraded",
        swisseph_version=core.version(),
        ephe_path_ok=ok,
    )


@app.post("/v1/positions", response_model=schemas.PositionsResponse)
def positions(req: schemas.PositionsRequest) -> schemas.PositionsResponse:
    if len(req.jds) * len(req.bodies) > schemas.MAX_POSITION_POINTS:
        raise HTTPException(413, f"batch exceeds {schemas.MAX_POSITION_POINTS} points")
    results = []
    with core.swe_lock:
        core.configure(req.ayanamsa)
        for jd in req.jds:
            row = []
            for body in req.bodies:
                try:
                    lon, speed = core.position_locked(jd, body, req.frame, req.speed)
                except Exception as e:
                    raise HTTPException(422, f"position failed for body={body} jd={jd}: {e}")
                row.append(schemas.PositionValue(lon=lon, speed=speed))
            results.append(row)
    return schemas.PositionsResponse(results=results)


@app.post("/v1/houses", response_model=schemas.HousesResponse)
def houses(req: schemas.HousesRequest) -> schemas.HousesResponse:
    results = []
    with core.swe_lock:
        core.configure(req.ayanamsa)
        for item in req.items:
            try:
                if req.system == "asc_only":
                    asc = core.ascendant_locked(item.jd, item.lat, item.lon)
                    results.append(schemas.HouseResult(ascendant=asc))
                else:
                    cusps = core.placidus_cusps_locked(item.jd, item.lat, item.lon)
                    asc = core.ascendant_locked(item.jd, item.lat, item.lon)
                    results.append(schemas.HouseResult(ascendant=asc, cusps=cusps))
            except ValueError:
                results.append(schemas.HouseResult(error="polar_undefined"))
    return schemas.HousesResponse(results=results)


@app.post("/v1/rise-set", response_model=schemas.RiseSetResponse)
def rise_set_batch(req: schemas.RiseSetRequest) -> schemas.RiseSetResponse:
    results = []
    with core.swe_lock:
        core.configure()
        for ev in req.events:
            r = rise_set.rise_set_event(
                jd_start=ev.jd_start, body=ev.body, event=ev.event,
                lat=ev.lat, lon=ev.lon,
                disc_center=ev.disc_center, refraction=ev.refraction,
                sun_altitude_at_event=ev.sun_altitude_at_event,
            )
            results.append(schemas.RiseSetResult(**r))
    return schemas.RiseSetResponse(results=results)


def _solve_crossings_locked(req: schemas.CrossingsRequest,
                            eval_cache: dict | None = None) -> schemas.CrossingsResponse:
    """Solve one crossings query. Caller must hold core.swe_lock; this applies
    configure() for the query's ayanamsa itself (batch queries may differ)."""
    if req.angle.kind in ("difference", "sum") and req.angle.body2 is None:
        raise HTTPException(422, "body2 required for difference/sum angles")
    core.configure(req.angle.ayanamsa)
    try:
        found = crossings.find_crossings(
            jd_start=req.jd_start, jd_end=req.jd_end,
            kind=req.angle.kind, body=req.angle.body, body2=req.angle.body2,
            frame=req.angle.frame,
            grid=req.targets.grid, targets=req.targets.list_,
            direction=req.direction, tolerance_jd=req.tolerance_jd,
            ayanamsa=req.angle.ayanamsa, eval_cache=eval_cache,
        )
    except crossings.CrossingError as e:
        raise HTTPException(422, str(e))
    return schemas.CrossingsResponse(crossings=[schemas.Crossing(**c) for c in found])


@app.post("/v1/crossings", response_model=schemas.CrossingsResponse)
def crossings_solve(req: schemas.CrossingsRequest) -> schemas.CrossingsResponse:
    with core.swe_lock:
        return _solve_crossings_locked(req)


@app.post("/v1/crossings-batch", response_model=schemas.CrossingsBatchResponse)
def crossings_solve_batch(req: schemas.CrossingsBatchRequest) -> schemas.CrossingsBatchResponse:
    """Solve many crossing queries in one request under one lock acquisition.

    Queries share a position-evaluation cache, so queries over the same window
    and bodies (e.g. tithi and karana, both Moon−Sun) sample the ephemeris
    once instead of once per query."""
    eval_cache: dict = {}
    with core.swe_lock:
        results = [_solve_crossings_locked(q, eval_cache) for q in req.queries]
    return schemas.CrossingsBatchResponse(results=results)


@app.post("/v1/ayanamsa", response_model=schemas.AyanamsaResponse)
def ayanamsa(req: schemas.AyanamsaRequest) -> schemas.AyanamsaResponse:
    with core.swe_lock:
        core.configure(req.ayanamsa)
        values = [core.ayanamsa_locked(jd) for jd in req.jds]
    return schemas.AyanamsaResponse(values=values)


@app.post("/v1/time/julday", response_model=schemas.JuldayResponse)
def julday(req: schemas.JuldayRequest) -> schemas.JuldayResponse:
    jds = []
    for d in req.dates:
        if len(d) != 4:
            raise HTTPException(422, "each date must be [year, month, day, hour]")
        jds.append(core.julday(int(d[0]), int(d[1]), int(d[2]), float(d[3])))
    return schemas.JuldayResponse(jds=jds)


@app.post("/v1/time/revjul", response_model=schemas.RevjulResponse)
def revjul(req: schemas.RevjulRequest) -> schemas.RevjulResponse:
    return schemas.RevjulResponse(
        dates=[list(core.revjul(jd)) for jd in req.jds]
    )
