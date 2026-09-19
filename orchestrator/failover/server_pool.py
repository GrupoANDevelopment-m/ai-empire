"""
Server Pool — manages a pool of servers (e.g. multiple LLM backends,
multiple Ollama instances, multiple regional deployments).
Promotes a backup when primary fails. Demotes on recovery.
"""
from __future__ import annotations
import asyncio
import time
import logging
import httpx
from enum import Enum
from typing import Callable, Awaitable
from dataclasses import dataclass, field

log = logging.getLogger("empire.failover.pool")


class ServerRole(str, Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    STANDBY = "standby"


class ServerState(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"
    PROMOTING = "promoting"
    DEMOTING = "demoting"


@dataclass
class Server:
    name: str
    url: str
    role: ServerRole = ServerRole.STANDBY
    state: ServerState = ServerState.HEALTHY
    last_health_check: float = 0.0
    last_latency_ms: float = 0.0
    health_check_interval: float = 10.0
    timeout: float = 5.0
    consecutive_failures: int = 0
    metadata: dict = field(default_factory=dict)

    async def ping(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.get(f"{self.url}/health")
                ok = r.status_code in (200, 204)
                self.last_health_check = time.time()
                self.last_latency_ms = r.elapsed.total_seconds() * 1000
                if ok:
                    self.consecutive_failures = 0
                    if self.state in (ServerState.DOWN, ServerState.DEMOTING):
                        self.state = ServerState.HEALTHY
                else:
                    self.consecutive_failures += 1
                    if self.consecutive_failures >= 3:
                        self.state = ServerState.DOWN
                return ok
        except Exception:
            self.consecutive_failures += 1
            self.last_health_check = time.time()
            if self.consecutive_failures >= 3:
                self.state = ServerState.DOWN
            return False


class ServerPool:
    """
    Manages a pool of servers with auto-failover.

    Pattern:
      - One or more primaries
      - N secondaries (ready to take over)
      - M standbys (warmed but not active)

    When all primaries go DOWN, promote the best secondary.
    When a primary comes back, optionally demote (or keep current).

    Usage:
        pool = ServerPool([
            Server("ollama-eu", "http://ollama-eu:11434", role=ServerRole.PRIMARY),
            Server("ollama-us", "http://ollama-us:11434", role=ServerRole.SECONDARY),
            Server("ollama-asia", "http://ollama-asia:11434", role=ServerRole.SECONDARY),
        ])
        await pool.start()
        # Route to active server
        url = pool.active_url()
    """

    def __init__(self, servers: list[Server] | None = None, auto_failover: bool = True):
        self.servers: list[Server] = servers or []
        self.auto_failover = auto_failover
        self._task: asyncio.Task | None = None
        self._running = False
        self._lock = asyncio.Lock()
        self._callbacks: list[Callable[[Server, ServerRole], Awaitable[None]]] = []

    def add(self, server: Server) -> None:
        self.servers.append(server)

    def on_role_change(self, cb: Callable[[Server, ServerRole], Awaitable[None]]) -> None:
        self._callbacks.append(cb)

    def active_servers(self) -> list[Server]:
        """Servers that can receive traffic right now (healthy + primary or secondary)."""
        return [
            s for s in self.servers
            if s.state == ServerState.HEALTHY
            and s.role in (ServerRole.PRIMARY, ServerRole.SECONDARY)
        ]

    def active_url(self) -> str | None:
        active = self.active_servers()
        if not active:
            return None
        # Pick the one with lowest latency
        active.sort(key=lambda s: s.last_latency_ms)
        return active[0].url

    def primaries(self) -> list[Server]:
        return [s for s in self.servers if s.role == ServerRole.PRIMARY]

    def secondaries(self) -> list[Server]:
        return [s for s in self.servers if s.role == ServerRole.SECONDARY]

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        log.info(f"ServerPool started with {len(self.servers)} servers")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self) -> None:
        while self._running:
            for s in self.servers:
                await s.ping()

            if self.auto_failover:
                await self._maybe_failover()

            # Sleep the smallest interval
            sleep_for = min((s.health_check_interval for s in self.servers), default=5.0)
            await asyncio.sleep(sleep_for)

    async def _maybe_failover(self) -> None:
        async with self._lock:
            # Find primaries that are down
            down_primaries = [s for s in self.primaries() if s.state == ServerState.DOWN]
            if not down_primaries:
                return

            # Find healthy secondaries
            healthy_seconds = [s for s in self.secondaries() if s.state == ServerState.HEALTHY]
            if not healthy_seconds:
                log.error("No healthy secondaries available for failover!")
                return

            # Pick the secondary with lowest latency
            best = min(healthy_seconds, key=lambda s: s.last_latency_ms)
            log.warning(
                f"FAILOVER: {down_primaries[0].name} (primary) is DOWN. "
                f"Promoting {best.name} (secondary) to primary."
            )
            best.state = ServerState.PROMOTING
            best.role = ServerRole.PRIMARY
            for cb in self._callbacks:
                try:
                    await cb(best, ServerRole.PRIMARY)
                except Exception as e:
                    log.error(f"Callback error: {e}")
            best.state = ServerState.HEALTHY
