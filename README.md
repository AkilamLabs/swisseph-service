# swisseph-service

A thin, batch-first HTTP microservice wrapping the
[Swiss Ephemeris](https://www.astro.com/swisseph/) via
[pyswisseph](https://github.com/astrorigin/pyswisseph).

It exposes **raw astronomy only** — planetary longitudes, house cusps,
rise/set events, ayanamsa values, and generic longitude-crossing
root-finding — over a small JSON API designed to be co-located with a
consuming application (localhost or an internal Docker network).

## Why this exists (licensing)

Swiss Ephemeris and pyswisseph are licensed **AGPL-3.0** (Astrodienst also
sells a separate professional license). AGPL copyleft extends to any program
that links them in-process. Running the ephemeris behind a network API keeps
that boundary clean: **this service is AGPL-3.0 and fully open source**
(satisfying AGPL §13 — every user interacting with it over a network has
access to this source), while applications consuming its numeric output over
HTTP interact with it at arm's length.

If you modify and operate this service for network users, the AGPL requires
you to offer them your modified source.

## API

All endpoints under `/v1`. Bodies are Swiss Ephemeris integer ids
(SUN=0, MOON=1, MERCURY=2, VENUS=3, MARS=4, JUPITER=5, SATURN=6,
MEAN_NODE=10, TRUE_NODE=11). Ayanamsa: `lahiri` (default) | `raman` | `kp`.

| Endpoint | Purpose |
|---|---|
| `GET /v1/health` | status, swisseph version, ephe-path check |
| `POST /v1/positions` | batch longitudes/speeds, `jds × bodies` cross product, sidereal or tropical |
| `POST /v1/houses` | batch ascendant / Placidus cusps (structured `polar_undefined` error) |
| `POST /v1/rise-set` | batch rise/set, flag-parameterized (disc center, refraction), optional Sun true altitude at event |
| `POST /v1/crossings` | find times where a body longitude / difference / sum crosses target angles (grid or list), bisected to `tolerance_jd` |
| `POST /v1/ayanamsa` | batch ayanamsa values |
| `POST /v1/time/julday`, `POST /v1/time/revjul` | calendar ↔ Julian day |

Interactive docs at `/docs` when running.

### Pinned conventions

Sidereal positions use `FLG_SWIEPH | FLG_SIDEREAL` with geocentric
coordinates (topocentric Moon correction is deliberately disabled — see the
validation note in `src/swisseph_service/core.py`). Default rise/set is disc
center **with** refraction; pass `"refraction": false` for true-altitude
events (heliacal work).

## Running

```bash
# local
python -m venv .venv && .venv/bin/pip install -e '.[dev]'
bash scripts/fetch_ephe.sh          # downloads semo_18.se1 + sepl_18.se1
SE_EPHE_PATH=./ephe .venv/bin/uvicorn swisseph_service.main:app --port 8001

# docker (ephe data baked in)
docker build -t swisseph-service .
docker run -p 8001:8001 swisseph-service
```

Environment: `SE_EPHE_PATH` (default `/app/ephe` in Docker), `PORT`
(default 8001), optional `SERVICE_TOKEN` (require `X-Service-Token` header
on all endpoints except health).

## Tests

```bash
bash scripts/fetch_ephe.sh
SE_EPHE_PATH=./ephe .venv/bin/pytest
```

## License

[AGPL-3.0-or-later](LICENSE). The bundled/downloaded Swiss Ephemeris data
files (`*.se1`) are redistributed under the same license from
[Astrodienst's mirror](https://github.com/aloistr/swisseph).
