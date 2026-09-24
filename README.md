# Blueprint OS (MVP)

Decision-grade business blueprints: paid intake → AI orchestrator → human review → DOCX delivery.

This repository is structured for **GitHub + Vercel** deployment. Optional `docker-compose.yml` supports local full-stack dev.

## Repository layout

| Path | Purpose |
|------|---------|
| `api/index.py` | Vercel serverless entry (FastAPI) |
| `app/` | Application code, templates, static assets |
| `scripts/init_db.sql` | Postgres schema (run once on Neon/Supabase) |
| `vercel.json` | Vercel Python function settings (300s timeout) |
| `docs/` | Deployment workflow (Word document) |

## Quick links

- **Step-by-step deploy guide (download):** [`docs/Blueprint_OS_GitHub_Vercel_Workflow.doc`](docs/Blueprint_OS_GitHub_Vercel_Workflow.doc) — open in Word/LibreOffice; use *Save As → .docx* if you need DOCX
- Same content on GitHub: [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)

## Environment variables

Copy `.env.example` to `.env` for local reference. **Set the same keys in Vercel → Project → Settings → Environment Variables** (never commit `.env`).

Required for production on Vercel:

- `DEPLOY_TARGET=vercel`
- `APP_URL` — your canonical HTTPS URL (e.g. `https://your-app.vercel.app`)
- `DATABASE_URL` — Neon/Supabase Postgres
- `STRIPE_*`, `OPENAI_API_KEY`
- `REVIEW_PASSWORD`, `JWT_SECRET`, `INTERNAL_JOB_SECRET`
- `QSTASH_TOKEN` (+ signing keys from Upstash QStash dashboard)

## Endpoints

- `/` — pricing
- `/intake` — client form → Stripe Checkout
- `/webhook/stripe` — payment → background job
- `/job/{id}` — status
- `/download/{id}/docx` — deliverable
- `/review` — reviewer inbox
