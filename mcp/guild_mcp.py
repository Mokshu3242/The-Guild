"""The Guild as an MCP server, so a client's AI (Claude Desktop, Cursor, any MCP client)
can quote and hire the guild as tools.

It only talks to the guild's public API with an API key. It never touches the database.

Setup:
    pip install -r requirements.txt
    set GUILD_API_KEY=guild_...            (from the Agent page, admins only)
    set GUILD_API_URL=https://guild-backend-vqg5.onrender.com
    python guild_mcp.py                    (stdio, started by the MCP client)
"""
import os

import httpx
from mcp.server.fastmcp import FastMCP

API_URL = os.environ.get("GUILD_API_URL", "http://127.0.0.1:8000").rstrip("/")
API_KEY = os.environ.get("GUILD_API_KEY", "")
TIMEOUT = 120  # Render's free tier can take a minute to wake up

mcp = FastMCP(
    "the-guild",
    instructions=(
        "The Guild is a group of freelancers who share one safety pool. "
        "To hire them: call quote_guild_job with the client's brief, show the client the milestones and total, "
        "and only call hire_guild after the client says yes. Prices come from the quote and can't be changed. "
        "After hiring, give the client the portal_url. They accept the agreement and pay each milestone there "
        "through PayPal. Use check_guild_job to see progress."
    ),
)


def _call(method: str, path: str, body: dict | None = None) -> dict:
    if not API_KEY:
        return {"error": "GUILD_API_KEY is not set. Ask the guild admin for a key."}
    try:
        r = httpx.request(method, f"{API_URL}{path}", json=body, timeout=TIMEOUT,
                          headers={"X-API-Key": API_KEY})
    except httpx.HTTPError as e:
        return {"error": f"Couldn't reach the guild: {e.__class__.__name__}. Try again in a minute."}
    try:
        data = r.json()
    except ValueError:
        data = {"detail": r.text[:300]}
    if r.status_code >= 400:
        detail = data.get("detail", data) if isinstance(data, dict) else data
        return {"error": detail, "status_code": r.status_code}
    return data


@mcp.tool()
def quote_guild_job(brief: str) -> dict:
    """Get a priced quote from The Guild for freelance work.

    brief: what the client wants in plain words, at least 30 characters. Include a budget like "$800"
    and a deadline if the client has them. Returns milestones, a total and a quote_id. Show these to
    the client before hiring.
    """
    return _call("POST", "/api/v1/quote", {"brief": brief})


@mcp.tool()
def hire_guild(quote_id: str, client_name: str, client_email: str) -> dict:
    """Hire The Guild using a quote from quote_guild_job. Only call this after the client agrees.

    Returns the job and a portal_url. Give the portal_url to the client: they accept the work
    agreement there and pay each milestone through PayPal. Calling this twice with the same
    quote_id returns the same job, so it's safe to retry.
    """
    return _call("POST", "/api/v1/hire",
                 {"quote_id": quote_id, "client_name": client_name, "client_email": client_email})


@mcp.tool()
def check_guild_job(job_id: str) -> dict:
    """See where a job hired through this key is now: worker, agreement, each milestone, and what happens next."""
    return _call("GET", f"/api/v1/jobs/{job_id}")


if __name__ == "__main__":
    mcp.run()
