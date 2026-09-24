import json
from typing import Any

from llm import json_call
from refusal import is_refused

ASSIST_SYS = (
    "You help users start a structured business blueprint intake. "
    "Merge new information into the form. Return STRICT JSON: "
    '{"assistant_reply": str, "fields": {'
    '"email":"","company":"","industry":"","problem":"","goal":"",'
    '"constraints":"","timeline":"","geography":"","budget_band":""'
    "}, "
    '"ready_to_submit": bool, "is_general_question": bool}. "
    "Only set field values when the user provided or clearly implied them; keep prior values from current_form. "
    "ready_to_submit is true only when email, problem, and goal are non-empty. "
    "For general questions about the service, answer briefly in assistant_reply and set is_general_question true."
)


def assist_from_message(message: str, current_form: dict[str, Any]) -> dict[str, Any]:
    payload = {"message": message, "current_form": current_form}
    out, _cost = json_call(ASSIST_SYS, json.dumps(payload, ensure_ascii=False), max_tokens=1000)
    fields = out.get("fields") or {}
    merged = {**current_form, **{k: (v or "") for k, v in fields.items() if v is not None}}
    problem = (merged.get("problem") or "") + " " + (merged.get("goal") or "")
    refused, reason = is_refused(problem)
    ready = bool(out.get("ready_to_submit")) and not refused
    if refused:
        ready = False
    return {
        "assistant_reply": out.get("assistant_reply") or "Tell me about your business problem and goal.",
        "fields": merged,
        "ready_to_submit": ready,
        "refused": refused,
        "refusal_reason": reason,
        "is_general_question": bool(out.get("is_general_question")),
    }
