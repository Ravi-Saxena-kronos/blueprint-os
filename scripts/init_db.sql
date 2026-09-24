CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS jobs (
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status TEXT NOT NULL DEFAULT 'queued',
    tier TEXT NOT NULL,
    industry TEXT,
    email TEXT NOT NULL,
    company TEXT,
    brief JSONB,
    classification JSONB,
    blueprint JSONB,
    verifier_report JSONB,
    reviewer_id TEXT,
    review_notes TEXT,
    stripe_session_id TEXT,
    stripe_payment_status TEXT,
    price_cents INT,
    model_cost_cents INT DEFAULT 0,
    sla_hours INT DEFAULT 24,
    delivered_at TIMESTAMPTZ,
    deliverable_blob_url TEXT
);

CREATE TABLE IF NOT EXISTS audit_events (
    id BIGSERIAL PRIMARY KEY,
    job_id UUID REFERENCES jobs(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actor TEXT NOT NULL,
    step TEXT,
    input_ref TEXT,
    output_ref TEXT,
    approval TEXT,
    meta JSONB
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_email ON jobs(email);
CREATE INDEX IF NOT EXISTS idx_audit_job ON audit_events(job_id);
