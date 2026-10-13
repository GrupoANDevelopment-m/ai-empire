"""Test /health endpoint."""
import pytest
from fastapi.testclient import TestClient
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from web.server import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_returns_200(client):
    """Health check should return 200."""
    r = client.get("/health")
    assert r.status_code == 200


def test_health_returns_component_status(client):
    """Health check should include component status."""
    r = client.get("/health")
    data = r.json()
    assert "status" in data
    assert "components" in data
    assert "uptime" in data


def test_health_live_returns_200(client):
    """Liveness probe should return 200."""
    r = client.get("/health/live")
    assert r.status_code == 200


def test_health_ready_returns_200(client):
    """Readiness probe should return 200."""
    r = client.get("/health/ready")
    assert r.status_code == 200
