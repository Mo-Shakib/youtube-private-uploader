import argparse
import sqlite3
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from history import credential_key, find_duplicate, fingerprint, open_database, record_upload, show_history


SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

BASE_DIR = Path(__file__).resolve().parent
TOKEN_FILE = BASE_DIR / "token.json"
CLIENT_FILE = BASE_DIR / "client_secret.json"

VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"
}


def authenticate():
    credentials = None

    if TOKEN_FILE.exists():
        credentials = Credentials.from_authorized_user_file(
            str(TOKEN_FILE), SCOPES
        )

    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CLIENT_FILE), SCOPES
            )
            credentials = flow.run_local_server(port=0)

        TOKEN_FILE.write_text(credentials.to_json())

    return build("youtube", "v3", credentials=credentials), credential_key(credentials)


def upload_video(youtube, file_path):
    title = file_path.stem

    print(f"\nUploading: {title}")

    media = MediaFileUpload(
        str(file_path),
        mimetype="video/*",
        chunksize=8 * 1024 * 1024,
        resumable=True
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": title,
                "description": "",
                "categoryId": "22"
            },
            "status": {
                "privacyStatus": "private",
                "selfDeclaredMadeForKids": False
            }
        },
        media_body=media
    )

    response = None

    while response is None:
        status, response = request.next_chunk()

        if status:
            progress = int(status.progress() * 100)
            print(f"\rProgress: {progress}%", end="", flush=True)

    video_id = response["id"]

    print(f"\nSUCCESS: {title}")
    print(f"URL: https://youtu.be/{video_id}")
    print("Privacy: Private")

    return video_id


def run_upload(path, force=False):
    path = Path(path).expanduser()

    if not path.exists():
        print("FAILED: Path does not exist")
        return 1

    if path.is_file():
        videos = [path]
    else:
        videos = sorted(
            file for file in path.iterdir()
            if file.is_file()
            and file.suffix.lower() in VIDEO_EXTENSIONS
        )

    if not videos:
        print("FAILED: No videos found")
        return 1

    try:
        history = open_database()
    except (OSError, sqlite3.Error) as error:
        print(f"Could not open upload history: {error}")
        return 1

    try:
        youtube, account_key = authenticate()
    except Exception as error:
        history.close()
        print(f"Authentication failed: {error}")
        return 1

    successful = 0
    skipped = 0
    failed = 0

    try:
        for video in videos:
            try:
                sha256, size_bytes, mtime_ns = fingerprint(video)
                # Hold a SQLite writer lock until this video's result is recorded.
                # A second local process cannot pass the duplicate check meanwhile.
                history.execute("BEGIN IMMEDIATE")
                duplicate = find_duplicate(history, account_key, sha256, size_bytes)
                if duplicate and not force:
                    print(f"\nSKIPPED: {video.name} (already uploaded)")
                    print(f"URL: https://youtu.be/{duplicate[0]}")
                    skipped += 1
                    history.commit()
                    continue
            except (OSError, sqlite3.Error) as error:
                history.rollback()
                print(f"\nFAILED: {video.name}\nReason: {error}")
                failed += 1
                continue

            try:
                video_id = upload_video(youtube, video)
            except Exception as error:
                history.rollback()
                print(f"\nFAILED: {video.name}\nReason: {error}")
                failed += 1
                continue

            try:
                current = video.stat()
                if (current.st_size, current.st_mtime_ns) != (size_bytes, mtime_ns):
                    raise OSError("Local file changed during upload")
                record_upload(history, account_key, video, sha256, size_bytes, video_id)
                successful += 1
            except (OSError, sqlite3.Error) as error:
                history.rollback()
                print(f"HISTORY ERROR: Uploaded video {video_id}, but could not record it: {error}")
                print("Check this YouTube URL before rerunning; the next run may upload it again.")
                return 1
    finally:
        history.close()

    print("\n----------------------------")
    print("UPLOAD SUMMARY")
    print(f"Successful: {successful}")
    print(f"Skipped: {skipped}")
    print(f"Failed: {failed}")
    print("----------------------------")

    return 1 if failed else 0


def normalize_interactive_path(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def interactive_menu():
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("A path or --history is required when running without a terminal.")
        return 2
    try:
        import questionary
    except ImportError:
        print("The interactive menu requires dependencies from requirements.txt.")
        return 1

    while True:
        choice = questionary.select(
            "What would you like to do?",
            choices=["Upload a video", "Upload a folder", "View upload history", "Exit"]
        ).ask()
        if choice in (None, "Exit"):
            return 0
        if choice == "View upload history":
            try:
                show_history()
            except (OSError, sqlite3.Error) as error:
                print(f"Could not read history: {error}")
            continue
        path = questionary.text("Path to video:" if choice == "Upload a video" else "Path to folder:").ask()
        if path:
            run_upload(normalize_interactive_path(path))


def main():
    parser = argparse.ArgumentParser(description="Upload videos privately to YouTube")
    parser.add_argument("path", nargs="?", help="Video file or directory")
    parser.add_argument("--history", action="store_true", help="Show recent uploads")
    parser.add_argument("--limit", type=int, default=20, help="History rows to show (default: 20)")
    parser.add_argument("--force", action="store_true", help="Upload even if already in history")
    args = parser.parse_args()

    if args.limit < 1:
        parser.error("--limit must be at least 1")
    if args.history:
        if args.path or args.force:
            parser.error("--history cannot be combined with a path or --force")
        try:
            show_history(args.limit)
            return 0
        except (OSError, sqlite3.Error) as error:
            print(f"Could not read history: {error}")
            return 1
    if args.path:
        return run_upload(args.path, args.force)
    if args.force:
        parser.error("--force requires a path")
    return interactive_menu()


if __name__ == "__main__":
    sys.exit(main())
