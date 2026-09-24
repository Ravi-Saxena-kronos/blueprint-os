"""Translate user input to English before blueprint processing."""

from __future__ import annotations

import re


def _looks_english(text: str) -> bool:
    if not text.strip():
        return True
    ascii_ratio = sum(1 for c in text if ord(c) < 128) / max(len(text), 1)
    return ascii_ratio > 0.85 and not re.search(r"[\u0900-\u097F\u4e00-\u9fff\u0600-\u06FF]", text)


def translate_to_english(text: str) -> tuple[str, str | None]:
    """
    Returns (english_text, detected_source_lang).
    Uses deep-translator (Google) — no extra API key.
    """
    raw = (text or "").strip()
    if not raw:
        return raw, None
    if _looks_english(raw):
        return raw, "en"

    try:
        from deep_translator import GoogleTranslator

        translated = GoogleTranslator(source="auto", target="en").translate(raw)
        if not translated:
            return raw, None
        return translated.strip(), "auto"
    except Exception:
        return raw, None
