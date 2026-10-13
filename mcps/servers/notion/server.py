"""Notion MCP server — Notion workspace tools."""
import os
import httpx

NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")


def list_tools() -> list[dict]:
    return [
        {"name": "notion_search", "description": "Search Notion", "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
        {"name": "notion_create_page", "description": "Create a page", "input_schema": {"type": "object", "properties": {"parent": {"type": "string"}, "title": {"type": "string"}, "content": {"type": "string"}}, "required": ["parent", "title"]}},
        {"name": "notion_get_page", "description": "Get a page", "input_schema": {"type": "object", "properties": {"page_id": {"type": "string"}}, "required": ["page_id"]}},
    ]


async def call_tool(name: str, arguments: dict) -> dict:
    headers = {"Authorization": f"Bearer {NOTION_TOKEN}", "Notion-Version": "2022-06-28"}
    async with httpx.AsyncClient() as client:
        if name == "notion_search":
            r = await client.post("https://api.notion.com/v1/search", headers=headers, json={"query": arguments["query"]})
        elif name == "notion_create_page":
            r = await client.post("https://api.notion.com/v1/pages", headers=headers, json={"parent": {"id": arguments["parent"]}, "properties": {"title": {"title": [{"text": {"content": arguments["title"]}}]}}})
        elif name == "notion_get_page":
            r = await client.get(f"https://api.notion.com/v1/pages/{arguments['page_id']}", headers=headers)
        else:
            raise ValueError(f"Unknown tool: {name}")
        return r.json()
