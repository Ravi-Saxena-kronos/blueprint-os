# Enqueue orchestrator work: RQ on Docker, QStash on Vercel.
import os
from typing import Literal
from urllib.parse import quote

import httpx

TaskName = Literal["run_research_and_draft", "run_deliver"]


def _is_vercel() -> bool:
    return os.environ.get("DEPLOY_TARGET") == "vercel" or bool(os.environ.get("VERCEL"))


def enqueue(task: TaskName, job_id: str) -> None:
    if _is_vercel():
        _enqueue_qstash(task, job_id)
        return
    _enqueue_rq(task, job_id)


def _enqueue_rq(task: TaskName, job_id: str) -> None:
    import redis
    from rq import Queue

    redis_url = os.environ.get("REDIS_URL", "redis://redis:6379")
    q = Queue("jobs", connection=redis.from_url(redis_url))
    timeout = "15m" if task == "run_research_and_draft" else "5m"
    q.enqueue(f"orchestrator.{task}", job_id, job_timeout=timeout)


def _qstash_disabled() -> bool:
    return os.environ.get("QSTASH_DISABLED", "").strip().lower() in ("1", "true", "yes")


def _enqueue_qstash(task: TaskName, job_id: str) -> None:
    if _qstash_disabled():
        raise RuntimeError(
            "QStash disabled (QSTASH_DISABLED=1). Job will run via inline orchestrator on the status page."
        )

    token = os.environ.get("QSTASH_TOKEN", "").strip()
    app_url = os.environ.get("APP_URL", "").rstrip("/")
    if not app_url:
        raise RuntimeError("APP_URL is required for Vercel background jobs")

    target = f"{app_url}/internal/jobs/{task}/{job_id}"
    secret = os.environ.get("INTERNAL_JOB_SECRET", "").strip()

    if token:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        if secret:
            headers["Upstash-Forward-Authorization"] = f"Bearer {secret}"
        base = os.environ.get("QSTASH_URL", "https://qstash.upstash.io").rstrip("/")
        # Destination URL must be encoded in the publish path (required on some QStash regions).
        publish_url = f"{base}/v2/publish/{quote(target, safe='')}"
        r = httpx.post(
            publish_url,
            headers=headers,
            content=b"{}",
            timeout=30.0,
        )
        if r.status_code in (401, 403):
            hint = (
                "QStash rejected the token (403/401). In Upstash Console open QStash (same region as "
                "QSTASH_URL), copy the QSTASH_TOKEN (not Redis password). Or set QSTASH_DISABLED=1 to "
                "run blueprints inline without QStash."
            )
            raise RuntimeError(f"{r.status_code} Forbidden — {hint} Body: {r.text[:200]}")
        r.raise_for_status()
        return

    if not secret:
        raise RuntimeError(
            "On Vercel set QSTASH_TOKEN (recommended) or INTERNAL_JOB_SECRET for dev-only inline calls"
        )
    r = httpx.post(
        target,
        headers={"Authorization": f"Bearer {secret}"},
        json={},
        timeout=300.0,
    )
    r.raise_for_status()
