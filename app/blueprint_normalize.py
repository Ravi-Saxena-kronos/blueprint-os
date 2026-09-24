"""Coerce LLM JSON into the Blueprint schema before Pydantic validation."""

from __future__ import annotations

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
    return str(value).strip() or default


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
                "tied_to_evidence": a.get("tied_to_evidence"),
                "status": _as_str(a.get("status"), "unknown"),
            }
        )
    if out:
        return out
    return fallback or [{"id": 1, "statement": "Client context as stated in the brief", "status": "unknown"}]


def normalize_blueprint_raw(raw: dict | None) -> dict:
    d = deepcopy(raw) if isinstance(raw, dict) else {}

    pf = d.get("problem_framing") if isinstance(d.get("problem_framing"), dict) else {}
    d["problem_framing"] = {
        "goal": _as_str(pf.get("goal") or d.get("goal"), "Answer the client question with a clear plan."),
        "stakeholders": [_as_str(x) for x in _as_list(pf.get("stakeholders")) if _as_str(x)],
        "success_criteria": [_as_str(x) for x in _as_list(pf.get("success_criteria")) if _as_str(x)]
        or ["Actionable recommendation documented"],
    }

    d["assumptions"] = _normalize_assumptions(d.get("assumptions"))

    options: list[dict] = []
    for o in _as_list(d.get("options")):
        if not isinstance(o, dict):
            continue
        options.append(
            {
                "name": _as_str(o.get("name"), "Option"),
                "pros": [_as_str(x) for x in _as_list(o.get("pros")) if _as_str(x)],
                "cons": [_as_str(x) for x in _as_list(o.get("cons")) if _as_str(x)],
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
        "dissenting_view": rec.get("dissenting_view"),
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
                "url": s.get("url"),
                "retrieved": _as_str(s.get("retrieved"), "2026-01-01"),
                "excerpt": _as_str(s.get("excerpt"), ""),
                "verified": bool(s.get("verified", False)),
            }
        )
    d["evidence_pack"] = {
        "sources": sources,
        "assumption_table": _normalize_assumptions(ep.get("assumption_table"), fallback=d["assumptions"]),
        "confidence_per_claim": conf,
        "falsifiers": [_as_str(x) for x in _as_list(ep.get("falsifiers")) if _as_str(x)],
    }

    d["next_steps"] = [_as_str(x) for x in _as_list(d.get("next_steps")) if _as_str(x)] or [
        "Download DOCX and share with stakeholders",
        "Validate top assumptions within 2 weeks",
    ]

    return d


def blueprint_to_validated(raw: dict | None) -> dict:
    """Normalize and validate; fall back to coerced assumption_table if needed."""
    from pydantic import ValidationError

    from schema import Blueprint

    normed = normalize_blueprint_raw(raw)
    try:
        return Blueprint(**normed).model_dump()
    except ValidationError:
        ep = dict(normed.get("evidence_pack") or {})
        ep["assumption_table"] = normed.get("assumptions") or []
        normed["evidence_pack"] = ep
        return Blueprint(**normalize_blueprint_raw(normed)).model_dump()
