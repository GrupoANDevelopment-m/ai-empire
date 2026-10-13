"""Google Maps MCP server — geocoding, directions, places."""
import os
import httpx

GOOGLE_MAPS_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")


def list_tools() -> list[dict]:
    return [
        {"name": "maps_geocode", "description": "Address → lat/lng",
         "input_schema": {"type": "object", "properties": {"address": {"type": "string"}}, "required": ["address"]}},
        {"name": "maps_reverse_geocode", "description": "lat/lng → address",
         "input_schema": {"type": "object", "properties": {"lat": {"type": "number"}, "lng": {"type": "number"}}, "required": ["lat", "lng"]}},
        {"name": "maps_directions", "description": "Get directions",
         "input_schema": {"type": "object", "properties": {"origin": {"type": "string"}, "destination": {"type": "string"}}, "required": ["origin", "destination"]}},
        {"name": "maps_places_search", "description": "Search places",
         "input_schema": {"type": "object", "properties": {"query": {"type": "string"}, "location": {"type": "string"}}, "required": ["query"]}},
    ]


async def call_tool(name: str, arguments: dict) -> dict:
    params = {"key": GOOGLE_MAPS_KEY}
    async with httpx.AsyncClient() as client:
        if name == "maps_geocode":
            r = await client.get("https://maps.googleapis.com/maps/api/geocode/json", params={**params, "address": arguments["address"]})
        elif name == "maps_reverse_geocode":
            r = await client.get("https://maps.googleapis.com/maps/api/geocode/json", params={**params, "latlng": f"{arguments['lat']},{arguments['lng']}"})
        elif name == "maps_directions":
            r = await client.get("https://maps.googleapis.com/maps/api/directions/json", params={**params, "origin": arguments["origin"], "destination": arguments["destination"]})
        elif name == "maps_places_search":
            r = await client.get("https://maps.googleapis.com/maps/api/place/textsearch/json", params={**params, "query": arguments["query"]})
        else:
            raise ValueError(f"Unknown tool: {name}")
        return r.json()
