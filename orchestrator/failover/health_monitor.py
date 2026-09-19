"""
Health Monitor — periodically checks the health of critical services.
Triggers failovers when a primary goes down.
"""
from __future__ import annotations
import time
import asyncio
import logging
import httpx
from enum import Enum
from typing import Callable, Awaitable
from dataclasses import dataclass, field

log = logging.getLogger("empire.failover.health")


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthCheck:
    name: str
    url: str
    interval: float = 30.0
    timeout: float = 5.0
    expected_status: int = 200
    consecutive_failures_to_unhealthy: int = 3
    method: str = "GET"
    body: dict | None = None
    headers: dict = field(default_factory=dict)
    last_status: HealthStatus = HealthStatus.UNKNOWN
    last_checked: float = 0.0
    last_latency_ms: float = 0.0
    consecutive_failures: int = 0
    last_error: str | None = None

    async def run(self) -> HealthStatus:
        start = time.time()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                if self.method.upper() == "GET":
                    r = await client.get(self.url, headers=self.headers)
                else:
                    r = await client.post(self.url, json=self.body, headers=self.headers)
                latency = (time.time() - start) * 1000
                self.last_latency_ms = latency
                self.last_checked = time.time()
                if r.status_code == self.expected_status:
                    self.consecutive_failures = 0
                    self.last_status = HealthStatus.HEALTHY
                    self.last_error = None
                elif r.status_code in (429, 503):
                    self.consecutive_failures += 1
                    self.last_status = HealthStatus.DEGRADED
                    self.last_error = f"HTTP {r.status_code}"
                else:
                    self.consecutive_failures += 1
                    self.last_error = f"HTTP {r.status_code}"
                    if self.consecutive_failures >= self.consecutive_failures_to_unhealthy:
                        self.last_status = HealthStatus.UNHEALTHY
                    else:
                        self.last_status = HealthStatus.DEGRADED
        except Exception as e:
            self.consecutive_failures += 1
            self.last_checked = time.time()
            self.last_latency_ms = (time.time() - start) * 1000
            self.last_error = f"{type(e).__name__}: {str(e)[:200]}"
            if self.consecutive_failures >= self.consecutive_failures_to_unhealthy:
                self.last_status = HealthStatus.UNHEALTHY
            else:
                self.last_status = HealthStatus.DEGRADED
        return self.last_status


class HealthMonitor:
    """
    Manages health checks for multiple services. Runs them in background.
    Provides a snapshot of current health. Triggers callbacks on status changes.
    """

    def __init__(self):
        self._checks: dict[str, HealthCheck] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._callbacks: list[Callable[[str, HealthStatus, HealthStatus], Awaitable[None]]] = []
        self._running = False

    def add_check(self, check: HealthCheck) -> None:
        self._checks[check.name] = check
        log.info(f"Added health check: {check.name} → {check.url}")

    def on_status_change(self, cb: Callable[[str, HealthStatus, HealthStatus], Awaitable[None]]) -> None:
        """Register a callback: (check_name, old_status, new_status) → coroutine."""
        self._callbacks.append(cb)

    def get(self, name: str) -> HealthCheck | None:
        return self._checks.get(name)

    def snapshot(self) -> dict:
        return {
            name: {
                "status": c.last_status.value,
                "last_checked": c.last_checked,
                "latency_ms": round(c.last_latency_ms, 1),
                "consecutive_failures": c.consecutive_failures,
                "last_error": c.last_error,
                "url": c.url,
            }
            for name, c in self._checks.items()
        }

    def unhealthy(self) -> list[str]:
        return [n for n, c in self._checks.items() if c.last_status == HealthStatus.UNHEALTHY]

    def healthy(self) -> list[str]:
        return [n for n, c in self._checks.items() if c.last_status == HealthStatus.HEALTHY]

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        for name, check in self._checks.items():
            self._tasks[name] = asyncio.create_task(self._loop(check))
        log.info(f"HealthMonitor started, {len(self._tasks)} checks running")

    async def stop(self) -> None:
        self._running = False
        for t in self._tasks.values():
            t.cancel()
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()
        log.info("HealthMonitor stopped")

    async def _loop(self, check: HealthCheck) -> None:
        while self._running:
            prev = check.last_status
            new = await check.run()
            if new != prev and new in (HealthStatus.UNHEALTHY, HealthStatus.HEALTHY):
                log.warning(f"Health change: {check.name} {prev.value} → {new.value}")
                for cb in self._callbacks:
                    try:
                        await cb(check.name, prev, new)
                    except Exception as e:
                        log.error(f"Callback error: {e}")
            await asyncio.sleep(check.interval)
