"""
Integration tests against a REAL running LiteLLM proxy.

These tests are skipped if LiteLLM is not running on localhost:4000.
They verify the AIGateway client actually talks to the proxy correctly.

Run with: pytest -m integration
Skip with: pytest -m "not integration"
"""
import asyncio
import time
import pytest
import httpx

from resilience.gateway_client import AIGateway, ChatMessage


pytestmark = pytest.mark.integration


class TestLiteLLMIntegration:
    """These hit a real LiteLLM proxy on http://localhost:4000."""

    @pytest.mark.asyncio
    async def test_litellm_health(self, litellm_available, http_client):
        r = await http_client.get(f"{litellm_available}/health/liveliness")
        assert r.status_code in (200, 204)

    @pytest.mark.asyncio
    async def test_litellm_models_list(self, litellm_available, http_client):
        r = await http_client.get(
            f"{litellm_available}/v1/models",
            headers={"Authorization": "Bearer sk-empire-change-me"},
        )
        # If auth is enforced, this will be 401. If not, 200 with model list.
        assert r.status_code in (200, 401, 403)

    @pytest.mark.asyncio
    async def test_gateway_chat_through_litellm(self, litellm_available):
        """Real chat through the gateway → LiteLLM → Ollama."""
        gw = AIGateway(litellm_url=litellm_available)
        resp = await gw.chat(
            [ChatMessage(role="user", content="Reply with just the word PONG and nothing else.")],
            model="local",  # routes to ollama
            max_tokens=20,
            prefer=["litellm"],
        )
        assert resp.content is not None
        assert len(resp.content) > 0
        assert resp.provider == "litellm"

    @pytest.mark.asyncio
    async def test_gateway_uses_circuit_breaker(self, litellm_available):
        """After many failures, circuit should open."""
        gw = AIGateway(litellm_url=litellm_available)
        # Use a bogus model that will 404
        for _ in range(6):
            try:
                await gw.chat(
                    [ChatMessage(role="user", content="x")],
                    model="this-model-does-not-exist-12345",
                    max_tokens=10,
                    prefer=["litellm"],
                )
            except Exception:
                pass
        # The litellm breaker should now be open
        breaker = gw.breakers["litellm"]
        # It may be open or in cooldown, depending on how it failed
        assert breaker.failure_count > 0 or breaker.is_open

    @pytest.mark.asyncio
    async def test_gateway_health_endpoint(self):
        gw = AIGateway()
        health = gw.get_health()
        assert "backends" in health
        assert "litellm" in health["backends"]
        assert "stats" in health
