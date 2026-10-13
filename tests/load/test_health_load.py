"""Load test for /health endpoint."""
import time
import pytest
import asyncio
import httpx


@pytest.mark.asyncio
async def test_health_under_concurrent_load():
    """Health should handle 50 concurrent requests."""
    async with httpx.AsyncClient(base_url="http://localhost:8080") as client:
        start = time.time()
        tasks = [client.get("/health") for _ in range(50)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        duration = time.time() - start
        
        success = sum(1 for r in results if not isinstance(r, Exception) and r.status_code == 200)
        rate = 50 / duration if duration > 0 else 0
        
        print(f"50 concurrent /health: {success}/50 success, {rate:.1f} req/s")
        assert success >= 45  # allow 10% failure under extreme load
        assert rate >= 50  # at least 50 req/s


@pytest.mark.asyncio
async def test_capabilities_under_load():
    """Capabilities should handle 25 concurrent requests."""
    # First get a token
    async with httpx.AsyncClient(base_url="http://localhost:8080") as client:
        r = await client.post(
            "/api/auth/login",
            json={"email": "admin@empire.local", "password": "empire"},
        )
        if r.status_code != 200:
            pytest.skip("No auth")
        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        start = time.time()
        tasks = [
            client.get("/api/capabilities", headers=headers)
            for _ in range(25)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        duration = time.time() - start
        
        success = sum(1 for r in results if not isinstance(r, Exception) and r.status_code == 200)
        rate = 25 / duration if duration > 0 else 0
        
        print(f"25 concurrent /api/capabilities: {success}/25, {rate:.1f} req/s")
        assert success >= 22
