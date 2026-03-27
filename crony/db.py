import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, List, Tuple, Optional

DB_DIR = Path.home() / ".crony"
DB_PATH = DB_DIR / "jobs.db"

def ensure_db() -> None:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                cron TEXT NOT NULL,
                command TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS job_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                run_at TEXT NOT NULL DEFAULT (datetime('now')),
                success INTEGER NOT NULL,
                stdout TEXT,
                stderr TEXT,
                duration REAL,
                FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
            )
            """
        )
        conn.commit()
    finally:
        conn.close()

@contextmanager
def get_conn():
    ensure_db()
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

# CRUD

def add_job(name: str, cron: str, command: str) -> int:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO jobs (name, cron, command) VALUES (?, ?, ?)",
            (name, cron, command),
        )
        conn.commit()
        return cur.lastrowid


def get_job(job_id: int) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        cur = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,))
        return cur.fetchone()


def list_jobs() -> List[sqlite3.Row]:
    with get_conn() as conn:
        cur = conn.execute("SELECT * FROM jobs ORDER BY id")
        return cur.fetchall()


def update_job_enabled(job_id: int, enabled: bool) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE jobs SET enabled=?, updated_at=datetime('now') WHERE id=?", (1 if enabled else 0, job_id)
        )
        conn.commit()
        return cur.rowcount > 0


def remove_job(job_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM jobs WHERE id=?", (job_id,))
        conn.commit()
        return cur.rowcount > 0


def add_run(job_id: int, success: bool, stdout: str, stderr: str, duration: float) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO job_runs (job_id, success, stdout, stderr, duration) VALUES (?, ?, ?, ?, ?)",
            (job_id, 1 if success else 0, stdout, stderr, duration),
        )
        conn.commit()
        return cur.lastrowid


def get_runs(job_id: int, limit: int = 20) -> List[sqlite3.Row]:
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT * FROM job_runs WHERE job_id=? ORDER BY run_at DESC LIMIT ?", (job_id, limit)
        )
        return cur.fetchall()
