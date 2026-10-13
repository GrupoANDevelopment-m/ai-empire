"""AI Empire Python SDK — official client library.

Installation:
    pip install ai-empire

Usage:
    from empire_client import EmpireClient
    client = EmpireClient(base_url="https://empire.example.com", token="...")
    
    # Chat
    response = await client.chat("Hello!")
    print(response.text)
    
    # Streaming
    async for chunk in client.chat_stream("Tell me a story"):
        print(chunk, end="")
    
    # Tools
    tools = await client.list_tools()
    result = await client.call_tool("browser_navigate", {"url": "https://example.com"})
"""
import os
import json
import asyncio
import httpx
from typing import Any, AsyncIterator, Optional


class EmpireError(Exception):
    """Base exception."""
    pass


class AuthenticationError(EmpireError):
    """401 — bad token."""
    pass


class RateLimitError(EmpireError):
    """429 — too many requests."""
    pass


class EmpireClient:
    """Synchronous + Async client for AI Empire API."""
    
    def __init__(
        self,
        base_url: str = os.getenv("EMPIRE_BASE_URL", "http://localhost:8080"),
        token: Optional[str] = os.getenv("EMPIRE_TOKEN"),
        timeout: float = 60.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
    
    async def __aenter__(self) -> "EmpireClient":
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            headers=self._headers(),
        )
        return self
    
    async def __aexit__(self, *args) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
    
    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h
    
    async def _request(self, method: str, path: str, **kwargs) -> Any:
        if not self._client:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                headers=self._headers(),
            )
        r = await self._client.request(method, path, **kwargs)
        if r.status_code == 401:
            raise AuthenticationError("Invalid or missing token")
        if r.status_code == 429:
            raise RateLimitError("Rate limit exceeded")
        r.raise_for_status()
        return r.json() if r.text else None
    
    async def login(self, email: str, password: str) -> str:
        """Login and return access token."""
        data = await self._request("POST", "/api/auth/login", json={"email": email, "password": password})
        self.token = data["access_token"]
        return self.token
    
    async def health(self) -> dict:
        return await self._request("GET", "/health")
    
    async def list_skills(self) -> list:
        data = await self._request("GET", "/api/capabilities")
        return data.get("skills", [])
    
    async def list_tools(self) -> list:
        data = await self._request("GET", "/api/capabilities")
        return data.get("tools", [])
    
    async def chat(self, message: str, session_id: Optional[str] = None) -> dict:
        return await self._request(
            "POST", "/api/chat",
            json={"message": message, "session_id": session_id},
        )
    
    async def chat_stream(self, message: str, session_id: Optional[str] = None) -> AsyncIterator[str]:
        """Stream chat response chunks."""
        if not self._client:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                headers=self._headers(),
            )
        async with self._client.stream(
            "POST", "/api/chat/stream",
            json={"message": message, "session_id": session_id, "stream": True},
        ) as r:
            async for line in r.aiter_lines():
                if line.startswith("data: "):
                    yield line[6:]
    
    async def call_tool(self, name: str, arguments: dict) -> Any:
        return await self._request(
            "POST", "/api/tools/call",
            json={"name": name, "arguments": arguments},
        )
    
    async def sanitize(self, text: str) -> str:
        """Sanitize HTML using bleach."""
        data = await self._request("POST", "/api/security/sanitize", json={"text": text})
        return data["sanitized"]
    
    async def browser_sessions(self) -> list:
        return await self._request("GET", "/api/browser/sessions")
    
    async def browser_open(self, tenant_id: str, profile: str = "default", headless: bool = True) -> str:
        data = await self._request(
            "POST", "/api/browser/sessions",
            json={"tenant_id": tenant_id, "profile": profile, "headless": headless},
        )
        return data["session_id"]


# Synchronous wrapper
class EmpireClientSync:
    """Sync version of EmpireClient."""
    
    def __init__(self, *args, **kwargs):
        self._async = EmpireClient(*args, **kwargs)
    
    def __enter__(self):
        asyncio.run(self._async.__aenter__())
        return self
    
    def __exit__(self, *args):
        asyncio.run(self._async.__aexit__(*args))
    
    def login(self, email: str, password: str) -> str:
        return asyncio.run(self._async.login(email, password))
    
    def chat(self, message: str, session_id: Optional[str] = None) -> dict:
        return asyncio.run(self._async.chat(message, session_id))
    
    def list_tools(self) -> list:
        return asyncio.run(self._async.list_tools())
    
    def health(self) -> dict:
        return asyncio.run(self._async.health())


# Example
if __name__ == "__main__":
    import sys
    async def main():
        async with EmpireClient() as c:
            print("Health:", await c.health())
            print("Tools:", len(await c.list_tools()))
    asyncio.run(main())
