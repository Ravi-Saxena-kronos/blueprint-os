"""Coerce LLM JSON into the Blueprint schema before Pydantic validation."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any


def _as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _as_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip() or default
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, dict):
        for key in ("text", "name", "value", "description", "goal", "title", "label"):
            if value.get(key) is not None:
                return _as_str(value[key], default)
        try:
            return json.dumps(value, ensure_ascii=False)[:2000]
        except (TypeError, ValueError):
            return default
    if isinstance(value, list):
        parts = [_as_str(x, "") for x in value]
        parts = [p for p in parts if p]
        return "; ".join(parts) if parts else default
    s = str(value).strip()
    return s or default


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    s = _as_str(value, "")
    return s if s else None


def _str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [p for p in (_as_str(x) for x in re.split(r"[,;\n]+", value)) if p]
    if isinstance(value, dict):
        out: list[str] = []
        for v in value.values():
            out.extend(_str_list(v))
        return out
    out: list[str] = []
    for item in _as_list(value):
        if isinstance(item, dict):
            out.append(_as_str(item))
        else:
            s = _as_str(item, "")
            if s:
                out.append(s)
    return out


def _as_int(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        s = value.strip()
        if s.isdigit():
            return int(s)
        m = re.search(r"\d+", s)
        if m:
            return int(m.group())
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_assumptions(items: Any, *, fallback: list[dict] | None = None) -> list[dict]:
    out: list[dict] = []
    for i, a in enumerate(_as_list(items)):
        if not isinstance(a, dict):
            continue
        out.append(
            {
                "id": _as_int(a.get("id"), i + 1),
                "statement": _as_str(a.get("statement"), "Assumption pending review"),
                "testable": bool(a.get("testable", True)),
                "tied_to_evidence": _optional_str(a.get("tied_to_evidence")),
                "status": _as_str(a.get("status"), "unknown"),
            }
        )
    if out:
        return out
    return fallback or [{"id": 1, "statement": "Client context as stated in the brief", "status": "unknown"}]


def normalize_blueprint_raw(raw: dict | None) -> dict:
    d = deepcopy(raw) if isinstance(raw, dict) else {}

    pf_raw = d.get("problem_framing")
    pf = pf_raw if isinstance(pf_raw, dict) else {}
    d["problem_framing"] = {
        "goal": _as_str(pf.get("goal") or d.get("goal") or pf_raw, "Answer the client question with a clear plan."),
        "stakeholders": _str_list(pf.get("stakeholders")) or ["Client"],
        "success_criteria": _str_list(pf.get("success_criteria")) or ["Actionable recommendation documented"],
    }

    d["assumptions"] = _normalize_assumptions(d.get("assumptions"))

    options: list[dict] = []
    for o in _as_list(d.get("options")):
        if not isinstance(o, dict):
            continue
        options.append(
            {
                "name": _as_str(o.get("name"), "Option"),
                "pros": _str_list(o.get("pros")) or ["See rationale"],
                "cons": _str_list(o.get("cons")) or ["See risks section"],
                "cost_band": _as_str(o.get("cost_band"), "TBD"),
            }
        )
    while len(options) < 2:
        options.append(
            {
                "name": f"Option {len(options) + 1}",
                "pros": ["To be refined with client input"],
                "cons": ["Requires validation"],
                "cost_band": "TBD",
            }
        )
    d["options"] = options[:5]

    rec = d.get("recommendation") if isinstance(d.get("recommendation"), dict) else {}
    d["recommendation"] = {
        "chosen_path": _as_str(rec.get("chosen_path") or rec.get("path"), options[0]["name"]),
        "rationale": _as_str(rec.get("rationale"), "Based on brief and available evidence."),
        "dissenting_view": _optional_str(rec.get("dissenting_view")),
    }

    action_plan: list[dict] = []
    for i, s in enumerate(_as_list(d.get("action_plan"))):
        if not isinstance(s, dict):
            continue
        deps = []
        for x in _as_list(s.get("depends_on")):
            deps.append(_as_int(x, 0))
        deps = [x for x in deps if x > 0]
        action_plan.append(
            {
                "step": _as_int(s.get("step"), i + 1),
                "action": _as_str(s.get("action"), "Define next action"),
                "owner_role": _as_str(s.get("owner_role"), "Owner"),
                "depends_on": deps,
            }
        )
    if not action_plan:
        action_plan = [{"step": 1, "action": "Review blueprint and confirm priorities", "owner_role": "Client", "depends_on": []}]
    d["action_plan"] = action_plan

    risks: list[dict] = []
    for r in _as_list(d.get("risks")):
        if not isinstance(r, dict):
            continue
        risks.append(
            {
                "description": _as_str(r.get("description"), "Execution risk"),
                "severity": _as_str(r.get("severity"), "medium"),
                "likelihood": _as_str(r.get("likelihood"), "medium"),
                "mitigation": _as_str(r.get("mitigation"), "Monitor and adjust"),
                "residual": _as_str(r.get("residual"), "Some uncertainty remains"),
            }
        )
    if not risks:
        risks = [
            {
                "description": "Market and data uncertainty",
                "severity": "medium",
                "likelihood": "medium",
                "mitigation": "Validate assumptions with primary research",
                "residual": "Residual uncertainty",
            }
        ]
    d["risks"] = risks

    ep = d.get("evidence_pack") if isinstance(d.get("evidence_pack"), dict) else {}
    conf = ep.get("confidence_per_claim") or {}
    if isinstance(conf, dict):
        parsed: dict[str, float] = {}
        for k, v in conf.items():
            try:
                parsed[str(k)] = float(v)
            except (TypeError, ValueError):
                parsed[str(k)] = 0.5
        conf = parsed
    else:
        conf = {}
    sources = []
    for s in _as_list(ep.get("sources")):
        if not isinstance(s, dict):
            continue
        sources.append(
            {
                "title": _as_str(s.get("title"), "Source"),
                "url": _optional_str(s.get("url")),
                "retrieved": _as_str(s.get("retrieved"), "2026-01-01"),
                "excerpt": _as_str(s.get("excerpt"), ""),
                "verified": bool(s.get("verified", False)),
            }
        )
    d["evidence_pack"] = {
        "sources": sources,
        "assumption_table": _normalize_assumptions(ep.get("assumption_table"), fallback=d["assumptions"]),
        "confidence_per_claim": conf,
        "falsifiers": _str_list(ep.get("falsifiers")),
    }

    d["next_steps"] = _str_list(d.get("next_steps")) or [
        "Download DOCX and share with stakeholders",
        "Validate top assumptions within 2 weeks",
    ]

    return d


def blueprint_to_validated(raw: dict | None) -> dict:
    """Normalize and validate with retries for common LLM type mistakes."""
    from pydantic import ValidationError

    from schema import Blueprint

    normed = normalize_blueprint_raw(raw)
    last_err: ValidationError | None = None
    for attempt in range(3):
        try:
            return Blueprint(**normed).model_dump()
        except ValidationError as ve:
            last_err = ve
            ep = dict(normed.get("evidence_pack") or {})
            ep["assumption_table"] = normed.get("assumptions") or []
            normed["evidence_pack"] = ep
            normed = normalize_blueprint_raw(normed)
            if attempt == 1:
                # Drop optional fields that often arrive as wrong types.
                rec = normed.get("recommendation") or {}
                rec["dissenting_view"] = _optional_str(rec.get("dissenting_view"))
                normed["recommendation"] = rec
    assert last_err is not None
    raise last_err
