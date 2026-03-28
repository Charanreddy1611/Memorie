"""
Memoire — SQLite persistence layer for memories, character references, and settings
===================================================================================

This module is the single source of truth for on-disk storage used by the Memoire app.
It opens a WAL-mode SQLite database (path from ``config.DB_PATH``), defines the schema
for memories (narrative metadata, media paths, calendar linkage), optional character
reference images for consistent AI generation, and a simple key/value settings table.

Typical use cases:
  * **Create / update memories** after the user captures a moment or the pipeline
    produces video, panels, music, and thumbnails — ``save_memory`` and ``update_memory``.
  * **List and filter** for the timeline UI, day view, and “on this day” nostalgia
    features — ``get_all_memories``, ``get_memories_for_date``, ``get_on_this_day``.
  * **Read one memory** by id for detail pages or export — ``get_memory``.
  * **Delete** a memory when the user removes an entry — ``delete_memory``.
  * **Character refs** store recent reference image paths per logical name (e.g. default)
    for multimodal generation — ``save_character_ref``, ``get_character_refs``,
    ``clear_character_refs``.
  * **App settings** (API keys, toggles) — ``get_setting``, ``set_setting``.

Calling ``init_db()`` at import ensures tables exist before any CRUD runs. Internal
helpers serialize JSON list fields (people, key_moments) and map rows to dicts the
rest of the app expects.
"""

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date

from config import DB_PATH
from logger import get_logger

log = get_logger(__name__)


@contextmanager
def get_db():
    """
    Yield a SQLite connection with Row factory and WAL mode; commit on success.

    The connection is closed after the block. Use as ``with get_db() as conn:``.
    """
    log.info("get_db called")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    """Create memories, character_refs, and settings tables if they do not exist."""
    log.info("init_db called")
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
    """
    Serialize a list to a JSON string for SQLite storage, or None if items is None.

    Args:
        items: List values to store, or None to represent SQL NULL.

    Returns:
        JSON-encoded string, or None.
    """
    log.info("_serialize_list called items=%r", items)
    if items is None:
        return None
    return json.dumps(items)


def _deserialize_list(raw: str | None) -> list:
    """
    Parse a JSON list from the database; return [] if missing or invalid.

    Args:
        raw: Stored JSON string, or None.

    Returns:
        A Python list (empty on failure or null input).
    """
    log.info("_deserialize_list called raw=%r", raw)
    if raw is None:
        return []
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []


def _row_to_memory(row: sqlite3.Row) -> dict:
    """
    Convert a memories table row to an app-facing dict with list fields hydrated.

    Args:
        row: A sqlite3.Row from the memories query.

    Returns:
        Dict including ``people`` and ``key_moments`` as lists.
    """
    log.info("_row_to_memory called row_id=%r", row["id"] if row else None)
    d = dict(row)
    d["people"] = _deserialize_list(d.get("people"))
    d["key_moments"] = _deserialize_list(d.get("key_moments"))
    return d


def save_memory(memory: dict) -> str:
    """
    Insert or replace a full memory row; assign a new UUID id if none provided.

    Args:
        memory: Dict with memory fields (id, date, title, summary, people, etc.).

    Returns:
        The memory id (existing or newly generated).
    """
    log.info("save_memory called memory=%r", memory)
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
    """
    Load a single memory by primary key.

    Args:
        memory_id: UUID string of the memory.

    Returns:
        Memory dict or None if not found.
    """
    log.info("get_memory called memory_id=%r", memory_id)
    with get_db() as conn:
        row = conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
        return _row_to_memory(row) if row else None


def get_all_memories() -> list[dict]:
    """
    Return every memory ordered by date then created_at (newest first).

    Returns:
        List of memory dicts.
    """
    log.info("get_all_memories called")
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM memories ORDER BY date DESC, created_at DESC").fetchall()
        return [_row_to_memory(r) for r in rows]


def get_memories_for_date(target_date: str) -> list[dict]:
    """
    Return memories whose ``date`` column equals the given ISO date string.

    Args:
        target_date: Date string (e.g. YYYY-MM-DD).

    Returns:
        List of memory dicts for that calendar day.
    """
    log.info("get_memories_for_date called target_date=%r", target_date)
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM memories WHERE date = ?", (target_date,)).fetchall()
        return [_row_to_memory(r) for r in rows]


def get_on_this_day(month: int, day: int) -> list[dict]:
    """
    Return memories that fall on this month/day in any year (anniversary-style).

    Args:
        month: Month number 1-12.
        day: Day of month 1-31.

    Returns:
        Matching memories, newest date first.
    """
    log.info("get_on_this_day called month=%r day=%r", month, day)
    pattern = f"%-{month:02d}-{day:02d}"
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM memories WHERE date LIKE ? ORDER BY date DESC",
            (pattern,),
        ).fetchall()
        return [_row_to_memory(r) for r in rows]


def update_memory(memory_id: str, updates: dict):
    """
    Partially update columns on a memory row.

    Args:
        memory_id: Id of the row to update.
        updates: Column name to value; list fields are JSON-serialized automatically.
    """
    log.info("update_memory called memory_id=%r updates=%r", memory_id, updates)
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
    """
    Remove a memory row by id.

    Args:
        memory_id: Primary key to delete.
    """
    log.info("delete_memory called memory_id=%r", memory_id)
    with get_db() as conn:
        conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))


def save_character_ref(image_path: str, name: str = "default") -> str:
    """
    Store a character reference image path under a logical name.

    Args:
        image_path: Filesystem path to the image.
        name: Group name (default ``default``).

    Returns:
        New reference row id (UUID string).
    """
    log.info("save_character_ref called image_path=%r name=%r", image_path, name)
    ref_id = str(uuid.uuid4())
    with get_db() as conn:
        conn.execute(
            "INSERT INTO character_refs (id, name, image_path) VALUES (?, ?, ?)",
            (ref_id, name, image_path),
        )
    return ref_id


def get_character_refs(name: str = "default") -> list[str]:
    """
    Return up to three most recent image paths for the given character name.

    Args:
        name: Logical character name.

    Returns:
        List of image_path strings (newest first).
    """
    log.info("get_character_refs called name=%r", name)
    with get_db() as conn:
        rows = conn.execute(
            "SELECT image_path FROM character_refs WHERE name = ? ORDER BY created_at DESC LIMIT 3",
            (name,),
        ).fetchall()
        return [r["image_path"] for r in rows]


def clear_character_refs(name: str = "default"):
    """
    Delete all character reference rows for a logical name.

    Args:
        name: Character group to clear.
    """
    log.info("clear_character_refs called name=%r", name)
    with get_db() as conn:
        conn.execute("DELETE FROM character_refs WHERE name = ?", (name,))


def get_setting(key: str, default: str = "") -> str:
    """
    Read a string value from the settings table.

    Args:
        key: Setting key.
        default: Returned if the key is missing.

    Returns:
        Stored value or default.
    """
    log.info("get_setting called key=%r default=%r", key, default)
    with get_db() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str):
    """
    Upsert a key/value pair in the settings table.

    Args:
        key: Setting key.
        value: String value to store.
    """
    log.info("set_setting called key=%r value=%r", key, value)
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )


init_db()
