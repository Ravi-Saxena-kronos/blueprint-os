import json
from datetime import datetime, timezone

from db import audit, get_job, update_job
from llm import LLMUserError, json_call, spend_ok
from schema import Blueprint

CLASSIFY_SYS = (
    "You classify inbound business problems. Return STRICT JSON: "
    '{"problem_type": one of [strategy, ops, gtm, product, finance, other], '
    '"complexity": one of [narrow, full, multi_stakeholder], '
    '"industry": short string, '
    '"reason": one sentence}.'
)

RESEARCH_SYS = (
    "You produce a source list for a business decision. Return STRICT JSON: "
    '{"sources":[{"title":str,"url":str,"retrieved":ISO date,'
    '"excerpt":str,"verified":false}]}. '
    "Prefer authoritative public sources. Do NOT invent URLs you are not "
    "confident exist. It is fine to return fewer than 5 sources."
)

PLAN_SYS = (
    "You are the blueprint planner. Using the brief, classification, and sources, "
    "return STRICT JSON matching the blueprint contract. Fields: "
    "problem_framing{goal,stakeholders[],success_criteria[]}, "
    "assumptions[{id,statement,testable,tied_to_evidence,status}], "
    "options[{name,pros[],cons[],cost_band}] (at least 2), "
    "recommendation{chosen_path,rationale,dissenting_view}, "
    "action_plan[{step,action,owner_role,depends_on[]}], "
    "risks[{description,severity,likelihood,mitigation,residual}], "
    "evidence_pack{sources[],assumption_table[],confidence_per_claim{},falsifiers[]}, "
    "next_steps[]."
)

VERIFY_SYS = (
    "You are a verifier. Check the blueprint for logic gaps, arithmetic errors, "
    "and citation coverage. Return STRICT JSON: "
    '{"coverage_score": 0..1, "flags": [{"section":str,"issue":str}], '
    '"low_confidence_sections": [str]}.'
)


def step_classify(brief: dict) -> tuple[dict, int]:
    return json_call(CLASSIFY_SYS, json.dumps(brief, ensure_ascii=False), max_tokens=400)


def step_research(brief: dict, classification: dict) -> tuple[dict, int]:
    user = json.dumps({"brief": brief, "classification": classification}, ensure_ascii=False)
    return json_call(RESEARCH_SYS, user, max_tokens=1200)


def step_plan(brief: dict, classification: dict, research: dict) -> tuple[dict, int]:
    user = json.dumps(
        {"brief": brief, "classification": classification, "sources": research},
        ensure_ascii=False,
    )
    return json_call(PLAN_SYS, user, max_tokens=3500)


def step_verify(blueprint: dict) -> tuple[dict, int]:
    return json_call(VERIFY_SYS, json.dumps(blueprint, ensure_ascii=False), max_tokens=900)


def run_research_and_draft(job_id: str) -> None:
    job = get_job(job_id)
    if not job:
        return
    brief = job.get("brief") or {}
    total_cost = job.get("model_cost_cents") or 0

    if not spend_ok(total_cost):
        update_job(job_id, status="blocked_budget")
        audit(job_id, actor="orchestrator", step="budget", meta={"total_cost_cents": total_cost})
        return

    try:
        audit(job_id, actor="orchestrator", step="classify", input_ref="brief")
        cls, c1 = step_classify(brief)
        total_cost += c1
        update_job(job_id, classification=cls, model_cost_cents=total_cost, status="researching")
        audit(job_id, actor="classify_agent", step="classify", output_ref="classification", meta={"cost_cents": c1})

        audit(job_id, actor="orchestrator", step="research", input_ref="classification")
        research, c2 = step_research(brief, cls)
        total_cost += c2
        audit(job_id, actor="research_agent", step="research", output_ref="evidence_raw", meta={"cost_cents": c2})

        audit(job_id, actor="orchestrator", step="plan")
        blueprint_raw, c3 = step_plan(brief, cls, research)
        total_cost += c3
        audit(job_id, actor="plan_agent", step="plan", output_ref="blueprint_draft", meta={"cost_cents": c3})

        audit(job_id, actor="orchestrator", step="verify")
        report, c4 = step_verify(blueprint_raw)
        total_cost += c4
        audit(job_id, actor="verifier_agent", step="verify", output_ref="verifier_report", meta={"cost_cents": c4})

        validated = Blueprint(**blueprint_raw).model_dump()
        update_job(
            job_id,
            blueprint=validated,
            verifier_report=report,
            model_cost_cents=total_cost,
            status="review",
        )
        audit(job_id, actor="orchestrator", step="human_review", approval="pending")
        if (job.get("brief") or {}).get("voice_express"):
            run_deliver(job_id)
            audit(job_id, actor="orchestrator", step="voice_express", approval="auto_deliver")
    except LLMUserError as e:
        msg = str(e)
        audit(job_id, actor="orchestrator", step="error", meta={"error": msg[:500]})
        brief_err = {**brief, "last_error": msg}
        update_job(job_id, status="error", brief=brief_err)
    except Exception as e:
        audit(job_id, actor="orchestrator", step="error", meta={"error": str(e)[:500]})
        update_job(job_id, status="error")
        raise


def run_deliver(job_id: str) -> None:
    from render import maybe_upload_blob

    job = get_job(job_id)
    if not job or not job.get("blueprint"):
        return
    blob_url = maybe_upload_blob(job)
    fields = {"status": "delivered", "delivered_at": datetime.now(timezone.utc)}
    if blob_url:
        fields["deliverable_blob_url"] = blob_url
    update_job(job_id, **fields)
    audit(job_id, actor="orchestrator", step="deliver", output_ref=blob_url or "render_on_download", approval="approved")
