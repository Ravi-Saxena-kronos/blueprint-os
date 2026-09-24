import json
from typing import Any

from llm import json_call
from refusal import is_refused

ASSIST_SYS = """
You help users start a structured business blueprint intake.
Merge new information into the form. Return STRICT JSON with keys:
assistant_reply (string),
fields (object with email, company, industry, problem, goal, constraints, timeline, geography, budget_band),
ready_to_submit (boolean),
is_general_question (boolean),
voice_ready (boolean).
Only set field values when the user provided or clearly implied them; keep prior values from current_form.
For voice_mode true: do not require email; set voice_ready true when the user question is clear enough to plan (problem or combined question).
For voice_mode false: ready_to_submit true only when email, problem, and goal are non-empty.
For general questions about the service, answer briefly in assistant_reply and set is_general_question true.
"""


def assist_from_message(
    message: str,
    current_form: dict[str, Any],
    *,
    voice_mode: bool = False,
) -> dict[str, Any]:
    from translate import translate_to_english

    message_en, src_lang = translate_to_english(message)
    payload = {
        "message": message_en,
        "original_message": message,
        "source_language": src_lang,
        "current_form": current_form,
        "voice_mode": voice_mode,
    }
    out, _cost = json_call(ASSIST_SYS, json.dumps(payload, ensure_ascii=False), max_tokens=1000)
    fields = out.get("fields") or {}
    merged = {**current_form, **{k: (v or "") for k, v in fields.items() if v is not None}}
    problem = (merged.get("problem") or "") + " " + (merged.get("goal") or "") + " " + message_en
    refused, reason = is_refused(problem)
    if voice_mode:
        ready = bool(out.get("voice_ready")) and not refused
        if not ready and message_en.strip() and not refused:
            merged.setdefault("problem", message_en.strip())
            merged.setdefault("goal", "Produce a decision-grade blueprint that answers the question.")
            ready = True
    else:
        ready = bool(out.get("ready_to_submit")) and not refused
    if refused:
        ready = False
    reply = out.get("assistant_reply") or "Tell me about your business problem and goal."
    if src_lang and src_lang != "en" and message_en != message:
        reply = f"(Translated to English) {reply}"
    return {
        "assistant_reply": reply,
        "fields": merged,
        "ready_to_submit": ready,
        "voice_ready": ready if voice_mode else False,
        "refused": refused,
        "refusal_reason": reason,
        "is_general_question": bool(out.get("is_general_question")),
        "english_message": message_en,
        "original_message": message,
    }


def brief_from_voice_question(
    message: str,
    *,
    original: str | None = None,
    source_lang: str | None = None,
    already_english: bool = False,
) -> dict[str, Any]:
    from translate import translate_to_english

    raw = (message or "").strip()
    if already_english:
        text_en = raw
        lang = source_lang or "en"
        orig = original or raw
    else:
        text_en, lang = translate_to_english(raw)
        orig = original or raw
    return {
        "problem": text_en,
        "goal": "Deliver a structured blueprint that answers the user's question with options and an action plan.",
        "constraints": "",
        "timeline": "",
        "geography": "",
        "budget_band": "",
        "voice_express": True,
        "original_question": orig,
        "source_language": lang,
    }
