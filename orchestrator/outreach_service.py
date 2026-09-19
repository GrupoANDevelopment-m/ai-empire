"""
Outreach service — OpenOutreach + SalesGPT wrapper
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os

app = FastAPI(title="OpenOutreach Service", version="1.0.0")


class LeadSearchRequest(BaseModel):
    goal: str
    max_results: int = 50
    geo: dict | None = None


class CampaignRequest(BaseModel):
    leads: list[dict]
    channels: list[str]
    require_approval: bool = True


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/search")
async def search_leads(req: LeadSearchRequest):
    """
    Discover leads matching the goal.
    In production: invoke OpenOutreach's Bayesian ranking pipeline.
    Here: stub returning a structured response.
    """
    return {
        "leads": [
            {
                "id": f"lead-{i}",
                "name": f"Sample Lead {i}",
                "linkedin_url": f"https://linkedin.com/in/sample-{i}",
                "score": 80 - i,
            }
            for i in range(min(req.max_results, 10))
        ],
        "note": "This is a stub. Full OpenOutreach pipeline requires the full repo + LinkedIn credentials.",
    }


@app.post("/campaign")
async def start_campaign(req: CampaignRequest):
    """Launch an outreach campaign."""
    return {
        "campaign_id": "stub-id",
        "leads_queued": len(req.leads),
        "channels": req.channels,
        "approval_required": req.require_approval,
    }
