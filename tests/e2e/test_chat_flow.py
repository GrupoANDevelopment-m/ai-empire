"""End-to-end test for chat with tool calling."""
import pytest
from fastapi.testclient import TestClient
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from web.server import app


@pytest.fixture
def client():
    return TestClient(app)


def test_chat_requires_auth(client):
    """Chat endpoint should require auth."""
    r = client.post(
        "/api/chat",
        json={"message": "hello"},
    )
    assert r.status_code in (401, 403)


def test_chat_creates_session(client):
    """First chat should create a session."""
    # Login
    r = client.post(
        "/api/auth/login",
        json={"email": "admin@empire.local", "password": "empire"},
    )
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # Send chat
    r = client.post(
        "/api/chat",
        headers=headers,
        json={"message": "Hello, AI Empire!"},
    )
    # Should either succeed (200) or 503 (no LLM)
    assert r.status_code in (200, 503)
    if r.status_code == 200:
        data = r.json()
        assert "session_id" in data
        assert "response" in data
