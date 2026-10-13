"""HubSpot MCP server — CRM tools."""
import os
import httpx

HUBSPOT_TOKEN = os.getenv("HUBSPOT_TOKEN", "")


def list_tools() -> list[dict]:
    return [
        {"name": "hubspot_create_contact", "description": "Create contact",
         "input_schema": {"type": "object", "properties": {"email": {"type": "string"}, "firstname": {"type": "string"}, "lastname": {"type": "string"}}, "required": ["email"]}},
        {"name": "hubspot_create_deal", "description": "Create deal",
         "input_schema": {"type": "object", "properties": {"name": {"type": "string"}, "amount": {"type": "number"}, "stage": {"type": "string"}}, "required": ["name", "amount"]}},
        {"name": "hubspot_list_contacts", "description": "List contacts",
         "input_schema": {"type": "object", "properties": {"limit": {"type": "integer"}}}},
    ]


async def call_tool(name: str, arguments: dict) -> dict:
    headers = {"Authorization": f"Bearer {HUBSPOT_TOKEN}"}
    async with httpx.AsyncClient() as client:
        if name == "hubspot_create_contact":
            r = await client.post("https://api.hubapi.com/crm/v3/objects/contacts", headers=headers, json={"properties": arguments})
        elif name == "hubspot_create_deal":
            r = await client.post("https://api.hubapi.com/crm/v3/objects/deals", headers=headers, json={"properties": arguments})
        elif name == "hubspot_list_contacts":
            r = await client.get("https://api.hubapi.com/crm/v3/objects/contacts", headers=headers, params={"limit": arguments.get("limit", 10)})
        else:
            raise ValueError(f"Unknown tool: {name}")
        return r.json()
