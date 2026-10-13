"""GitHub MCP server — provides GitHub tools via REST API.

Tools: list_repos, get_issue, create_issue, create_pr, search_code
"""
import os
import httpx

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
BASE_URL = "https://api.github.com"


def list_tools() -> list[dict]:
    return [
        {"name": "github_list_repos", "description": "List repos for a user/org",
         "input_schema": {"type": "object", "properties": {"org": {"type": "string"}}}},
        {"name": "github_get_issue", "description": "Get a specific issue",
         "input_schema": {"type": "object", "properties": {"repo": {"type": "string"}, "number": {"type": "integer"}}, "required": ["repo", "number"]}},
        {"name": "github_create_issue", "description": "Create an issue",
         "input_schema": {"type": "object", "properties": {"repo": {"type": "string"}, "title": {"type": "string"}, "body": {"type": "string"}}, "required": ["repo", "title"]}},
        {"name": "github_create_pr", "description": "Create a PR",
         "input_schema": {"type": "object", "properties": {"repo": {"type": "string"}, "title": {"type": "string"}, "head": {"type": "string"}, "base": {"type": "string"}}, "required": ["repo", "title", "head", "base"]}},
        {"name": "github_search_code", "description": "Search code",
         "input_schema": {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}},
    ]


async def call_tool(name: str, arguments: dict) -> dict:
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}
    async with httpx.AsyncClient() as client:
        if name == "github_list_repos":
            org = arguments.get("org", "")
            url = f"{BASE_URL}/orgs/{org}/repos" if org else f"{BASE_URL}/user/repos"
            r = await client.get(url, headers=headers)
            return r.json()
        if name == "github_get_issue":
            r = await client.get(f"{BASE_URL}/repos/{arguments['repo']}/issues/{arguments['number']}", headers=headers)
            return r.json()
        if name == "github_create_issue":
            r = await client.post(
                f"{BASE_URL}/repos/{arguments['repo']}/issues",
                headers={**headers, "Content-Type": "application/json"},
                json={"title": arguments["title"], "body": arguments.get("body", "")},
            )
            return r.json()
        if name == "github_create_pr":
            r = await client.post(
                f"{BASE_URL}/repos/{arguments['repo']}/pulls",
                headers={**headers, "Content-Type": "application/json"},
                json={"title": arguments["title"], "head": arguments["head"], "base": arguments["base"]},
            )
            return r.json()
        if name == "github_search_code":
            r = await client.get(f"{BASE_URL}/search/code", params={"q": arguments["q"]}, headers=headers)
            return r.json()
    raise ValueError(f"Unknown tool: {name}")
