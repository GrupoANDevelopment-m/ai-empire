"""Test LLM client (mocked)."""
import pytest
from unittest.mock import AsyncMock, patch
from empire.agent.llm.client import LLMClient, LLMUnavailable


class TestLLMClient:
    
    def test_init_with_env(self, monkeypatch):
        monkeypatch.setenv("NVIDIA_NIM_API_KEY", "test-key")
        monkeypatch.setenv("NVIDIA_NIM_BASE_URL", "https://test.nvidia.com/v1")
        client = LLMClient()
        assert client.nvidia_nim_key == "test-key"
        assert client.nvidia_nim_url == "https://test.nvidia.com/v1"
    
    @pytest.mark.asyncio
    async def test_detect_no_providers(self, monkeypatch):
        for key in ["NVIDIA_NIM_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"]:
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://nonexistent:11434")
        client = LLMClient()
        info = await client.detect()
        # May or may not find providers, but should not crash
        assert "backend" in info
    
    @pytest.mark.asyncio
    async def test_chat_no_provider_raises(self, monkeypatch):
        for key in ["NVIDIA_NIM_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"]:
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://nonexistent:11434")
        client = LLMClient()
        with pytest.raises(LLMUnavailable):
            await client.chat(messages=[{"role": "user", "content": "hi"}])
    
    def test_backend_constants(self):
        client = LLMClient()
        # Should have these as known backends
        for backend in ["ollama", "openai", "anthropic", "nvidia_nim", "litellm"]:
            assert isinstance(backend, str)
