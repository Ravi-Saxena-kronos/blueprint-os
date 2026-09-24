"""JSON chat completions — OpenAI or free-tier OpenAI-compatible providers (Groq, Gemini, OpenRouter)."""

from __future__ import annotations

import json
import os
import re

from openai import APIStatusError, OpenAI, RateLimitError

CEILING = int(os.environ.get("MODEL_BUDGET_CEILING_CENTS", "20000"))

# Rough $/1K tokens for budget tracking (free providers → ~0)
_COST = {
    "openai": (0.015, 0.060),
    "groq": (0.0, 0.0),
    "gemini": (0.0, 0.0),
    "openrouter": (0.0, 0.0),
}

_PROVIDERS: dict[str, dict[str, str | None]] = {
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "key_env": "GROQ_API_KEY",
        # Llama 3.3 IDs were removed from free/dev tier Aug 2026 — see Groq deprecations doc.
        "default_model": "openai/gpt-oss-20b",
        "fallback_models": "openai/gpt-oss-120b,qwen/qwen3.8-27b,allam-2-7b",
        "signup": "https://console.groq.com/keys (free tier)",
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "key_env": "GEMINI_API_KEY",
        "default_model": "gemini-2.0-flash",
        "signup": "https://aistudio.google.com/apikey (free tier)",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "key_env": "OPENROUTER_API_KEY",
        "default_model": "meta-llama/llama-3.3-70b-instruct:free",
        "signup": "https://openrouter.ai/keys (includes free models)",
    },
    "openai": {
        "base_url": None,
        "key_env": "OPENAI_API_KEY",
        "default_model": "gpt-4o-mini",
        "signup": "https://platform.openai.com (paid credits)",
    },
}

_client: OpenAI | None = None
_active_provider: str | None = None
_resolved_model: str | None = None


class LLMUserError(RuntimeError):
    """LLM errors with a short user-facing message."""


OpenAIUserError = LLMUserError  # backward compatible imports


def active_provider() -> str | None:
    _ensure_client()
    return _active_provider


def llm_configured() -> bool:
    if os.environ.get("LLM_PROVIDER", "").strip():
        name = os.environ["LLM_PROVIDER"].strip().lower()
        return bool(os.environ.get(_PROVIDERS[name]["key_env"], "").strip())
    for name in ("groq", "gemini", "openrouter", "openai"):
        if os.environ.get(_PROVIDERS[name]["key_env"], "").strip():
            return True
    return False


def _resolve_provider() -> str:
    explicit = os.environ.get("LLM_PROVIDER", "").strip().lower()
    if explicit:
        if explicit not in _PROVIDERS:
            raise LLMUserError(f"Unknown LLM_PROVIDER={explicit}. Use groq, gemini, openrouter, or openai.")
        return explicit
    for name in ("groq", "gemini", "openrouter", "openai"):
        if os.environ.get(_PROVIDERS[name]["key_env"], "").strip():
            return name
    hints = "; ".join(f"{n}: set {_PROVIDERS[n]['key_env']}" for n in ("groq", "gemini", "openrouter"))
    raise LLMUserError(
        f"No LLM API key configured. Free options — {hints}. "
        f"Groq is recommended: {_PROVIDERS['groq']['signup']}"
    )


def _model_for(provider: str) -> str:
    """LLM_MODEL applies to all providers; OPENAI_MODEL only when LLM_PROVIDER=openai."""
    global _resolved_model
    if _resolved_model:
        return _resolved_model
    custom = os.environ.get("LLM_MODEL", "").strip()
    if custom:
        return custom
    if provider == "openai":
        return os.environ.get("OPENAI_MODEL", "").strip() or str(_PROVIDERS["openai"]["default_model"])
    return str(_PROVIDERS[provider]["default_model"])


def _model_candidates(provider: str) -> list[str]:
    primary = _model_for(provider)
    out = [primary]
    if os.environ.get("LLM_MODEL", "").strip():
        return out
    extra = (_PROVIDERS.get(provider) or {}).get("fallback_models") or ""
    for mid in str(extra).split(","):
        mid = mid.strip()
        if mid and mid not in out:
            out.append(mid)
    return out


def _remember_model(model: str) -> None:
    global _resolved_model
    _resolved_model = model


def _ensure_client() -> tuple[OpenAI, str, str]:
    global _client, _active_provider
    if _client is not None and _active_provider:
        return _client, _active_provider, _model_for(_active_provider)

    provider = _resolve_provider()
    meta = _PROVIDERS[provider]
    key = os.environ.get(str(meta["key_env"]), "").strip()
    if not key:
        raise LLMUserError(
            f"Set {meta['key_env']} in Vercel (or LLM_PROVIDER={provider}). {meta.get('signup', '')}"
        )

    kwargs: dict = {"api_key": key}
    if meta["base_url"]:
        kwargs["base_url"] = meta["base_url"]
    if provider == "openrouter":
        kwargs["default_headers"] = {
            "HTTP-Referer": os.environ.get("APP_URL", "https://blueprint-os.local"),
            "X-Title": "Blueprint OS",
        }

    _client = OpenAI(**kwargs)
    _active_provider = provider
    return _client, provider, _model_for(provider)


def spend_ok(already_cents: int) -> bool:
    return already_cents < CEILING


def _parse_json(text: str) -> dict:
    raw = (text or "").strip()
    if not raw:
        return {}
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```\s*$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start >= 0 and end > start:
            return json.loads(raw[start : end + 1])
        raise


def _wrap_err(exc: Exception, provider: str) -> LLMUserError:
    if isinstance(exc, RateLimitError):
        return LLMUserError(
            f"{provider} rate limit reached. Wait a minute or switch LLM_PROVIDER / API key."
        )
    if isinstance(exc, APIStatusError):
        if exc.status_code == 429:
            return LLMUserError(f"{provider} quota/rate limit (429). Try again later or use another provider.")
        if exc.status_code == 401:
            env = _PROVIDERS.get(provider, {}).get("key_env", "API key")
            return LLMUserError(f"Invalid {env}. Check Vercel environment variables.")
        if exc.status_code == 404 and "model" in str(exc).lower():
            return LLMUserError(
                f"{provider} model not found. Set LLM_MODEL to a current model ID from "
                f"https://console.groq.com/docs/models (e.g. openai/gpt-oss-20b)."
            )
    return LLMUserError(f"{provider} error: {str(exc)[:220]}")


def _is_model_not_found(exc: Exception) -> bool:
    if isinstance(exc, APIStatusError) and exc.status_code == 404:
        return True
    s = str(exc).lower()
    return "model_not_found" in s or ("404" in s and "model" in s)


def json_call(system: str, user: str, *, max_tokens: int = 3500) -> tuple[dict, int]:
    client, provider, _ = _ensure_client()
    system_full = system.strip() + "\n\nReturn one JSON object only. No markdown fences or commentary."

    messages = [
        {"role": "system", "content": system_full},
        {"role": "user", "content": user},
    ]

    last_exc: Exception | None = None
    for model in _model_candidates(provider):
        for use_json_mode in (True, False):
            try:
                kwargs: dict = {
                    "model": model,
                    "messages": messages,
                    "temperature": 0.2,
                    "max_tokens": max_tokens,
                }
                if use_json_mode:
                    kwargs["response_format"] = {"type": "json_object"}
                r = client.chat.completions.create(**kwargs)
                text = r.choices[0].message.content or "{}"
                usage = r.usage
                in_per, out_per = _COST.get(provider, (0.0, 0.0))
                cost = (usage.prompt_tokens / 1000) * in_per + (usage.completion_tokens / 1000) * out_per
                _remember_model(model)
                return _parse_json(text), int(round(cost))
            except json.JSONDecodeError as exc:
                raise LLMUserError("Model returned invalid JSON. Retry or switch LLM_MODEL.") from exc
            except Exception as exc:
                last_exc = exc
                if _is_model_not_found(exc):
                    break  # try next model candidate
                if use_json_mode:
                    continue
                raise _wrap_err(exc, provider) from exc

    if last_exc:
        raise _wrap_err(last_exc, provider) from last_exc
    raise LLMUserError("LLM call failed.")
