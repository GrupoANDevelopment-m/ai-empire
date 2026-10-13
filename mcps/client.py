"""MCP client — loads MCP servers and routes tool calls."""
import os
import json
import asyncio
import importlib.util
from pathlib import Path
from typing import Any, Optional


class MCPClient:
    """Client for loading and invoking MCP servers."""
    
    def __init__(self, registry_path: Path = Path("mcps/registry/registry.yaml")):
        self.registry_path = registry_path
        self.servers: dict[str, Any] = {}
        self._loaded = False
    
    def load(self) -> None:
        """Load all available MCP servers from registry."""
        import yaml
        with open(self.registry_path) as f:
            registry = yaml.safe_load(f)
        
        for srv in registry.get("servers", []):
            name = srv["name"]
            path = Path(srv["path"])
            spec = importlib.util.spec_from_file_location(f"mcp_{name}", path / "server.py")
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                self.servers[name] = module
        self._loaded = True
    
    def list_tools(self) -> list[dict]:
        """Aggregate all tools from all loaded servers."""
        if not self._loaded:
            self.load()
        tools = []
        for name, srv in self.servers.items():
            for tool in srv.list_tools():
                tools.append({
                    "server": name,
                    "name": tool["name"],
                    "description": tool["description"],
                    "input_schema": tool["input_schema"],
                })
        return tools
    
    async def call(self, server: str, tool: str, arguments: dict) -> Any:
        """Call a tool on a specific server."""
        if not self._loaded:
            self.load()
        if server not in self.servers:
            raise KeyError(f"Unknown server: {server}")
        return await self.servers[server].call_tool(tool, arguments)
