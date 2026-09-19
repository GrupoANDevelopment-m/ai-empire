"""
Pytest configuration and shared fixtures.

Markers:
  - unit: fast, no external deps
  - integration: hits HTTP endpoints (skip if service unavailable)
  - e2e: full pipeline test
  - chaos: actually kills/starts services (DANGEROUS, skip by default)
"""
import asyncio
import os
import sys
import socket
import pytest
import pytest_asyncio

# Add parent to path so imports work
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def pytest_configure(config):
    config.addinivalue_line("markers", "unit: unit tests (no external deps)")
    config.addinivalue_line("markers", "integration: hits real HTTP endpoints")
    config.addinivalue_line("markers", "e2e: full pipeline test")
    config.addinivalue_line("markers", "chaos: kills/starts services (dangerous)")


def _can_connect(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session")
def event_loop():
    """Single event loop for the whole session (pytest-asyncio default is per-test)."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def litellm_url():
    return os.getenv("LITELLM_URL", "http://localhost:4000")


@pytest.fixture
def litellm_available(litellm_url):
    """Skip the test if LiteLLM proxy is not running locally."""
    host = "localhost"
    port = 4000
    if not _can_connect(host, port):
        pytest.skip(f"LiteLLM proxy not running at {litellm_url}")
    return litellm_url


@pytest.fixture
def ollama_url():
    return os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


@pytest.fixture
def ollama_available(ollama_url):
    if not _can_connect("localhost", 11434):
        pytest.skip(f"Ollama not running at {ollama_url}")
    return ollama_url


@pytest.fixture
def chaos_allowed():
    """Only run chaos tests if explicitly enabled."""
    if not os.getenv("EMPIRE_CHAOS_TESTS", "").lower() in ("1", "true", "yes"):
        pytest.skip("Set EMPIRE_CHAOS_TESTS=1 to enable chaos tests")


@pytest_asyncio.fixture
async def http_client():
    """Shared httpx client."""
    import httpx
    async with httpx.AsyncClient(timeout=10.0) as client:
        yield client
