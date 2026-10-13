"""Filesystem MCP server — file operations in allowed paths."""
import os
import asyncio
from pathlib import Path

ALLOWED_PATHS = [Path(p) for p in os.getenv("FS_ALLOWED_PATHS", "/tmp,/workspace").split(",")]


def list_tools() -> list[dict]:
    return [
        {"name": "fs_read", "description": "Read a file", "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
        {"name": "fs_write", "description": "Write a file", "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
        {"name": "fs_list", "description": "List directory", "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
        {"name": "fs_delete", "description": "Delete a file", "input_schema": {"type": "object", "properties": {"path": {"type:": "string"}}, "required": ["path"]}},
    ]


def _is_allowed(path: str) -> bool:
    p = Path(path).resolve()
    return any(p.is_relative_to(a) for a in ALLOWED_PATHS)


async def call_tool(name: str, arguments: dict) -> any:
    path = arguments["path"]
    if not _is_allowed(path):
        raise PermissionError(f"Path {path} not in allowed list")
    p = Path(path)
    if name == "fs_read":
        return p.read_text()
    if name == "fs_write":
        p.write_text(arguments["content"])
        return {"written": len(arguments["content"])}
    if name == "fs_list":
        return [str(f) for f in p.iterdir()]
    if name == "fs_delete":
        p.unlink()
        return {"deleted": path}
    raise ValueError(f"Unknown tool: {name}")
