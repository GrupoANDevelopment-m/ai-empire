"""Test /api/capabilities endpoint."""
import pytest
from fastapi.testclient import TestClient
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from web.server import app


@pytest.fixture
def client():
    return TestClient(app)


def test_capabilities_requires_auth(client):
    """Should require authentication."""
    r = client.get("/api/capabilities")
    assert r.status_code in (401, 403)


def test_capabilities_returns_skills_and_tools(client):
    """Should return list of skills and tools."""
    r = client.post(
        "/api/auth/login",
        json={"email": "admin@empire.local", "password": "empire"},
    )
    token = r.json()["access_token"]
    r = client.get(
        "/api/capabilities",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "skills" in data
    assert "tools" in data
    # Should have at least 1 skill installed
    assert len(data["skills"]) >= 1
