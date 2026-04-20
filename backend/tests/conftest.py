import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.main import create_app


@pytest.fixture
def api_auth_headers():
    return {"X-API-Key": "mock-key-001"}


@pytest.fixture
def api_client_factory(tmp_path, monkeypatch):
    def _factory(db_name: str = "test.db"):
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / db_name}")
        monkeypatch.setenv("MOCK_API_KEY", "mock-key-001")
        monkeypatch.setenv("SIMULATOR_ENABLED", "false")
        app = create_app()
        return TestClient(app)

    return _factory
