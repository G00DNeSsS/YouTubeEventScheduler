import sqlite3
import os
from db.models import SCHEMA

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "autodrop.db")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        try:
            conn.execute("ALTER TABLE accounts ADD COLUMN long_uploads_status TEXT DEFAULT 'unknown'")
        except Exception:
            pass


# --- Accounts ---

def get_accounts():
    with get_connection() as conn:
        return conn.execute("SELECT * FROM accounts ORDER BY created_at").fetchall()


def add_account(account_name: str, channel_id: str, credentials_json: str,
                long_uploads_status: str = "unknown") -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO accounts (account_name, channel_id, credentials_json, long_uploads_status) VALUES (?, ?, ?, ?)",
            (account_name, channel_id, credentials_json, long_uploads_status)
        )
        return cur.lastrowid


def delete_account(account_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))


def update_account_credentials(account_id: int, credentials_json: str):
    with get_connection() as conn:
        conn.execute(
            "UPDATE accounts SET credentials_json = ? WHERE id = ?",
            (credentials_json, account_id)
        )


# --- Videos ---

def get_videos():
    with get_connection() as conn:
        return conn.execute("SELECT * FROM videos ORDER BY created_at DESC").fetchall()


def add_video(file_path, title, description, tags, thumbnail_path,
              privacy, video_type, duration_seconds) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO videos
               (file_path, title, description, tags, thumbnail_path, privacy, video_type, duration_seconds)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (file_path, title, description, tags, thumbnail_path, privacy, video_type, duration_seconds)
        )
        return cur.lastrowid


def update_video(video_id: int, title, description, tags, thumbnail_path, privacy, video_type):
    with get_connection() as conn:
        conn.execute(
            """UPDATE videos SET title=?, description=?, tags=?, thumbnail_path=?,
               privacy=?, video_type=? WHERE id=?""",
            (title, description, tags, thumbnail_path, privacy, video_type, video_id)
        )


def update_video_title(video_id: int, title: str):
    with get_connection() as conn:
        conn.execute("UPDATE videos SET title = ? WHERE id = ?", (title, video_id))


def delete_video(video_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM videos WHERE id = ?", (video_id,))


def get_video(video_id: int):
    with get_connection() as conn:
        return conn.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()


# --- Scheduled Posts ---

def get_scheduled_posts(status=None):
    with get_connection() as conn:
        if status:
            return conn.execute(
                """SELECT sp.*, v.title, v.file_path, a.account_name
                   FROM scheduled_posts sp
                   JOIN videos v ON sp.video_id = v.id
                   JOIN accounts a ON sp.account_id = a.id
                   WHERE sp.status = ? ORDER BY sp.scheduled_at""",
                (status,)
            ).fetchall()
        return conn.execute(
            """SELECT sp.*, v.title, v.file_path, a.account_name
               FROM scheduled_posts sp
               JOIN videos v ON sp.video_id = v.id
               JOIN accounts a ON sp.account_id = a.id
               ORDER BY sp.scheduled_at"""
        ).fetchall()


def get_posts_for_date(date_str: str):
    with get_connection() as conn:
        return conn.execute(
            """SELECT sp.*, v.title, a.account_name
               FROM scheduled_posts sp
               JOIN videos v ON sp.video_id = v.id
               JOIN accounts a ON sp.account_id = a.id
               WHERE DATE(sp.scheduled_at) = ?
               ORDER BY sp.scheduled_at""",
            (date_str,)
        ).fetchall()


def get_dates_with_posts():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT DATE(scheduled_at) as d FROM scheduled_posts"
        ).fetchall()
        return [row["d"] for row in rows]


def add_scheduled_post(video_id: int, account_id: int, scheduled_at: str) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO scheduled_posts (video_id, account_id, scheduled_at) VALUES (?, ?, ?)",
            (video_id, account_id, scheduled_at)
        )
        return cur.lastrowid


def update_post_status(post_id: int, status: str, error_message=None,
                        youtube_video_id=None, post_url=None):
    with get_connection() as conn:
        conn.execute(
            """UPDATE scheduled_posts
               SET status=?, error_message=?, youtube_video_id=?, post_url=?
               WHERE id=?""",
            (status, error_message, youtube_video_id, post_url, post_id)
        )


def delete_scheduled_post(post_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM scheduled_posts WHERE id = ?", (post_id,))


def reschedule_post(post_id: int, new_datetime: str):
    with get_connection() as conn:
        conn.execute(
            "UPDATE scheduled_posts SET scheduled_at = ?, status = 'pending' WHERE id = ?",
            (new_datetime, post_id)
        )


def get_scheduled_post(post_id: int):
    with get_connection() as conn:
        return conn.execute(
            """SELECT sp.*, v.title, v.file_path, v.description, v.tags,
                      v.thumbnail_path, v.privacy, v.video_type,
                      a.account_name, a.credentials_json
               FROM scheduled_posts sp
               JOIN videos v ON sp.video_id = v.id
               JOIN accounts a ON sp.account_id = a.id
               WHERE sp.id = ?""",
            (post_id,)
        ).fetchone()
