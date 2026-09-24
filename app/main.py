import hmac
import os
import sys
from pathlib import Path
from typing import Optional

# Vercel loads this file as app.main; keep sibling imports working.
_APP_ROOT = Path(__file__).resolve().parent
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

import stripe
from dotenv import load_dotenv
from fastapi import Cookie, FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, URLSafeTimedSerializer

from db import audit, get_job, list_all_jobs, list_review_jobs, new_job, update_job
from internal_auth import verify_internal_request
from job_queue import enqueue
from refusal import is_refused
from render import OUTPUT_DIR, docx_bytes

load_dotenv()

APP_URL = os.environ.get("APP_URL", "http://localhost:8000")
REVIEW_PASSWORD = os.environ.get("REVIEW_PASSWORD", "change-me")
STRIPE_SECRET = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICES = {
    "express": os.environ.get("STRIPE_PRICE_EXPRESS", ""),
    "standard": os.environ.get("STRIPE_PRICE_STANDARD", ""),
    "premium": os.environ.get("STRIPE_PRICE_PREMIUM", ""),
}
SECRET_KEY = os.environ.get("JWT_SECRET", "dev-secret-change-me")
FREE_ACCESS_MODE = os.environ.get("FREE_ACCESS_MODE", "").lower() in ("1", "true", "yes")

stripe.api_key = STRIPE_SECRET
APP_DIR = Path(__file__).resolve().parent
app = FastAPI()
_static = APP_DIR / "static"
_templates = APP_DIR / "templates"
if _static.is_dir():
    app.mount("/static", StaticFiles(directory=str(_static)), name="static")
if not _templates.is_dir():
    _templates = APP_DIR / "templates"
templates = Jinja2Templates(directory=str(_templates)) if _templates.is_dir() else None
templates.env.globals["free_access"] = FREE_ACCESS_MODE
_signer = URLSafeTimedSerializer(SECRET_KEY)

TIERS = {
    "express": {"name": "Express", "price": "$99–$199", "sla": "24h", "hours": 24},
    "standard": {"name": "Standard", "price": "$499–$1,499", "sla": "48–72h", "hours": 72},
    "premium": {"name": "Premium", "price": "$2,500–$7,500", "sla": "5–7d", "hours": 168},
}


def _env_ok() -> list[str]:
    missing = []
    if not os.environ.get("DATABASE_URL", "").strip():
        missing.append("DATABASE_URL")
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        missing.append("OPENAI_API_KEY")
    if not os.environ.get("INTERNAL_JOB_SECRET", "").strip():
        missing.append("INTERNAL_JOB_SECRET")
    if not os.environ.get("QSTASH_TOKEN", "").strip():
        missing.append("QSTASH_TOKEN")
    return missing


@app.get("/health")
def health():
    missing = _env_ok()
    return {"ok": not missing, "missing_env": missing, "deploy": os.environ.get("DEPLOY_TARGET", "?")}


def _tpl(request: Request, name: str, ctx: dict):
    if templates is None:
        return HTMLResponse("<h1>Blueprint OS</h1><p>Templates missing on server.</p>", status_code=500)
    return templates.TemplateResponse(name, {"request": request, **ctx})


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return _tpl(request, "index.html", {"tiers": TIERS})


@app.get("/intake", response_class=HTMLResponse)
def intake_form(request: Request, tier: str = "standard"):
    if tier not in TIERS:
        tier = "standard"
    return _tpl(request, "intake.html", {"tier": tier, "tiers": TIERS})


@app.post("/intake")
async def intake_submit(
    email: str = Form(...),
    company: str = Form(""),
    industry: str = Form(""),
    tier: str = Form("standard"),
    problem: str = Form(...),
    goal: str = Form(...),
    constraints: str = Form(""),
    timeline: str = Form(""),
    geography: str = Form(""),
    budget_band: str = Form(""),
):
    refused, reason = is_refused(problem + " " + goal)
    if refused:
        return JSONResponse({"error": "We cannot take this request.", "detail": reason}, status_code=422)
    if tier not in TIERS:
        return JSONResponse({"error": "Invalid tier."}, status_code=422)
    if not FREE_ACCESS_MODE and not STRIPE_PRICES.get(tier):
        return JSONResponse({"error": "Pricing not configured for this tier. Contact support."}, status_code=503)

    brief = {
        "problem": problem,
        "goal": goal,
        "constraints": constraints,
        "timeline": timeline,
        "geography": geography,
        "budget_band": budget_band,
    }
    job_id = new_job(tier=tier, email=email, industry=industry, company=company)
    update_job(job_id, brief=brief, sla_hours=TIERS[tier]["hours"])
    audit(job_id, actor="client", step="intake", input_ref="web_form", output_ref="brief")

    if FREE_ACCESS_MODE:
        update_job(job_id, stripe_payment_status="waived", status="paid")
        audit(job_id, actor="system", step="payment", approval="free_access")
        enqueue("run_research_and_draft", job_id)
        return RedirectResponse(f"/job/{job_id}?started=1", status_code=303)

    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{"price": STRIPE_PRICES[tier], "quantity": 1}],
        customer_email=email,
        success_url=f"{APP_URL}/job/{job_id}?paid=1",
        cancel_url=f"{APP_URL}/intake?tier={tier}",
        metadata={"job_id": job_id, "tier": tier},
    )
    update_job(job_id, stripe_session_id=session.id, stripe_payment_status="pending")
    return RedirectResponse(session.url, status_code=303)


@app.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    if event["type"] == "checkout.session.completed":
        s = event["data"]["object"]
        job_id = s["metadata"].get("job_id")
        if job_id:
            update_job(job_id, stripe_payment_status="paid", status="paid")
            audit(job_id, actor="stripe", step="payment", output_ref=s["id"], approval="paid")
            enqueue("run_research_and_draft", job_id)
    return {"ok": True}


@app.post("/internal/jobs/{task}/{job_id}")
async def internal_job(task: str, job_id: str, request: Request):
    body = await request.body()
    try:
        verify_internal_request(request.headers.get("authorization"), body)
    except PermissionError as e:
        raise HTTPException(401, str(e)) from e

    import orchestrator

    if task == "run_research_and_draft":
        orchestrator.run_research_and_draft(job_id)
    elif task == "run_deliver":
        orchestrator.run_deliver(job_id)
    else:
        raise HTTPException(404, "Unknown task")
    return {"ok": True}


@app.get("/job/{job_id}", response_class=HTMLResponse)
def job_status(request: Request, job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return _tpl(request, "status.html", {"job": job})


@app.get("/download/{job_id}/docx")
def download_docx(job_id: str):
    job = get_job(job_id)
    if not job or job["status"] != "delivered":
        raise HTTPException(404, "Not delivered")

    blob_url = job.get("deliverable_blob_url")
    if blob_url:
        return RedirectResponse(blob_url, status_code=302)

    if not job.get("blueprint"):
        raise HTTPException(404, "Blueprint missing")

    path = os.path.join(OUTPUT_DIR, f"{job_id}.docx")
    if os.path.exists(path):
        return FileResponse(path, filename=f"blueprint-{job_id[:8]}.docx")

    content = docx_bytes(job)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="blueprint-{job_id[:8]}.docx"'},
    )


def _require_reviewer(reviewer: Optional[str]):
    if not reviewer:
        raise HTTPException(401, "Not signed in")
    try:
        val = _signer.loads(reviewer, max_age=60 * 60 * 8)
        if val != "reviewer":
            raise HTTPException(401, "Bad session")
    except BadSignature as e:
        raise HTTPException(401, "Bad session") from e


@app.get("/review/login", response_class=HTMLResponse)
def review_login_page(request: Request):
    return _tpl(request, "review_login.html", {})


@app.post("/review/login")
def review_login(password: str = Form(...)):
    if not hmac.compare_digest(password, REVIEW_PASSWORD):
        raise HTTPException(401, "Wrong password")
    token = _signer.dumps("reviewer")
    r = RedirectResponse("/review", status_code=303)
    r.set_cookie("reviewer", token, httponly=True, samesite="lax", secure=APP_URL.startswith("https://"))
    return r


@app.get("/review", response_class=HTMLResponse)
def review_inbox(request: Request, reviewer: Optional[str] = Cookie(None)):
    _require_reviewer(reviewer)
    return _tpl(request, "review.html", {"jobs": list_review_jobs()})


@app.get("/review/{job_id}", response_class=HTMLResponse)
def review_job_page(request: Request, job_id: str, reviewer: Optional[str] = Cookie(None)):
    _require_reviewer(reviewer)
    job = get_job(job_id)
    if not job:
        raise HTTPException(404)
    return _tpl(request, "review_job.html", {"job": job})


@app.post("/review/{job_id}/approve")
def review_approve(job_id: str, notes: str = Form(""), reviewer: Optional[str] = Cookie(None)):
    _require_reviewer(reviewer)
    job = get_job(job_id)
    if not job:
        raise HTTPException(404)
    audit(job_id, actor="reviewer", step="human_review", approval="approved", meta={"notes": notes[:500]})
    update_job(job_id, reviewer_id="reviewer", review_notes=notes, status="approved")
    enqueue("run_deliver", job_id)
    return RedirectResponse(f"/review/{job_id}", status_code=303)


@app.post("/review/{job_id}/reject")
def review_reject(job_id: str, notes: str = Form(""), reviewer: Optional[str] = Cookie(None)):
    _require_reviewer(reviewer)
    job = get_job(job_id)
    if not job:
        raise HTTPException(404)
    audit(job_id, actor="reviewer", step="human_review", approval="returned", meta={"notes": notes[:500]})
    update_job(job_id, reviewer_id="reviewer", review_notes=notes, status="returned")
    return RedirectResponse(f"/review/{job_id}", status_code=303)


@app.get("/review-log")
def review_log(reviewer: Optional[str] = Cookie(None)):
    _require_reviewer(reviewer)
    return {"jobs": list_all_jobs(limit=200)}
