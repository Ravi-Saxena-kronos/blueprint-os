import json
import os

from openai import OpenAI

_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
CEILING = int(os.environ.get("MODEL_BUDGET_CEILING_CENTS", "20000"))

IN_PER_1K = 0.015
OUT_PER_1K = 0.060


def spend_ok(already_cents: int) -> bool:
    return already_cents < CEILING


def json_call(system: str, user: str, *, max_tokens: int = 3500) -> tuple[dict, int]:
    r = _client.chat.completions.create(
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
