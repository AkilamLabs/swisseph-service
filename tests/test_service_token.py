"""Optional SERVICE_TOKEN shared secret: enforced on every route but health."""

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def guarded(monkeypatch):
    monkeypatch.setenv("SERVICE_TOKEN", "s3cret-token")
    import swisseph_service.main as main
    yield TestClient(importlib.reload(main).app)
    monkeypatch.delenv("SERVICE_TOKEN")
    importlib.reload(main)


BODY = {"jds": [2445945.69], "bodies": [0]}


def test_missing_token_is_401(guarded):
    assert guarded.post("/v1/positions", json=BODY).status_code == 401


def test_wrong_token_is_401(guarded):
    r = guarded.post("/v1/positions", json=BODY, headers={"x-service-token": "s3cret-tokeX"})
    assert r.status_code == 401


def test_non_ascii_token_is_401_not_500(guarded):
    r = guarded.post("/v1/positions", json=BODY, headers={"x-service-token": "s3cret-t\xf6ken".encode("latin-1")})
    assert r.status_code == 401


def test_right_token_passes(guarded):
    r = guarded.post("/v1/positions", json=BODY, headers={"x-service-token": "s3cret-token"})
    assert r.status_code == 200


def test_health_needs_no_token(guarded):
    assert guarded.get("/v1/health").status_code == 200
