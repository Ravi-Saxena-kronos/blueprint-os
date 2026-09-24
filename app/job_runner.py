"""Ensure paid/queued jobs actually start (QStash retry + optional inline fallback)."""

from __future__ import annotations

import os

from db import (
    count_enqueue_attempts,
    get_job,
    last_enqueue_error,
    orchestrator_started,
    try_claim_job,
    update_job,
)
from job_queue import enqueue, _qstash_disabled


def _inline_allowed() -> bool:
    return os.environ.get("INLINE_ORCHESTRATOR", "1").strip() not in ("0", "false", "no")


def _qstash_auth_failed(msg: str | None) -> bool:
    if not msg:
        return False
    m = msg.lower()
    return any(x in m for x in ("403", "401", "forbidden", "rejected the token", "qstash disabled"))


def kick_enqueue(job_id: str) -> str | None:
    """Publish background work to QStash. Returns error message or None on success."""
    from db import audit

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
        msg = str(exc)[:500]
        j = get_job(job_id)
        if j and j["status"] != "delivered":
            b = j.get("brief") or brief
            if not (b.get("last_error")):
                update_job(job_id, status="error", brief={**b, "last_error": msg})
        raise


def ensure_job_running(job_id: str, *, allow_inline: bool = True) -> None:
    """
    Retries QStash when useful; runs the orchestrator in-process when QStash fails or is disabled.
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

    prev_err = last_enqueue_error(job_id)
    skip_qstash = _qstash_disabled() or _qstash_auth_failed(prev_err)

    err: str | None = prev_err
    if not skip_qstash and count_enqueue_attempts(job_id) < 2:
        err = kick_enqueue(job_id)
        if _qstash_auth_failed(err):
            skip_qstash = True
        if orchestrator_started(job_id):
            return

    if not allow_inline or not _inline_allowed():
        return

    if try_claim_job(job_id):
        _run_inline(job_id)
