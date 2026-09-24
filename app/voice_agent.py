from __future__ import annotations

from typing import Any, Optional

STEPS = [
    ("email", "What email should we use for updates and your blueprint link?"),
    ("problem", "In one or two sentences, what problem are you facing today?"),
    ("goal", "What outcome would count as done for you?"),
    ("constraints", "Any constraints we should know? Say skip if none."),
    ("timeline", "What timeline are you working with? Say skip if flexible."),
    ("geography", "Which geography or market? Say skip if not applicable."),
    ("budget_band", "Rough budget band? Say skip if unknown."),
]

SKIP_WORDS = {"skip", "none", "na", "n/a", "no", "nothing"}


def new_session(tier: str = "standard") -> dict[str, Any]:
    return {"tier": tier, "step": 0, "data": {}}


def _norm_skip(text: str) -> str:
    t = (text or "").strip()
    if t.lower() in SKIP_WORDS:
        return ""
    return t


def process_turn(session: dict[str, Any], user_text: str) -> tuple[dict[str, Any], str, bool]:
    """Returns (updated_session, agent_reply, ready_to_submit)."""
    text = (user_text or "").strip()
    if not text:
        return session, "I didn't catch that. Please try again.", False

    idx = int(session.get("step", 0))
    if idx >= len(STEPS):
        return session, "Ready to submit. Tap Submit blueprint.", True

    field, _prompt = STEPS[idx]
    if field == "email" and "@" not in text:
        return session, "Please say or type a valid email address.", False

    session.setdefault("data", {})
    session["data"][field] = _norm_skip(text) if field not in ("email", "problem", "goal") else text.strip()
    session["step"] = idx + 1

    if session["step"] >= len(STEPS):
        return session, "Thanks. I have everything. Tap Submit blueprint to start your plan.", True

    _, next_prompt = STEPS[session["step"]]
    return session, next_prompt, False


def session_to_intake(session: dict[str, Any]) -> Optional[dict[str, str]]:
    d = session.get("data") or {}
    email = d.get("email", "").strip()
    problem = d.get("problem", "").strip()
    goal = d.get("goal", "").strip()
    if not email or not problem or not goal:
        return None
    return {
        "tier": session.get("tier") or "standard",
        "email": email,
        "company": "",
        "industry": "",
        "problem": problem,
        "goal": goal,
        "constraints": d.get("constraints", ""),
        "timeline": d.get("timeline", ""),
        "geography": d.get("geography", ""),
        "budget_band": d.get("budget_band", ""),
    }


def welcome_message() -> str:
    field, prompt = STEPS[0]
    return f"Hi, I'm your blueprint intake assistant. {prompt}"
