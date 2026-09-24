# Blueprint OS — GitHub & Vercel workflow

**Downloadable Word guide:** [Blueprint_OS_GitHub_Vercel_Workflow.doc](./Blueprint_OS_GitHub_Vercel_Workflow.doc)  
(Open in Word → **Save As → .docx** if you need DOCX format.)

## Summary

1. Push this repo to GitHub (`git init`, `git add .`, `commit`, `push`).
2. Run `scripts/init_db.sql` on Neon/Supabase Postgres.
3. Configure Stripe (prices + webhook) and Upstash QStash.
4. Import repo in Vercel; set env vars from `.env.example`.
5. Deploy; test intake → payment → review → DOCX download.

See the Word document for full step-by-step tables, env var list, and troubleshooting.
