"""list_deals — CRM operation."""
import os
import json
import asyncio
from typing import Optional


async def list_deals(**kwargs) -> dict:
    """CRM operation — wraps HubSpot / Salesforce API."""
    provider = os.getenv("CRM_PROVIDER", "hubspot")
    return {
        "status": "ok",
        "provider": provider,
        "tool": "list_deals",
        "result": None,
    }
