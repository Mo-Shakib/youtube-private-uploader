"""Local upload history. No OAuth credentials or video data are stored here."""

import hashlib
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

EXPORT_FILE = Path(__file__).resolve().parent / "upload-history.md"


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


def history_rows(limit=None):
    db = open_database()
    try:
        query = """SELECT uploaded_at, file_name, video_id, account_key
                   FROM uploads ORDER BY id DESC"""
        if limit is None:
            return db.execute(query).fetchall()
        return db.execute(query + " LIMIT ?", (limit,)).fetchall()
    finally:
        db.close()


def display_name(file_name):
    name = file_name.replace("\n", " ").replace("\r", " ")
    return name[:50] + "....." if len(name) > 50 else name


def export_time_label():
    now = datetime.now().astimezone()
    hour = now.hour % 12 or 12
    period = "AM" if now.hour < 12 else "PM"
    offset = now.strftime("%z")
    return (f"{now.day} {now.strftime('%B')} {now.year} at "
            f"{hour}:{now.minute:02d} {period} (UTC{offset[:3]}:{offset[3:]})")


def show_history(limit=20):
    rows = history_rows(limit)
    if not rows:
        print("No uploads recorded yet.")
        return
    widths = (16, 55, 28, 8)
    border = "+" + "+".join("-" * (width + 2) for width in widths) + "+"

    def print_row(values):
        print("| " + " | ".join(f"{value:<{width}}" for value, width in zip(values, widths)) + " |")

    print("\nUPLOAD HISTORY (newest first)")
    print(border)
    print_row(("Uploaded", "Title (filename)", "YouTube URL", "Profile"))
    print(border)
    for uploaded_at, file_name, video_id, account_key in rows:
        date = datetime.fromisoformat(uploaded_at).astimezone().strftime("%Y-%m-%d %H:%M")
        print_row((date, display_name(file_name), f"https://youtu.be/{video_id}", account_key[:8]))
        print(border)


def export_history(rows=None):
    if rows is None:
        rows = history_rows()
    lines = [
        "# YouTube Private Uploader — Upload History",
        "",
        "| Uploaded | Title (filename) | YouTube URL | Profile |",
        "| --- | --- | --- | --- |",
    ]
    for uploaded_at, file_name, video_id, account_key in rows:
        date = datetime.fromisoformat(uploaded_at).astimezone().strftime("%Y-%m-%d %H:%M")
        title = display_name(file_name).replace("\\", "\\\\").replace("|", "\\|")
        url = f"https://youtu.be/{video_id}"
        lines.append(f"| {date} | {title} | [{url}]({url}) | {account_key[:8]} |")
    if not rows:
        lines.extend(("", "No uploads recorded yet."))
    lines.extend(("", f"**Exported:** {export_time_label()}"))

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=EXPORT_FILE.parent,
                                         prefix=".upload-history-", suffix=".tmp", delete=False) as output:
            temp_path = Path(output.name)
            output.write("\n".join(lines) + "\n")
        os.replace(temp_path, EXPORT_FILE)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    return EXPORT_FILE, len(rows)


def reset_history():
    db = open_database()
    try:
        # This prevents another local process from uploading between the
        # backup snapshot and deletion.
        db.execute("BEGIN IMMEDIATE")
        rows = db.execute("""SELECT uploaded_at, file_name, video_id, account_key
                             FROM uploads ORDER BY id DESC""").fetchall()
        if not rows:
            db.rollback()
            return None, 0
        path, count = export_history(rows)
        db.execute("DELETE FROM uploads")
        db.commit()
        return path, count
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
