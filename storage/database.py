"""SQLite autosave. The caller's serial executor keeps writes off the UI thread."""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path

from tagging.model import Project


def save_project(path: str | Path, project: Project) -> None:
    payload = json.dumps(project.to_dict(), ensure_ascii=False, separators=(",", ":"))
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(target, timeout=30) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE IF NOT EXISTS project (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)")
        conn.execute("INSERT INTO project(id,payload) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload", (payload,))


def load_project(path: str | Path) -> Project:
    with sqlite3.connect(path) as conn:
        row = conn.execute("SELECT payload FROM project WHERE id=1").fetchone()
    if not row:
        raise ValueError("No project in database")
    return Project.from_dict(json.loads(row[0]))
