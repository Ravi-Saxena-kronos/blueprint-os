"""Ensure paid/queued jobs actually start (QStash retry + optional inline fallback)."""

from __future__ import annotations

import os

from db import (
    audit,
    count_enqueue_attempts,
    get_job,
    orchestrator_started,
    try_claim_job,
    update_job,
)
from job_queue import enqueue


def _inline_allowed() -> bool:
    return os.environ.get("INLINE_ORCHESTRATOR", "1").strip() not in ("0", "false", "no")


def kick_enqueue(job_id: str) -> str | None:
    """Publish background work to QStash. Returns error message or None on success."""
    try:
        enqueue("run_research_and_draft", job_id)
        audit(job_id, actor="system", step="enqueue", approval="published")
        return None
    except Exception as exc:
        msg = str(exc)[:400]
        audit(job_id, actor="system", step="enqueue", meta={"error": msg})
        return msg


def _run_inline(job_id: str) -> None:
    job = get_job(job_id) or {}
    brief = job.get("brief") or {}
    import orchestrator

    try:
        orchestrator.run_research_and_draft(job_id)
    except Exception as exc:
        if get_job(job_id) and get_job(job_id)["status"] not in ("error", "delivered"):
            update_job(
                job_id,
                status="error",
                brief={**brief, "last_error": str(exc)[:500]},
            )
        raise


def ensure_job_running(job_id: str, *, allow_inline: bool = True) -> None:
    """
    Called from the status page when a job looks stuck on paid/queued/processing.
    Retries QStash; optionally runs the orchestrator in-process if the worker never started.
    """
    job = get_job(job_id)
    if not job:
        return
    status = job["status"]
    if status not in ("paid", "queued", "processing"):
        return
    if orchestrator_started(job_id):
        return
    if status == "processing":
        return

    attempts = count_enqueue_attempts(job_id)
    err: str | None = None
    if attempts < 4:
        err = kick_enqueue(job_id)
        if orchestrator_started(job_id):
            return

    if not allow_inline or not _inline_allowed():
        if err and allow_inline:
            brief = job.get("brief") or {}
            update_job(
                job_id,
                status="error",
                brief={
                    **brief,
                    "last_error": (
                        f"Background worker did not start: {err}. "
                        "Set QSTASH_TOKEN, APP_URL=https://blueprint-os-xi.vercel.app, "
                        "INTERNAL_JOB_SECRET, and GROQ_API_KEY on Vercel."
                    ),
                },
            )
        return

    if try_claim_job(job_id):
        _run_inline(job_id)
