# Enqueue orchestrator work: RQ on Docker, QStash on Vercel.
import os
from typing import Literal

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


def _enqueue_qstash(task: TaskName, job_id: str) -> None:
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
            "Upstash-Forward-Authorization": f"Bearer {secret}" if secret else "",
        }
        r = httpx.post(
            f"https://qstash.upstash.io/v2/publish/{target}",
            headers=headers,
            content=b"{}",
            timeout=30.0,
        )
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
