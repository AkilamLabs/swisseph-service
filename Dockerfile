# swisseph-service — AGPL-3.0 (see LICENSE). Ephemeris data files are baked in;
# this image redistributes Swiss Ephemeris under the same license.
FROM python:3.12-slim AS build

# build-essential is required to compile the pyswisseph C extension: recent
# pyswisseph releases (e.g. 2.10.3.2) publish only an sdist for cp312, so pip
# builds the wheel from source. Lives in the build stage only — the multi-stage
# final image copies just site-packages, so the runtime image stays slim.
RUN apt-get update && apt-get install -y --no-install-recommends curl build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY ephe /app/ephe
COPY scripts/fetch_ephe.sh scripts/
RUN bash scripts/fetch_ephe.sh /app/ephe

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir .

FROM python:3.12-slim

RUN useradd --create-home appuser
WORKDIR /app
COPY --from=build /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=build /usr/local/bin/uvicorn /usr/local/bin/uvicorn
COPY --from=build /app/ephe /app/ephe
COPY LICENSE README.md ./

ENV SE_EPHE_PATH=/app/ephe
ENV PORT=8001
USER appuser
EXPOSE 8001

HEALTHCHECK --interval=15s --timeout=3s --start-period=5s \
    CMD python -c "import urllib.request,os,sys; \
        r=urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/v1/health', timeout=2); \
        sys.exit(0 if r.status==200 else 1)"

# Two workers: swisseph state is per-process (configure() runs per batch under
# each process lock), so workers are safe and remove cross-request serialization.
CMD ["sh", "-c", "uvicorn swisseph_service.main:app --host 0.0.0.0 --port ${PORT} --workers ${WORKERS:-2}"]
