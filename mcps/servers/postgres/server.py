"""Postgres MCP server — SQL operations on a Postgres database."""
import os
import asyncpg
from typing import Any

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://empire:empire@localhost:5432/empire")


def list_tools() -> list[dict]:
    return [
        {"name": "pg_query", "description": "Run a SELECT query",
         "input_schema": {"type": "object", "properties": {"sql": {"type": "string"}, "params": {"type": "array"}}, "required": ["sql"]}},
        {"name": "pg_execute", "description": "Run an INSERT/UPDATE/DELETE",
         "input_schema": {"type": "object", "properties": {"sql": {"type": "string"}, "params": {"type": "array"}}, "required": ["sql"]}},
        {"name": "pg_list_tables", "description": "List tables",
         "input_schema": {"type": "object", "properties": {"schema": {"type": "string"}}}},
    ]


async def call_tool(name: str, arguments: dict) -> Any:
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        if name == "pg_query":
            if not arguments["sql"].strip().upper().startswith("SELECT"):
                raise ValueError("Use pg_execute for non-SELECT")
            return await conn.fetch(arguments["sql"], *(arguments.get("params") or []))
        if name == "pg_execute":
            return await conn.execute(arguments["sql"], *(arguments.get("params") or []))
        if name == "pg_list_tables":
            schema = arguments.get("schema", "public")
            return await conn.fetch(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = $1",
                schema,
            )
    finally:
        await conn.close()
    raise ValueError(f"Unknown tool: {name}")
