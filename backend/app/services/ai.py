# The Guild\backend\app\services\ai.py
import json

import httpx

from app.config import settings


def run_ai(messages: list[dict], temperature: float = 0.2, max_tokens: int = 600) -> str:
    url = (
        f"https://api.cloudflare.com/client/v4/accounts/"
        f"{settings.cloudflare_account_id}/ai/run/{settings.cloudflare_ai_model}"
    )
    headers = {"Authorization": f"Bearer {settings.cloudflare_api_token}"}
    payload = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    r = httpx.post(url, headers=headers, json=payload, timeout=60)
    r.raise_for_status()
    data = r.json()
    if not data.get("success", False):
        raise RuntimeError(f"Workers AI error: {data}")
    response = data["result"]["response"]
    if isinstance(response, (dict, list)):
        return json.dumps(response)
    return response