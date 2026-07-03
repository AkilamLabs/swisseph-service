"""HTTP round-trip tests: the JSON layer must not perturb a single bit."""

import pytest

from swisseph_service import core

CHENNAI = {"lat": 13.0827, "lon": 80.2707}
JD_1984 = 2445945.6902777776
SUN, MOON, JUPITER = 0, 1, 5


def test_health(client):
    r = client.get("/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["ephe_path_ok"] is True


def test_positions_batch_exact_roundtrip(client):
    jds = [JD_1984, JD_1984 + 100.0]
    bodies = [SUN, MOON]
    r = client.post("/v1/positions", json={
        "jds": jds, "bodies": bodies, "frame": "sidereal",
        "ayanamsa": "lahiri", "speed": True,
    })
    assert r.status_code == 200
    results = r.json()["results"]
    assert len(results) == 2 and len(results[0]) == 2

    # exact float equality vs a direct in-process call — JSON must be lossless
    with core.swe_lock:
        core.configure("lahiri")
        expected_lon, expected_speed = core.position_locked(JD_1984, MOON, "sidereal", True)
    assert results[0][1]["lon"] == expected_lon
    assert results[0][1]["speed"] == expected_speed


def test_positions_batch_cap(client):
    r = client.post("/v1/positions", json={
        "jds": [2451545.0 + i for i in range(10001)], "bodies": list(range(6)),
    })
    assert r.status_code == 413


def test_houses_placidus_and_polar(client):
    r = client.post("/v1/houses", json={
        "items": [
            {"jd": JD_1984, **CHENNAI},
            {"jd": JD_1984, "lat": 78.0, "lon": 80.0},
        ],
        "system": "placidus", "ayanamsa": "kp",
    })
    assert r.status_code == 200
    ok, polar = r.json()["results"]
    assert len(ok["cusps"]) == 12
    assert ok["cusps"][0] == pytest.approx(195.672600, abs=1e-4)
    assert polar["error"] == "polar_undefined"
    assert polar["cusps"] is None


def test_rise_set_with_sun_altitude(client):
    jd0 = core.julday(2026, 2, 1, 0.0)
    r = client.post("/v1/rise-set", json={"events": [
        {"jd_start": jd0, "body": SUN, "event": "rise", **CHENNAI},
        {"jd_start": jd0, "body": JUPITER, "event": "rise", **CHENNAI,
         "refraction": False, "sun_altitude_at_event": True},
    ]})
    assert r.status_code == 200
    sunrise, jup_rise = r.json()["results"]
    assert jd0 < sunrise["jd"] < jd0 + 1.0
    assert sunrise["sun_true_altitude"] is None
    assert jd0 < jup_rise["jd"] < jd0 + 1.5
    assert isinstance(jup_rise["sun_true_altitude"], float)


def test_ayanamsa_and_time_endpoints(client):
    r = client.post("/v1/ayanamsa", json={"jds": [2451545.0], "ayanamsa": "lahiri"})
    assert 23.85 < r.json()["values"][0] < 23.86

    r = client.post("/v1/time/julday", json={"dates": [[1984, 9, 2, 4.566666666666666]]})
    jd = r.json()["jds"][0]
    assert jd == pytest.approx(JD_1984, abs=1e-9)

    r = client.post("/v1/time/revjul", json={"jds": [jd]})
    y, m, d, h = r.json()["dates"][0]
    assert (y, m, d) == (1984, 9, 2)
