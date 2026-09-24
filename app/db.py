import os
import uuid
from typing import Any, Optional

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

DB_URL = os.environ["DATABASE_URL"]


def conn():
    return psycopg.connect(DB_URL, row_factory=dict_row)


def new_job(tier: str, email: str, industry: Optional[str], company: Optional[str]) -> str:
    job_id = str(uuid.uuid4())
    with conn() as c, c.cursor() as cur:
        cur.execute(
            "INSERT INTO jobs (id, tier, email, industry, company, status) "
            "VALUES (%s,%s,%s,%s,%s,'queued')",
            (job_id, tier, email, industry, company),
        )
        c.commit()
    return job_id


def get_job(job_id: str) -> Optional[dict]:
    with conn() as c, c.cursor() as cur:
        cur.execute("SELECT * FROM jobs WHERE id=%s", (job_id,))
        return cur.fetchone()


def update_job(job_id: str, **fields: Any) -> None:
    if not fields:
        return
    cols, vals = [], []
    for k, v in fields.items():
        cols.append(f"{k}=%s")
        vals.append(Jsonb(v) if isinstance(v, (dict, list)) else v)
    vals.append(job_id)
    with conn() as c, c.cursor() as cur:
        cur.execute(
            f"UPDATE jobs SET {', '.join(cols)}, updated_at=NOW() WHERE id=%s",
            vals,
        )
        c.commit()


def audit(job_id: str, actor: str, step: str, *,
          input_ref: Optional[str] = None,
          output_ref: Optional[str] = None,
          approval: Optional[str] = None,
          meta: Optional[dict] = None) -> None:
    with conn() as c, c.cursor() as cur:
        cur.execute(
            "INSERT INTO audit_events (job_id, actor, step, input_ref, output_ref, approval, meta) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (job_id, actor, step, input_ref, output_ref, approval, Jsonb(meta or {})),
        )
        c.commit()


def list_review_jobs() -> list[dict]:
    with conn() as c, c.cursor() as cur:
        cur.execute("SELECT * FROM jobs WHERE status='review' ORDER BY created_at ASC")
        return cur.fetchall()


def list_all_jobs(limit: int = 100) -> list[dict]:
    with conn() as c, c.cursor() as cur:
        cur.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT %s", (limit,))
        return cur.fetchall()
