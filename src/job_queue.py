import os
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

ISO_FMT = "%Y-%m-%dT%H:%M:%S.%fZ"


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime(ISO_FMT)


def parse_iso(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    return datetime.strptime(ts, ISO_FMT).replace(tzinfo=timezone.utc)


@dataclass
class Job:
    id: str
    type: str
    status: str
    payload: str
    result: Optional[str]
    error: Optional[str]
    attempts: int
    max_attempts: int
    backoff_base: int
    created_at: str
    started_at: Optional[str]
    completed_at: Optional[str]
    next_attempt_at: Optional[str]
    priority: int


class JobQueue:
    def __init__(self, db_path: str = None) -> None:
        self.db_path = db_path or os.environ.get("JOB_DB_PATH", "jobs.db")
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("BEGIN")
            conn.execute(
                """
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
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_next_attempt ON jobs(next_attempt_at)"
            )
            conn.execute("COMMIT")

    # --- Public API ---
    def enqueue(
        self,
        job_type: str,
        payload: Dict[str, Any],
        *,
        max_attempts: int = 5,
        priority: int = 0,
        backoff_base: int = 2,
    ) -> str:
        job_id = uuid.uuid4().hex
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                INSERT INTO jobs (
                    id, type, status, payload, result, error, attempts, max_attempts,
                    backoff_base, created_at, started_at, completed_at, next_attempt_at, priority
                ) VALUES (?, ?, 'pending', ?, NULL, NULL, 0, ?, ?, ?, NULL, NULL, NULL, ?)
                """,
                (
                    job_id,
                    job_type,
                    json.dumps(payload),
                    max_attempts,
                    backoff_base,
                    now_iso(),
                    priority,
                ),
            )
            conn.execute("COMMIT")
        return job_id

    def reserve_one(self) -> Optional[Job]:
        now = now_iso()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT * FROM jobs
                WHERE status = 'pending'
                  AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
                ORDER BY priority DESC, created_at ASC
                LIMIT 1
                """,
                (now,),
            ).fetchone()
            if not row:
                conn.execute("COMMIT")
                return None

            # Try to claim the job (optimistic lock by status)
            updated = conn.execute(
                """
                UPDATE jobs
                SET status='processing', started_at=COALESCE(started_at, ?), attempts=attempts+1
                WHERE id = ? AND status = 'pending'
                """,
                (now, row["id"]),
            )
            if updated.rowcount != 1:
                conn.execute("COMMIT")
                return None

            # Re-read with updated state
            claimed = conn.execute("SELECT * FROM jobs WHERE id = ?", (row["id"],)).fetchone()
            conn.execute("COMMIT")
            return Job(**dict(claimed)) if claimed else None

    def complete(self, job_id: str, result: Dict[str, Any] | str | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET status='completed', completed_at=?, result=? , error=NULL
                WHERE id = ?
                """,
                (now_iso(), json.dumps(result) if isinstance(result, (dict, list)) else (result or None), job_id),
            )

    def _compute_backoff(self, attempts: int) -> int:
        # Exponential backoff in seconds, capped at 1 hour
        base = 5  # seconds
        delay = base * (2 ** max(0, attempts - 1))
        return int(min(delay, 3600))

    def fail(self, job_id: str, error_message: str) -> None:
        with self._connect() as conn:
            row = conn.execute("SELECT attempts, max_attempts FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if not row:
                return
            attempts, max_attempts = row["attempts"], row["max_attempts"]
            if attempts < max_attempts:
                delay = self._compute_backoff(attempts)
                next_time = (datetime.now(timezone.utc) + timedelta(seconds=delay)).strftime(ISO_FMT)
                conn.execute(
                    """
                    UPDATE jobs
                    SET status='pending', error=?, next_attempt_at=?
                    WHERE id = ?
                    """,
                    (error_message[:2000], next_time, job_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE jobs
                    SET status='failed', error=?, completed_at=?
                    WHERE id = ?
                    """,
                    (error_message[:2000], now_iso(), job_id),
                )

    def get(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if not row:
                return None
            data = dict(row)
            # Best effort parse JSON fields
            try:
                if data.get("payload"):
                    data["payload"] = json.loads(data["payload"])  # type: ignore
            except Exception:
                pass
            try:
                if data.get("result"):
                    data["result"] = json.loads(data["result"])  # type: ignore
            except Exception:
                pass
            return data

    def stats(self) -> Dict[str, Any]:
        with self._connect() as conn:
            counts = {
                s: conn.execute("SELECT COUNT(*) FROM jobs WHERE status=?", (s,)).fetchone()[0]
                for s in ("pending", "processing", "completed", "failed")
            }
            oldest = conn.execute(
                "SELECT created_at FROM jobs WHERE status='pending' ORDER BY created_at ASC LIMIT 1"
            ).fetchone()
            return {
                "counts": counts,
                "oldest_pending": oldest[0] if oldest else None,
                "db_path": self.db_path,
            }

    def list_jobs(self, limit: int = 50, status: Optional[str] = None) -> Dict[str, Any]:
        with self._connect() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM jobs WHERE status=? ORDER BY created_at DESC LIMIT ?",
                    (status, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return {"jobs": [dict(r) for r in rows]}

    def cleanup(self, max_age_hours: int = 72, statuses: Tuple[str, ...] = ("completed", "failed")) -> Dict[str, Any]:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).strftime(ISO_FMT)
        with self._connect() as conn:
            q_marks = ",".join(["?"] * len(statuses))
            sql = f"DELETE FROM jobs WHERE status IN ({q_marks}) AND completed_at IS NOT NULL AND completed_at < ?"
            args = [*statuses, cutoff]
            cur = conn.execute(sql, args)
            return {"deleted": cur.rowcount, "cutoff": cutoff, "statuses": list(statuses)}

