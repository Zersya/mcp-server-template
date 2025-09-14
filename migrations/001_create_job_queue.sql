-- SQLite migration: create jobs queue table
BEGIN TRANSACTION;

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    status TEXT NOT NULL,
    payload TEXT NOT NULL,
    result TEXT,
    error TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 5,
    backoff_base INTEGER NOT NULL DEFAULT 2,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    next_attempt_at TEXT,
    priority INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_next_attempt ON jobs(next_attempt_at);

COMMIT;

