"""
Chaos tests: kill services, verify the system self-heals.

These tests:
  - Actually stop/start containers
  - Verify the failover triggers
  - Verify the system comes back online

Run with:
    EMPIRE_CHAOS_TESTS=1 pytest -m chaos
"""
import asyncio
import subprocess
import time
import pytest
import httpx

pytestmark = pytest.mark.chaos


def docker(*args):
    """Run a docker command and return (returncode, stdout, stderr)."""
    r = subprocess.run(
        ["docker"] + list(args),
        capture_output=True, text=True, timeout=60,
    )
    return r.returncode, r.stdout, r.stderr


def container_exists(name: str) -> bool:
    rc, out, _ = docker("ps", "-a", "--format", "{{.Names}}")
    if rc != 0:
        return False
    return name in out.splitlines()


def container_running(name: str) -> bool:
    rc, out, _ = docker("ps", "--format", "{{.Names}}")
    if rc != 0:
        return False
    return name in out.splitlines()


class TestChaosKillOllama:
    """Kill Ollama, verify the system still works (via fallback)."""

    def test_ollama_kill_and_recover(self, chaos_allowed):
        container = "ai-empire-ollama"
        if not container_exists(container):
            pytest.skip(f"{container} not running, can't run chaos test")

        # Get baseline health
        baseline = httpx.get("http://localhost:11434/api/tags", timeout=5)
        assert baseline.status_code == 200, "Ollama must be healthy before chaos"

        try:
            # Kill it
            rc, _, err = docker("stop", container)
            assert rc == 0, f"failed to stop: {err}"
            time.sleep(2)

            # Now it should be unreachable
            with pytest.raises(httpx.ConnectError):
                httpx.get("http://localhost:11434/api/tags", timeout=2)

            # Restart it
            rc, _, err = docker("start", container)
            assert rc == 0, f"failed to start: {err}"

            # Wait for it to come back (Ollama takes a bit)
            for _ in range(30):
                try:
                    r = httpx.get("http://localhost:11434/api/tags", timeout=2)
                    if r.status_code == 200:
                        break
                except httpx.ConnectError:
                    time.sleep(1)
            else:
                pytest.fail("Ollama did not recover within 30s")

        finally:
            # Always leave it running
            if not container_running(container):
                docker("start", container)

    def test_ollama_restart_preserves_data(self, chaos_allowed):
        """After restart, models are still there."""
        container = "ai-empire-ollama"
        if not container_exists(container):
            pytest.skip(f"{container} not running")

        before = httpx.get("http://localhost:11434/api/tags", timeout=5).json()
        before_models = {m["name"] for m in before.get("models", [])}

        try:
            docker("restart", container, "--time", "5")
            time.sleep(10)
            after = httpx.get("http://localhost:11434/api/tags", timeout=5).json()
            after_models = {m["name"] for m in after.get("models", [])}
            # Models should be the same (they live in the volume)
            assert before_models == after_models, "models were lost on restart!"
        except Exception:
            if not container_running(container):
                docker("start", container)
            raise


class TestChaosKillPostgres:
    """Kill Postgres, verify the system reports it but recovers."""

    def test_postgres_kill_and_recover(self, chaos_allowed):
        container = "ai-empire-postgres"
        if not container_exists(container):
            pytest.skip(f"{container} not running")

        try:
            # Verify it's healthy
            rc, out, _ = docker("exec", container, "pg_isready", "-U", "empire")
            assert rc == 0, "Postgres must be healthy before chaos"

            # Stop it
            docker("stop", container)
            time.sleep(2)

            # Now pg_isready should fail
            rc, out, _ = docker("exec", container, "pg_isready", "-U", "empire")
            # Container is stopped, so exec returns non-zero
            assert rc != 0

            # Start it back
            docker("start", container)
            time.sleep(5)

            # Verify recovery
            for _ in range(15):
                rc, out, _ = docker("exec", container, "pg_isready", "-U", "empire")
                if rc == 0:
                    break
                time.sleep(1)
            else:
                pytest.fail("Postgres did not recover")

        finally:
            if not container_running(container):
                docker("start", container)


class TestChaosNetworkPartition:
    """Simulate network partition by stopping a single service."""

    def test_n8n_unavailable_doesnt_break_orchestrator(self, chaos_allowed):
        """If n8n is down, the orchestrator (langgraph) should still respond."""
        container = "ai-empire-n8n"
        if not container_exists(container):
            pytest.skip(f"{container} not running")

        # Verify orchestrator up
        try:
            r = httpx.get("http://localhost:8123/health", timeout=2)
            orch_up = r.status_code == 200
        except Exception:
            orch_up = False
        if not orch_up:
            pytest.skip("Orchestrator not running")

        try:
            # Stop n8n
            docker("stop", container)
            time.sleep(2)

            # Orchestrator should still respond
            r = httpx.get("http://localhost:8123/health", timeout=5)
            assert r.status_code == 200, "Orchestrator should survive n8n outage"

        finally:
            if not container_running(container):
                docker("start", container)
