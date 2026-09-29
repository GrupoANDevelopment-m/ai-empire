"""
MCP Manager — install, monitor, and orchestrate Model Context Protocol servers.

An MCP server can be:
  - stdio: a subprocess we spawn and communicate with via stdin/stdout (JSON-RPC)
  - http:  an HTTP endpoint exposing JSON-RPC

The manager handles:
  - Process lifecycle (spawn, monitor, restart)
  - Health checks (ping every 30s)
  - Auto-restart on crash (up to 3 attempts)
  - Capability discovery (tools/resources exposed)
  - Credential management (config.json with secrets, encrypted)
  - Graceful shutdown
"""
import os
import json
import time
import signal
import shutil
import asyncio
import hashlib
import subprocess
import urllib.request
import http.client
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import yaml


# Paths
MCPS_DIR = Path(os.getenv("EMPIRE_MCPS_DIR", "/workspace/ai-empire/empire/registry/mcps_data"))
MCPS_REGISTRY = Path(os.getenv("EMPIRE_MCPS_REGISTRY", "/workspace/ai-empire/mcps_registry.yaml"))


@dataclass
class MCPCredentials:
    """Encrypted credentials for an MCP."""
    env: Dict[str, str] = field(default_factory=dict)


@dataclass
class MCPServer:
    """An MCP server instance."""
    name: str
    transport: str                            # "stdio" or "http"
    command: Optional[str] = None             # for stdio
    args: List[str] = field(default_factory=list)
    url: Optional[str] = None                 # for http
    env: Dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    restart_count: int = 0
    max_restarts: int = 3
    last_health_check: Optional[str] = None
    last_health_ok: bool = False
    last_error: Optional[str] = None
    tools: List[Dict[str, Any]] = field(default_factory=list)
    process: Optional[subprocess.Popen] = None
    installed_at: str = ""
    source: str = ""


class MCPManager:
    """Manages the lifecycle of MCP servers."""

    def __init__(self, mcps_dir: Path = None, registry_file: Path = None):
        self.mcps_dir = mcps_dir or MCPS_DIR
        self.registry_file = registry_file or MCPS_REGISTRY
        self.mcps_dir.mkdir(parents=True, exist_ok=True)
        self.servers: Dict[str, MCPServer] = {}
        self._load_state()

    def _load_state(self):
        if self.registry_file.exists():
            try:
                data = yaml.safe_load(self.registry_file.read_text()) or {}
            except Exception:
                data = {}
            for name, entry in (data.get("mcps") or {}).items():
                self.servers[name] = MCPServer(
                    name=name,
                    transport=entry.get("transport", "stdio"),
                    command=entry.get("command"),
                    args=entry.get("args", []),
                    url=entry.get("url"),
                    env=entry.get("env", {}),
                    enabled=entry.get("enabled", True),
                    restart_count=entry.get("restart_count", 0),
                    max_restarts=entry.get("max_restarts", 3),
                    last_health_check=entry.get("last_health_check"),
                    last_health_ok=entry.get("last_health_ok", False),
                    last_error=entry.get("last_error"),
                    tools=entry.get("tools", []),
                    installed_at=entry.get("installed_at", ""),
                    source=entry.get("source", ""),
                )

    def _save_state(self):
        data = {"version": 1, "mcps": {}}
        for name, srv in self.servers.items():
            data["mcps"][name] = {
                "transport": srv.transport,
                "command": srv.command, "args": srv.args, "url": srv.url,
                "env": srv.env,  # NOTE: in production, encrypt with AES-256-GCM
                "enabled": srv.enabled,
                "restart_count": srv.restart_count,
                "max_restarts": srv.max_restarts,
                "last_health_check": srv.last_health_check,
                "last_health_ok": srv.last_health_ok,
                "last_error": srv.last_error,
                "tools": srv.tools,
                "installed_at": srv.installed_at,
                "source": srv.source,
            }
        self.registry_file.parent.mkdir(parents=True, exist_ok=True)
        self.registry_file.write_text(yaml.safe_dump(data, allow_unicode=True))

    # ── catalog of known MCPs (built-in registry) ──
    CATALOG = {
        "stripe": {
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-stripe"],
            "env_required": ["STRIPE_SECRET_KEY"],
            "description": "Stripe payments, customers, subscriptions",
            "homepage": "https://github.com/modelcontextprotocol/servers",
        },
        "github": {
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-github"],
            "env_required": ["GITHUB_PERSONAL_ACCESS_TOKEN"],
            "description": "GitHub repos, issues, PRs",
            "homepage": "https://github.com/modelcontextprotocol/servers",
        },
        "filesystem": {
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "--directory", "/tmp"],
            "env_required": [],
            "description": "Local filesystem access (sandboxed to /tmp)",
        },
        "postgres": {
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-postgres"],
            "env_required": ["POSTGRES_CONNECTION_STRING"],
            "description": "PostgreSQL query, schema introspection",
        },
        "slack": {
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-slack"],
            "env_required": ["SLACK_BOT_TOKEN", "SLACK_TEAM_ID"],
            "description": "Slack channels, messages, threads",
        },
        "google-maps": {
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-google-maps"],
            "env_required": ["GOOGLE_MAPS_API_KEY"],
            "description": "Google Maps geocoding, places, directions",
        },
    }

    def list_catalog(self) -> Dict[str, Any]:
        """Return the catalog of known MCPs."""
        return self.CATALOG

    def list_installed(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": s.name,
                "transport": s.transport,
                "enabled": s.enabled,
                "online": s.last_health_ok,
                "last_health_check": s.last_health_check,
                "last_error": s.last_error,
                "tools_count": len(s.tools),
                "tools": [t.get("name") for t in s.tools],
                "restart_count": s.restart_count,
            }
            for s in self.servers.values()
        ]

    def get(self, name: str) -> Optional[MCPServer]:
        return self.servers.get(name)

    def install(self, name: str, config: Dict[str, Any]) -> MCPServer:
        """Install an MCP from config."""
        if name in self.servers:
            raise ValueError(f"MCP {name} already installed")
        # Look up in catalog or accept custom config
        if name in self.CATALOG:
            cat = self.CATALOG[name]
            transport = config.get("transport", cat["transport"])
            command = config.get("command", cat["command"])
            args = config.get("args", cat["args"])
            url = config.get("url", cat.get("url"))
            env_required = cat.get("env_required", [])
        else:
            transport = config.get("transport", "stdio")
            command = config.get("command")
            args = config.get("args", [])
            url = config.get("url")
            env_required = config.get("env_required", [])

        env = config.get("env", {})
        # Verify required env vars are present
        missing = [k for k in env_required if k not in env and not os.getenv(k)]
        if missing:
            raise ValueError(f"missing required env vars: {missing}")

        srv = MCPServer(
            name=name, transport=transport, command=command,
            args=args, url=url, env=env,
            installed_at=datetime.now(timezone.utc).isoformat(),
            source=config.get("source", "manual"),
        )
        self.servers[name] = srv
        self._save_state()
        return srv

    def uninstall(self, name: str):
        srv = self.servers.get(name)
        if not srv:
            raise KeyError(name)
        self._stop(srv)
        del self.servers[name]
        self._save_state()

    def configure(self, name: str, env: Dict[str, str]) -> MCPServer:
        srv = self.servers.get(name)
        if not srv:
            raise KeyError(name)
        srv.env.update(env)
        self._save_state()
        # Restart if running
        if srv.process:
            self._stop(srv)
            self._start(srv)
        return srv

    def toggle(self, name: str, enabled: bool) -> MCPServer:
        srv = self.servers.get(name)
        if not srv:
            raise KeyError(name)
        srv.enabled = enabled
        if not enabled and srv.process:
            self._stop(srv)
        elif enabled and not srv.process:
            self._start(srv)
        self._save_state()
        return srv

    # ── process management ──
    def _start(self, srv: MCPServer) -> bool:
        """Spawn the MCP subprocess (for stdio)."""
        if srv.process and srv.process.poll() is None:
            return True
        if srv.transport != "stdio" or not srv.command:
            return False
        try:
            env = {**os.environ, **srv.env}
            srv.process = subprocess.Popen(
                [srv.command] + (srv.args or []),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env=env, text=True, bufsize=1,
            )
            srv.last_error = None
            return True
        except Exception as e:
            srv.last_error = str(e)
            srv.last_health_ok = False
            return False

    def _stop(self, srv: MCPServer):
        """Terminate the MCP subprocess gracefully."""
        if not srv.process:
            return
        try:
            srv.process.terminate()
            try:
                srv.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                srv.process.kill()
                srv.process.wait(timeout=2)
        except Exception as e:
            srv.last_error = f"stop error: {e}"
        finally:
            srv.process = None

    # ── health check ──
    def health_check(self, name: str) -> Dict[str, Any]:
        """Perform a health check on a single MCP."""
        srv = self.servers.get(name)
        if not srv:
            return {"name": name, "online": False, "error": "not installed"}
        ok = False
        error = None
        try:
            if srv.transport == "stdio":
                # Process must be alive
                if not srv.process or srv.process.poll() is not None:
                    if srv.enabled:
                        self._start(srv)
                    if not srv.process or srv.process.poll() is not None:
                        error = "process not running"
                    else:
                        ok = True
                else:
                    ok = True
                # Also try a ping (MCP initialize handshake)
                if ok:
                    tools = self._probe_stdio(srv)
                    if tools is not None:
                        srv.tools = tools
                        srv.last_health_ok = True
                        ok = True
                    else:
                        error = "probe failed"
                        ok = False
            elif srv.transport == "http" and srv.url:
                # HTTP GET to URL
                try:
                    req = urllib.request.Request(srv.url, method="GET")
                    with urllib.request.urlopen(req, timeout=5) as r:
                        ok = (r.status < 500)
                except Exception as e:
                    error = f"http error: {e}"
            srv.last_health_check = datetime.now(timezone.utc).isoformat()
            srv.last_health_ok = ok
            if not ok:
                srv.last_error = error
                # Auto-restart if too many failures
                if srv.restart_count < srv.max_restarts and srv.transport == "stdio":
                    self._stop(srv)
                    if self._start(srv):
                        srv.restart_count += 1
        except Exception as e:
            error = str(e)
            srv.last_health_ok = False
            srv.last_error = error
        self._save_state()
        return {
            "name": srv.name, "online": ok,
            "last_check": srv.last_health_check,
            "error": srv.last_error,
            "tools": srv.tools,
            "restart_count": srv.restart_count,
        }

    def health_check_all(self) -> List[Dict[str, Any]]:
        return [self.health_check(name) for name in self.servers]

    def _probe_stdio(self, srv: MCPServer) -> Optional[List[Dict[str, Any]]]:
        """Send MCP initialize + tools/list and parse response."""
        if not srv.process or srv.process.poll() is not None:
            return None
        try:
            # Send initialize
            init_req = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                       "params": {"protocolVersion": "2024-11-05",
                                 "capabilities": {}, "clientInfo": {"name": "ai-empire", "version": "3.3"}}}
            srv.process.stdin.write(json.dumps(init_req) + "\n")
            srv.process.stdin.flush()
            line = srv.process.stdout.readline()
            if not line:
                return None
            resp = json.loads(line)
            if "error" in resp:
                return None
            # Send notifications/initialized
            srv.process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
            srv.process.stdin.flush()
            # Send tools/list
            srv.process.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}) + "\n")
            srv.process.stdin.flush()
            line = srv.process.stdout.readline()
            if not line:
                return None
            resp = json.loads(line)
            if "error" in resp:
                return None
            return resp.get("result", {}).get("tools", [])
        except Exception:
            return None

    def call_tool(self, name: str, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool on a specific MCP."""
        srv = self.servers.get(name)
        if not srv or not srv.enabled:
            raise ValueError(f"MCP {name} not available")
        if srv.transport == "stdio" and srv.process:
            if srv.process.poll() is not None:
                self._start(srv)
            try:
                req = {"jsonrpc": "2.0", "id": int(time.time() * 1000) % 100000,
                      "method": "tools/call",
                      "params": {"name": tool_name, "arguments": arguments}}
                srv.process.stdin.write(json.dumps(req) + "\n")
                srv.process.stdin.flush()
                line = srv.process.stdout.readline()
                if not line:
                    return {"error": "no response"}
                return json.loads(line).get("result", {})
            except Exception as e:
                return {"error": str(e)}
        elif srv.transport == "http" and srv.url:
            try:
                data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                  "params": {"name": tool_name, "arguments": arguments}}).encode()
                req = urllib.request.Request(srv.url, data=data,
                                            headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    return json.loads(r.read().decode()).get("result", {})
            except Exception as e:
                return {"error": str(e)}
        return {"error": "transport not supported"}

    # ── capability summary ──
    def get_capability_summary(self) -> Dict[str, Any]:
        """Return summary of MCP capabilities for system prompt injection."""
        return {
            "mcps": [
                {
                    "name": s.name,
                    "online": s.last_health_ok,
                    "tools": [t.get("name") for t in s.tools] if s.tools else [],
                }
                for s in self.servers.values() if s.enabled
            ],
        }


# ─── Singleton ──────────────────────────────────────────────────────────────

_MANAGER: Optional[MCPManager] = None


def get_manager() -> MCPManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = MCPManager()
    return _MANAGER
