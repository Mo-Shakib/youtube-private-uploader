"""Local upload history. No OAuth credentials or video data are stored here."""

import hashlib
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


def database_path():
    override = os.environ.get("YTUPLOAD_HISTORY_DB")
    if override:
        return Path(override).expanduser()
    if sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    elif os.name == "nt":
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return root / "youtube-private-uploader" / "history.db"


def open_database():
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    try:
        if os.name != "nt":
            path.chmod(0o600)
        db.execute("""
            CREATE TABLE IF NOT EXISTS uploads (
                id INTEGER PRIMARY KEY,
                account_key TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_name TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                title TEXT NOT NULL,
                video_id TEXT NOT NULL,
                uploaded_at TEXT NOT NULL
            )
        """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS uploads_duplicate_idx
            ON uploads (account_key, sha256, size_bytes)
        """)
        db.commit()
    except Exception:
        db.close()
        raise
    return db


def credential_key(credentials):
    if not credentials.refresh_token:
        raise ValueError("OAuth token has no refresh token; reauthenticate before uploading")
    # A change of OAuth grant creates a new deduplication namespace. Store no token.
    value = f"{credentials.client_id}:{credentials.refresh_token}".encode()
    return hashlib.sha256(value).hexdigest()


def fingerprint(path):
    before = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as video:
        for chunk in iter(lambda: video.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise OSError("File changed while being read; try again when it is stable")
    return digest.hexdigest(), after.st_size, after.st_mtime_ns


def find_duplicate(db, account_key, sha256, size_bytes):
    return db.execute("""
        SELECT video_id FROM uploads
        WHERE account_key = ? AND sha256 = ? AND size_bytes = ?
        ORDER BY id DESC LIMIT 1
    """, (account_key, sha256, size_bytes)).fetchone()


def record_upload(db, account_key, path, sha256, size_bytes, video_id):
    db.execute("""
        INSERT INTO uploads (
            account_key, file_path, file_name, sha256, size_bytes,
            title, video_id, uploaded_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        account_key, str(path.resolve()), path.name, sha256, size_bytes,
        path.stem, video_id, datetime.now(timezone.utc).isoformat()
    ))
    db.commit()


def show_history(limit=20):
    db = open_database()
    try:
        rows = db.execute("""
            SELECT uploaded_at, file_name, video_id, account_key
            FROM uploads ORDER BY id DESC LIMIT ?
        """, (limit,)).fetchall()
    finally:
        db.close()
    if not rows:
        print("No uploads recorded yet.")
        return
    print("\nUPLOAD HISTORY (newest first)")
    for uploaded_at, file_name, video_id, account_key in rows:
        date = datetime.fromisoformat(uploaded_at).astimezone().strftime("%Y-%m-%d %H:%M")
        print(f"{date}  {file_name}  https://youtu.be/{video_id}  [profile {account_key[:8]}]")
