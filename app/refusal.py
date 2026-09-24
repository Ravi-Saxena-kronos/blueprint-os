REFUSAL_KEYWORDS = [
    "diagnose my", "medical advice", "treat my",
    "legal advice", "sue ", "lawsuit against",
    "individualized tax", "personal tax advice",
    "guaranteed revenue", "guaranteed return",
    "prescribe", "clinical trial for",
]


def is_refused(text: str) -> tuple[bool, str]:
    t = (text or "").lower()
    for kw in REFUSAL_KEYWORDS:
        if kw in t:
            return True, f"Refusal list trigger: '{kw.strip()}'"
    return False, ""
