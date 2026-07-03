import os

import pytest
from fastapi.testclient import TestClient

from swisseph_service.main import app


def pytest_collection_modifyitems(config, items):
    if not os.environ.get("SE_EPHE_PATH"):
        skip = pytest.mark.skip(reason="SE_EPHE_PATH not set (run scripts/fetch_ephe.sh)")
        for item in items:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)
