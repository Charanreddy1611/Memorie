import sqlite3
import json
import uuid
import os
from datetime import datetime, date
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), "memory_director.db")


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                date TEXT NOT NULL,
                title TEXT,
                summary TEXT,
                people TEXT,
                location TEXT,
                emotion TEXT,
                key_moments TEXT,
                style TEXT DEFAULT 'movie_trailer',
                video_path TEXT,
                panel_paths TEXT,
                thumbnail_path TEXT,
                music_path TEXT,
                cover_path TEXT,
                calendar_event_id TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS character_refs (
                id TEXT PRIMARY KEY,
                name TEXT DEFAULT 'default',
                image_path TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        """)


def _serialize_list(items: list | None) -> str | None:
    if items is None:
        return None
    return json.dumps(items)


def _deserialize_list(raw: str | None) -> list:
    if raw is None:
        return []
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []


def _row_to_memory(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["people"] = _deserialize_list(d.get("people"))
    d["key_moments"] = _deserialize_list(d.get("key_moments"))
    return d


# ── Memory CRUD ──

def save_memory(memory: dict) -> str:
    memory_id = memory.get("id", str(uuid.uuid4()))
    with get_db() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO memories
               (id, date, title, summary, people, location, emotion,
                key_moments, style, video_path, panel_paths, thumbnail_path,
                music_path, cover_path, calendar_event_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                memory_id,
                memory.get("date", date.today().isoformat()),
                memory.get("title", "Untitled Memory"),
                memory.get("summary", ""),
                _serialize_list(memory.get("people")),
                memory.get("location"),
                memory.get("emotion"),
                _serialize_list(memory.get("key_moments")),
                memory.get("style", "movie_trailer"),
                memory.get("video_path"),
                memory.get("panel_paths"),
                memory.get("thumbnail_path"),
                memory.get("music_path"),
                memory.get("cover_path"),
                memory.get("calendar_event_id"),
            ),
        )
    return memory_id


def get_memory(memory_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
        return _row_to_memory(row) if row else None


def get_all_memories() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM memories ORDER BY date DESC, created_at DESC").fetchall()
        return [_row_to_memory(r) for r in rows]


def get_memories_for_date(target_date: str) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM memories WHERE date = ?", (target_date,)).fetchall()
        return [_row_to_memory(r) for r in rows]


def get_on_this_day(month: int, day: int) -> list[dict]:
    pattern = f"%-{month:02d}-{day:02d}"
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM memories WHERE date LIKE ? ORDER BY date DESC",
            (pattern,),
        ).fetchall()
        return [_row_to_memory(r) for r in rows]


def update_memory(memory_id: str, updates: dict):
    set_clauses = []
    values = []
    for key, val in updates.items():
        if key in ("people", "key_moments"):
            val = _serialize_list(val)
        set_clauses.append(f"{key} = ?")
        values.append(val)
    values.append(memory_id)

    with get_db() as conn:
        conn.execute(
            f"UPDATE memories SET {', '.join(set_clauses)} WHERE id = ?",
            values,
        )


def delete_memory(memory_id: str):
    with get_db() as conn:
        conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))


# ── Character References ──

def save_character_ref(image_path: str, name: str = "default") -> str:
    ref_id = str(uuid.uuid4())
    with get_db() as conn:
        conn.execute(
            "INSERT INTO character_refs (id, name, image_path) VALUES (?, ?, ?)",
            (ref_id, name, image_path),
        )
    return ref_id


def get_character_refs(name: str = "default") -> list[str]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT image_path FROM character_refs WHERE name = ? ORDER BY created_at DESC LIMIT 3",
            (name,),
        ).fetchall()
        return [r["image_path"] for r in rows]


def clear_character_refs(name: str = "default"):
    with get_db() as conn:
        conn.execute("DELETE FROM character_refs WHERE name = ?", (name,))


# ── Settings ──

def get_setting(key: str, default: str = "") -> str:
    with get_db() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )


init_db()
