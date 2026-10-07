import json
import logging
import re

import httpx
from pydantic import BaseModel, ValidationError

from app.config import settings

logger = logging.getLogger(__name__)


class AIError(Exception):
    """The AI call failed or returned something unusable."""


def _extract_json(text: str) -> str:
    """Strip markdown fences and any chatter around the JSON object."""
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    start, end = t.find("{"), t.rfind("}")
    if start != -1 and end > start:
        t = t[start:end + 1]
    return t.strip()


def run_ai(messages: list[dict], temperature: float = 0.2, max_tokens: int = 800) -> str:
    url = (
        f"https://api.cloudflare.com/client/v4/accounts/"
        f"{settings.cloudflare_account_id}/ai/run/{settings.cloudflare_ai_model}"
    )
    r = httpx.post(
        url,
        headers={"Authorization": f"Bearer {settings.cloudflare_api_token}"},
        json={"messages": messages, "temperature": temperature, "max_tokens": max_tokens},
        timeout=90,
    )
    r.raise_for_status()
    data = r.json()
    if not data.get("success", False):
        raise RuntimeError(f"Workers AI error: {data.get('errors')}")
    response = data["result"]["response"]
    if isinstance(response, (dict, list)):
        return json.dumps(response)
    return response


def run_ai_json(messages: list[dict], schema: type[BaseModel], temperature: float = 0.1,
                max_tokens: int = 800):
    """Call the model and validate against a Pydantic schema. Retries once."""
    try:
        raw = run_ai(messages, temperature, max_tokens)
        try:
            return schema.model_validate_json(_extract_json(raw))
        except ValidationError as e:
            logger.warning("AI JSON invalid, retrying: %s", e)
            retry = list(messages) + [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": (
                    f"That was not valid JSON for the required shape. Error: {e}. "
                    "Return ONLY the JSON object. No markdown, no extra text."
                )},
            ]
            raw2 = run_ai(retry, 0.0, max_tokens)
            return schema.model_validate_json(_extract_json(raw2))
    except (httpx.HTTPError, RuntimeError, ValidationError) as e:
        raise AIError(str(e)) from e