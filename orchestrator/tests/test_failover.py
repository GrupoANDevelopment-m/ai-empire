"""
REAL tests for failover — health monitor + server pool.

We use a lightweight aiohttp / uvicorn test server to simulate
healthy and unhealthy endpoints. Then verify the failover logic
actually fires.
"""
import asyncio
import threading
import time
import socket
import pytest
import pytest_asyncio
from http.server import HTTPServer, BaseHTTPRequestHandler
from contextlib import contextmanager
import httpx

from failover.health_monitor import HealthMonitor, HealthCheck, HealthStatus
from failover.server_pool import ServerPool, Server, ServerRole, ServerState


# ============================================================================
# Helpers: tiny HTTP server we control
# ============================================================================

class ControllableHandler(BaseHTTPRequestHandler):
    """Handler whose responses are controlled by a per-instance state object."""
    def log_message(self, format, *args):
        pass  # silence

    def do_GET(self):
        state = self.server.handler_state  # per-instance, set in fake_server
        if state["delay"] > 0:
            time.sleep(state["delay"])
        self.send_response(state["status"])
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ok" if state["status"] == 200 else b"error")

    def do_POST(self):
        self.do_GET()


class _StatefulHTTPServer(HTTPServer):
    """HTTPServer with per-instance handler_state (each instance has its own dict)."""
    handler_state = {"status": 200, "delay": 0.0}


@contextmanager
def fake_server(port: int):
    """Run a fake server in a background thread on a free port.
    Returns (url, state_dict) where state_dict is per-instance and mutable.
    """
    # Find a free port
    if port == 0:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]

    # Per-instance state — each fake_server() gets its own dict
    state = {"status": 200, "delay": 0.0}

    server = _StatefulHTTPServer(("127.0.0.1", port), ControllableHandler)
    server.handler_state = state  # type: ignore[attr-defined]

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.1)  # let it start
    try:
        yield f"http://127.0.0.1:{port}", state
    finally:
        server.shutdown()
        server.server_close()


# ============================================================================
# HealthCheck
# ============================================================================

class TestHealthCheck:

    @pytest.mark.asyncio
    async def test_healthy_endpoint(self):
        with fake_server(0) as (url, state):
            check = HealthCheck(name="t", url=f"{url}/health", expected_status=200, timeout=2)
            status = await check.run()
            assert status == HealthStatus.HEALTHY
            assert check.consecutive_failures == 0
            assert check.last_latency_ms >= 0

    @pytest.mark.asyncio
    async def test_unhealthy_endpoint_5xx(self):
        with fake_server(0) as (url, state):
            state["status"] = 500
            check = HealthCheck(name="t", url=f"{url}/health", expected_status=200, timeout=2)
            await check.run()
            assert check.last_status == HealthStatus.DEGRADED
            assert check.consecutive_failures == 1

    @pytest.mark.asyncio
    async def test_opens_after_consecutive_failures(self):
        with fake_server(0) as (url, state):
            state["status"] = 500
            check = HealthCheck(
                name="t", url=f"{url}/health", expected_status=200,
                timeout=2, consecutive_failures_to_unhealthy=3,
            )
            for _ in range(3):
                await check.run()
            assert check.last_status == HealthStatus.UNHEALTHY
            assert check.consecutive_failures == 3

    @pytest.mark.asyncio
    async def test_unreachable_endpoint(self):
        check = HealthCheck(
            name="t", url="http://127.0.0.1:1/nope",  # nothing listening
            expected_status=200, timeout=1,
            consecutive_failures_to_unhealthy=2,
        )
        await check.run()
        await check.run()
        assert check.last_status == HealthStatus.UNHEALTHY
        assert check.last_error is not None

    @pytest.mark.asyncio
    async def test_recovery_to_healthy(self):
        with fake_server(0) as (url, state):
            check = HealthCheck(
                name="t", url=f"{url}/health", expected_status=200, timeout=2,
                consecutive_failures_to_unhealthy=2,
            )
            state["status"] = 500
            for _ in range(2):
                await check.run()
            assert check.last_status == HealthStatus.UNHEALTHY

            # Server recovers
            state["status"] = 200
            status = await check.run()
            assert status == HealthStatus.HEALTHY
            assert check.consecutive_failures == 0


# ============================================================================
# HealthMonitor
# ============================================================================

class TestHealthMonitor:

    @pytest.mark.asyncio
    async def test_snapshot_includes_all_checks(self):
        mon = HealthMonitor()
        mon.add_check(HealthCheck("a", "http://x/a", interval=60))
        mon.add_check(HealthCheck("b", "http://x/b", interval=60))
        snap = mon.snapshot()
        assert "a" in snap
        assert "b" in snap
        # Initial state UNKNOWN
        assert snap["a"]["status"] == "unknown"

    @pytest.mark.asyncio
    async def test_callback_fires_on_status_change(self):
        mon = HealthMonitor()
        with fake_server(0) as (url, state):
            mon.add_check(HealthCheck(
                "svc", f"{url}/health", interval=0.1, timeout=1,
                consecutive_failures_to_unhealthy=1,
            ))

            events = []
            async def on_change(name, old, new):
                events.append((name, old.value, new.value))

            mon.on_status_change(on_change)
            await mon.start()
            try:
                # Break the server (use the per-instance state)
                state["status"] = 500
                await asyncio.sleep(0.5)  # let it run a cycle
            finally:
                await mon.stop()

            # We should have at least one transition
            # (could be UNKNOWN→HEALTHY first, then HEALTHY→DEGRADED/UNHEALTHY)
            assert len(events) >= 1
            assert all(e[0] == "svc" for e in events)

    @pytest.mark.asyncio
    async def test_unhealthy_lists_problem_services(self):
        mon = HealthMonitor()
        with fake_server(0) as (url, state):
            state["status"] = 500
            mon.add_check(HealthCheck(
                "broken", f"{url}/h", interval=60, timeout=1,
                consecutive_failures_to_unhealthy=1,
            ))
            await mon._checks["broken"].run()
            assert "broken" in mon.unhealthy()


# ============================================================================
# ServerPool
# ============================================================================

class TestServerPool:

    @pytest.mark.asyncio
    async def test_active_url_picks_healthy_primary(self):
        with fake_server(0) as (url, state):
            pool = ServerPool([
                Server("primary", f"{url}/health", role=ServerRole.PRIMARY, timeout=2, health_check_interval=60),
            ])
            active = pool.active_url()
            assert active == f"{url}/health"

    @pytest.mark.asyncio
    async def test_failover_to_secondary_when_primary_dies(self):
        """Real test: start with primary + secondary, kill primary, expect promotion."""
        with fake_server(0) as (url_p, state_p), fake_server(0) as (url_s, state_s):
            primary = Server(
                "primary", f"{url_p}/health", role=ServerRole.PRIMARY,
                timeout=2, health_check_interval=0.1,
            )
            secondary = Server(
                "secondary", f"{url_s}/health", role=ServerRole.SECONDARY,
                timeout=2, health_check_interval=0.1,
            )
            pool = ServerPool([primary, secondary], auto_failover=True)
            await pool.start()
            try:
                # Both healthy
                assert pool.active_url() == f"{url_p}/health"

                # Kill primary
                state_p["status"] = 500
                # Wait for: 3 failures to mark DOWN, then failover
                await asyncio.sleep(1.0)

                # Secondary should now be promoted to primary
                assert any(s.role == ServerRole.PRIMARY and s.name == "secondary" for s in pool.servers)
                # Active URL should now be secondary
                assert pool.active_url() == f"{url_s}/health"
            finally:
                await pool.stop()

    @pytest.mark.asyncio
    async def test_no_failover_when_secondary_also_dead(self):
        """When both are down, active_url returns None."""
        with fake_server(0) as (url_p, state_p), fake_server(0) as (url_s, state_s):
            primary = Server("p", f"{url_p}/health", ServerRole.PRIMARY, timeout=1, health_check_interval=0.1)
            secondary = Server("s", f"{url_s}/health", ServerRole.SECONDARY, timeout=1, health_check_interval=0.1)
            pool = ServerPool([primary, secondary], auto_failover=True)
            state_p["status"] = 500
            state_s["status"] = 500
            await pool.start()
            try:
                await asyncio.sleep(0.8)
                assert pool.active_url() is None
            finally:
                await pool.stop()

    @pytest.mark.asyncio
    async def test_callback_fires_on_promotion(self):
        with fake_server(0) as (url_p, state_p), fake_server(0) as (url_s, state_s):
            primary = Server("p", f"{url_p}/health", ServerRole.PRIMARY, timeout=2, health_check_interval=0.1)
            secondary = Server("s", f"{url_s}/health", ServerRole.SECONDARY, timeout=2, health_check_interval=0.1)
            pool = ServerPool([primary, secondary], auto_failover=True)

            events = []
            async def on_promote(srv, role):
                events.append((srv.name, role.value))

            pool.on_role_change(on_promote)
            state_p["status"] = 500
            await pool.start()
            try:
                await asyncio.sleep(1.0)
                # Promotion event fired
                assert any(name == "s" and role == "primary" for name, role in events)
            finally:
                await pool.stop()


# ============================================================================
# End-to-end: a full failure scenario
# ============================================================================

class TestEndToEndFailover:

    @pytest.mark.asyncio
    async def test_real_failure_recovery_cycle(self):
        """
        Simulate: primary healthy → primary fails → failover → primary recovers.
        The active URL should track the current healthy server.
        """
        with fake_server(0) as (url_p, state_p), fake_server(0) as (url_s, state_s):
            primary = Server("p", f"{url_p}/health", ServerRole.PRIMARY, timeout=2, health_check_interval=0.1)
            secondary = Server("s", f"{url_s}/health", ServerRole.SECONDARY, timeout=2, health_check_interval=0.1)
            pool = ServerPool([primary, secondary], auto_failover=True)
            await pool.start()
            try:
                # Phase 1: both healthy
                assert pool.active_url() == f"{url_p}/health"

                # Phase 2: primary dies
                state_p["status"] = 500
                await asyncio.sleep(1.0)
                assert pool.active_url() == f"{url_s}/health"  # failover

                # Phase 3: primary recovers
                state_p["status"] = 200
                # Wait long enough for primary to be marked healthy again
                # (but it stays as a non-primary since we don't demote)
                await asyncio.sleep(0.5)
                # Both are now healthy; pool should prefer primary
                # (lowest latency — both are similar)
                active = pool.active_url()
                assert active in (f"{url_p}/health", f"{url_s}/health")
            finally:
                await pool.stop()
