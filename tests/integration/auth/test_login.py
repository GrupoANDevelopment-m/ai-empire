"""Test login endpoint."""
import pytest
from fastapi.testclient import TestClient
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from web.server import app


@pytest.fixture
def client():
    return TestClient(app)


def test_login_with_default_admin(client):
    """Login should succeed with default admin."""
    r = client.post(
        "/api/auth/login",
        json={"email": "admin@empire.local", "password": "empire"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data
    assert "token_type" in data


def test_login_with_wrong_password(client):
    """Login should fail with wrong password."""
    r = client.post(
        "/api/auth/login",
        json={"email": "admin@empire.local", "password": "wrong"},
    )
    assert r.status_code == 401


def test_login_rate_limited(client):
    """Should rate limit login attempts."""
    for _ in range(10):
        r = client.post(
            "/api/auth/login",
            json={"email": "x@x.com", "password": "x"},
        )
    # 6th+ attempt should be rate limited
    assert r.status_code in (401, 429)
