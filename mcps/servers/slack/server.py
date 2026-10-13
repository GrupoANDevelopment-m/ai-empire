"""Slack MCP server — Slack messaging tools."""
import os
import httpx

SLACK_TOKEN = os.getenv("SLACK_TOKEN", "")


def list_tools() -> list[dict]:
    return [
        {"name": "slack_post_message", "description": "Post a message",
         "input_schema": {"type": "object", "properties": {"channel": {"type": "string"}, "text": {"type": "string"}}, "required": ["channel", "text"]}},
        {"name": "slack_list_channels", "description": "List channels",
         "input_schema": {"type": "object", "properties": {}}},
        {"name": "slack_get_history", "description": "Get channel history",
         "input_schema": {"type": "object", "properties": {"channel": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["channel"]}},
    ]


async def call_tool(name: str, arguments: dict) -> dict:
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    async with httpx.AsyncClient() as client:
        if name == "slack_post_message":
            r = await client.post(
                "https://slack.com/api/chat.postMessage",
                headers=headers,
                json={"channel": arguments["channel"], "text": arguments["text"]},
            )
            return r.json()
        if name == "slack_list_channels":
            r = await client.get("https://slack.com/api/conversations.list", headers=headers)
            return r.json()
        if name == "slack_get_history":
            r = await client.get(
                "https://slack.com/api/conversations.history",
                params={"channel": arguments["channel"], "limit": arguments.get("limit", 20)},
                headers=headers,
            )
            return r.json()
    raise ValueError(f"Unknown tool: {name}")
