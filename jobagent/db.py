from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from jobagent.paths import DATA_DIR, DB_PATH

STATUSES = (
    "new",
    "skipped",
    "applied",
    "pending_link",
    "pending_email",
    "failed",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY,
                channel_id INTEGER NOT NULL,
                channel_title TEXT,
                channel_username TEXT,
                message_id INTEGER NOT NULL,
                posted_at TEXT,
                text TEXT,
                urls TEXT,
                contacts TEXT,
                emails TEXT,
                score INTEGER NOT NULL DEFAULT 0,
                matched_keywords TEXT,
                status TEXT NOT NULL DEFAULT 'new',
                apply_method TEXT,
                applied_at TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(channel_id, message_id)
            )
            """
        )
        existing = {row[1] for row in conn.execute("PRAGMA table_info(jobs)")}
        extras = {
            "company": "TEXT",
            "position": "TEXT",
            "salary": "TEXT",
            "remote": "TEXT",
            "location": "TEXT",
            "apply_url": "TEXT",
            "telegram_contact": "TEXT",
            "apply_status": "TEXT",
        }
        for name, spec in extras.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE jobs ADD COLUMN {name} {spec}")


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def loads(value: str | None) -> list[str]:
    if not value:
        return []
    data = json.loads(value)
    return [str(item) for item in data]


def upsert_job(conn: sqlite3.Connection, payload: dict[str, Any]) -> bool:
    """Insert a job if new. Returns True when a row was inserted."""
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO jobs (
            channel_id, channel_title, channel_username, message_id,
            posted_at, text, urls, contacts, emails, score, matched_keywords,
            status, created_at
        ) VALUES (
            :channel_id, :channel_title, :channel_username, :message_id,
            :posted_at, :text, :urls, :contacts, :emails, :score, :matched_keywords,
            'new', :created_at
        )
        """,
        payload,
    )
    return cur.rowcount == 1


def rescore_new_jobs(
    conn: sqlite3.Connection,
    keywords: list[str],
    location_keywords: list[str],
) -> None:
    from jobagent.matcher import score_text

    rows = conn.execute("SELECT id, text FROM jobs WHERE status = 'new'").fetchall()
    for row in rows:
        score, hits = score_text(row["text"] or "", keywords, location_keywords)
        conn.execute(
            "UPDATE jobs SET score = ?, matched_keywords = ? WHERE id = ?",
            (score, dumps(hits), row["id"]),
        )


def list_inbox(conn: sqlite3.Connection, min_score: int = 1) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT * FROM jobs
            WHERE status = 'new' AND score >= ?
            ORDER BY score DESC, posted_at DESC, id DESC
            """,
            (min_score,),
        )
    )


def set_status(
    conn: sqlite3.Connection,
    job_id: int,
    status: str,
    *,
    apply_method: str | None = None,
    notes: str | None = None,
) -> None:
    if status not in STATUSES:
        raise ValueError(f"Unknown status: {status}")
    applied_at = utc_now() if status == "applied" else None
    conn.execute(
        """
        UPDATE jobs
        SET status = ?, apply_method = COALESCE(?, apply_method),
            applied_at = COALESCE(?, applied_at), notes = COALESCE(?, notes)
        WHERE id = ?
        """,
        (status, apply_method, applied_at, notes, job_id),
    )


def counts(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute("SELECT status, COUNT(*) AS n FROM jobs GROUP BY status")
    return {row["status"]: row["n"] for row in rows}


def record_application(
    conn: sqlite3.Connection,
    job_id: int,
    *,
    apply_method: str,
    parsed: dict[str, str | None],
    notes: str | None = None,
    apply_status: str = "applied",
) -> None:
    applied_at = utc_now()
    conn.execute(
        """
        UPDATE jobs SET
            status = 'applied',
            apply_status = ?,
            apply_method = ?,
            applied_at = COALESCE(applied_at, ?),
            notes = COALESCE(?, notes),
            company = ?,
            position = ?,
            salary = ?,
            remote = ?,
            location = ?,
            apply_url = ?,
            telegram_contact = ?
        WHERE id = ?
        """,
        (
            apply_status,
            apply_method,
            applied_at,
            notes,
            parsed.get("company"),
            parsed.get("position"),
            parsed.get("salary"),
            parsed.get("remote"),
            parsed.get("location"),
            parsed.get("apply_url"),
            parsed.get("telegram_contact"),
            job_id,
        ),
    )


def set_apply_status(conn: sqlite3.Connection, job_id: int, apply_status: str) -> None:
    conn.execute(
        "UPDATE jobs SET apply_status = ? WHERE id = ?",
        (apply_status, job_id),
    )


def list_applications(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT id, applied_at, apply_status, apply_method, company, position,
                   salary, remote, location, telegram_contact, apply_url,
                   channel_id, channel_username, message_id, channel_title, notes
            FROM jobs
            WHERE status = 'applied' OR apply_status IS NOT NULL
            ORDER BY COALESCE(applied_at, created_at) DESC, id DESC
            """
        )
    )


def export_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT applied_at, apply_status, apply_method, company, position,
                   salary, remote, location, telegram_contact, apply_url,
                   channel_id, channel_username, message_id, channel_title,
                   notes, posted_at, score
            FROM jobs
            WHERE status = 'applied' OR apply_status IS NOT NULL
            ORDER BY COALESCE(applied_at, posted_at) DESC, id DESC
            """
        )
    )


def db_path() -> Path:
    return DB_PATH
