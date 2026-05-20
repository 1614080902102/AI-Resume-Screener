"""SQLite persistence layer for jobs and screenings."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).parent.parent / "data" / "screener.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    department TEXT,
    jd_text TEXT NOT NULL,
    threshold INTEGER NOT NULL DEFAULT 80,
    custom_rules TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open',  -- open / closed
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS screenings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    candidate_name TEXT,
    candidate_source TEXT,        -- 上传文件名 / zip 名
    score INTEGER NOT NULL DEFAULT 0,
    passed INTEGER NOT NULL DEFAULT 0,
    verdict TEXT,
    summary TEXT,
    resume_json TEXT,
    match_json TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_screenings_job ON screenings(job_id);
CREATE INDEX IF NOT EXISTS idx_screenings_created ON screenings(created_at);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ---------- Jobs ----------
def list_jobs(status: str | None = None, order: str = "id_asc") -> list[dict]:
    order_sql = {
        "id_asc": "id ASC",
        "id_desc": "id DESC",
        "updated_desc": "updated_at DESC",
    }.get(order, "id ASC")
    with get_conn() as conn:
        if status:
            rows = conn.execute(
                f"SELECT * FROM jobs WHERE status=? ORDER BY {order_sql}",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT * FROM jobs ORDER BY {order_sql}"
            ).fetchall()
        return [dict(r) for r in rows]


def get_job(job_id: int) -> dict | None:
    with get_conn() as conn:
        r = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return dict(r) if r else None


def create_job(
    name: str,
    jd_text: str,
    threshold: int = 80,
    custom_rules: str = "",
    department: str = "",
) -> int:
    now = _now()
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO jobs (name, department, jd_text, threshold,
               custom_rules, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 'open', ?, ?)""",
            (name, department, jd_text, threshold, custom_rules, now, now),
        )
        return cur.lastrowid


def update_job(
    job_id: int,
    name: str | None = None,
    jd_text: str | None = None,
    threshold: int | None = None,
    custom_rules: str | None = None,
    department: str | None = None,
    status: str | None = None,
):
    job = get_job(job_id)
    if not job:
        return
    fields = {
        "name": name if name is not None else job["name"],
        "department": department if department is not None else job["department"],
        "jd_text": jd_text if jd_text is not None else job["jd_text"],
        "threshold": threshold if threshold is not None else job["threshold"],
        "custom_rules": (
            custom_rules if custom_rules is not None else job["custom_rules"]
        ),
        "status": status if status is not None else job["status"],
        "updated_at": _now(),
    }
    with get_conn() as conn:
        conn.execute(
            """UPDATE jobs SET name=:name, department=:department, jd_text=:jd_text,
               threshold=:threshold, custom_rules=:custom_rules,
               status=:status, updated_at=:updated_at WHERE id=:id""",
            {**fields, "id": job_id},
        )


def delete_job(job_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM jobs WHERE id=?", (job_id,))


# ---------- Screenings ----------
def save_screening(
    job_id: int,
    candidate_name: str,
    candidate_source: str,
    score: int,
    passed: bool,
    verdict: str,
    summary: str,
    resume_struct: dict,
    match: dict,
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO screenings
               (job_id, candidate_name, candidate_source, score, passed,
                verdict, summary, resume_json, match_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job_id,
                candidate_name,
                candidate_source,
                score,
                1 if passed else 0,
                verdict,
                summary,
                json.dumps(resume_struct, ensure_ascii=False),
                json.dumps(match, ensure_ascii=False),
                _now(),
            ),
        )
        return cur.lastrowid


def list_screenings(
    job_id: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    passed_only: bool = False,
    min_score: int | None = None,
) -> list[dict]:
    where = []
    params: list[Any] = []
    if job_id is not None:
        where.append("job_id=?")
        params.append(job_id)
    if start_date:
        where.append("created_at>=?")
        params.append(start_date)
    if end_date:
        where.append("created_at<=?")
        params.append(end_date + "T23:59:59")
    if passed_only:
        where.append("passed=1")
    if min_score is not None:
        where.append("score>=?")
        params.append(min_score)
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM screenings{where_sql} ORDER BY score DESC, created_at DESC",
            params,
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["resume"] = json.loads(d.pop("resume_json") or "{}")
            d["match"] = json.loads(d.pop("match_json") or "{}")
        except Exception:
            d["resume"], d["match"] = {}, {}
        out.append(d)
    return out


def get_screening(screening_id: int) -> dict | None:
    with get_conn() as conn:
        r = conn.execute(
            "SELECT * FROM screenings WHERE id=?", (screening_id,)
        ).fetchone()
        if not r:
            return None
        d = dict(r)
        try:
            d["resume"] = json.loads(d.pop("resume_json") or "{}")
            d["match"] = json.loads(d.pop("match_json") or "{}")
        except Exception:
            d["resume"], d["match"] = {}, {}
        return d


def delete_screening(screening_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM screenings WHERE id=?", (screening_id,))


# ---------- Stats ----------
def job_stats(job_id: int) -> dict:
    with get_conn() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM screenings WHERE job_id=?", (job_id,)
        ).fetchone()[0]
        passed = conn.execute(
            "SELECT COUNT(*) FROM screenings WHERE job_id=? AND passed=1",
            (job_id,),
        ).fetchone()[0]
        avg_score = conn.execute(
            "SELECT AVG(score) FROM screenings WHERE job_id=?", (job_id,)
        ).fetchone()[0] or 0
        # by day
        per_day = conn.execute(
            """SELECT DATE(created_at) AS d, COUNT(*) AS c,
                      SUM(passed) AS p, AVG(score) AS avg_s
               FROM screenings WHERE job_id=?
               GROUP BY DATE(created_at) ORDER BY d""",
            (job_id,),
        ).fetchall()
    return {
        "total": total,
        "passed": passed,
        "pass_rate": (passed / total) if total else 0.0,
        "avg_score": round(avg_score, 1) if avg_score else 0.0,
        "per_day": [dict(r) for r in per_day],
    }


def global_stats() -> dict:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT j.id, j.name, j.threshold,
                      COUNT(s.id) AS total,
                      SUM(CASE WHEN s.passed=1 THEN 1 ELSE 0 END) AS passed,
                      AVG(s.score) AS avg_score
               FROM jobs j LEFT JOIN screenings s ON s.job_id=j.id
               GROUP BY j.id ORDER BY j.updated_at DESC"""
        ).fetchall()
    return {"jobs": [dict(r) for r in rows]}
