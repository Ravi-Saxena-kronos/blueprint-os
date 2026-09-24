import json
import os

from openai import OpenAI

_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
CEILING = int(os.environ.get("MODEL_BUDGET_CEILING_CENTS", "20000"))

IN_PER_1K = 0.015
OUT_PER_1K = 0.060

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        _client = OpenAI(api_key=key)
    return _client


def spend_ok(already_cents: int) -> bool:
    return already_cents < CEILING


def json_call(system: str, user: str, *, max_tokens: int = 3500) -> tuple[dict, int]:
    client = _get_client()
    r = client.chat.completions.create(
        model=_MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
        max_tokens=max_tokens,
    )
    text = r.choices[0].message.content or "{}"
    usage = r.usage
    cost = (usage.prompt_tokens / 1000) * IN_PER_1K + (usage.completion_tokens / 1000) * OUT_PER_1K
    return json.loads(text), int(round(cost))
