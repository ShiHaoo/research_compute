"""SQLite 持久化：sessions / messages / jobs 三张表。"""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

DB_PATH = "app.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                tool_calls TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                analysis_type TEXT NOT NULL,
                filename TEXT NOT NULL,
                status TEXT NOT NULL,
                exit_code INTEGER,
                stdout_path TEXT,
                stderr_path TEXT,
                created_at TEXT NOT NULL,
                finished_at TEXT
            );
            """
        )


def create_session(title: str) -> int:
    with _db() as conn:
        cur = conn.execute(
            "INSERT INTO sessions (title, created_at) VALUES (?, ?)", (title, _now())
        )
        return cur.lastrowid


def list_sessions() -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT id, title, created_at FROM sessions ORDER BY created_at DESC, id DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def rename_session(session_id: int, title: str) -> None:
    with _db() as conn:
        conn.execute("UPDATE sessions SET title = ? WHERE id = ?", (title, session_id))


def add_message(session_id: int, role: str, content: str, tool_calls: str | None) -> int:
    with _db() as conn:
        cur = conn.execute(
            "INSERT INTO messages (session_id, role, content, tool_calls, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (session_id, role, content, tool_calls, _now()),
        )
        return cur.lastrowid


def list_messages(session_id: int) -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT id, session_id, role, content, tool_calls, created_at"
            " FROM messages WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def insert_job(
    job_id: str, analysis_type: str, filename: str, status: str,
    stdout_path: str, stderr_path: str,
) -> None:
    with _db() as conn:
        conn.execute(
            "INSERT INTO jobs (id, analysis_type, filename, status, exit_code,"
            " stdout_path, stderr_path, created_at, finished_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (job_id, analysis_type, filename, status, None, stdout_path, stderr_path, _now(), None),
        )


def get_job(job_id: str) -> dict | None:
    with _db() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None


def update_job(job_id: str, status: str | None = None, exit_code: int | None = None,
               finished_at: str | None = None) -> None:
    fields: dict[str, object] = {}
    if status is not None:
        fields["status"] = status
    if exit_code is not None:
        fields["exit_code"] = exit_code
    if finished_at is not None:
        fields["finished_at"] = finished_at
    if not fields:
        return
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [job_id]
    with _db() as conn:
        conn.execute(f"UPDATE jobs SET {set_clause} WHERE id = ?", values)
