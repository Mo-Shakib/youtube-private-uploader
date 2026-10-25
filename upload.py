import argparse
import sqlite3
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from history import credential_key, export_history, find_duplicate, fingerprint, open_database, record_upload, reset_history, show_history
from playlists import authenticate as authenticate_playlists
from playlists import authorized_channel, create_private_playlist, ensure_video_in_playlist, owned_playlists, recorded_videos_match_channel


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


def run_upload(path, force=False, playlist_id=None, new_playlist=None, playlist_client=None):
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

    playlist_channel_verified = False
    playlist_channel_mismatch = False
    if playlist_id or new_playlist:
        try:
            playlist_client = playlist_client or authenticate_playlists()
            channel = authorized_channel(playlist_client)
            recent_ids = [row[0] for row in history.execute(
                "SELECT video_id FROM uploads WHERE account_key = ? ORDER BY id DESC LIMIT 5",
                (account_key,)
            ).fetchall()]
            if not recorded_videos_match_channel(playlist_client, channel["id"], recent_ids):
                raise ValueError("Playlist authorization does not match the channel used for recorded uploads")
            playlist_channel_verified = bool(recent_ids)
            print(f"Playlist channel: {channel.get('snippet', {}).get('title', channel['id'])}")
            if new_playlist and playlist_channel_verified:
                playlist_id = create_private_playlist(playlist_client, new_playlist)
                print(f"Created private playlist: https://www.youtube.com/playlist?list={playlist_id}")
            elif playlist_id and playlist_id not in {item["id"] for item in owned_playlists(playlist_client)}:
                raise ValueError("Playlist was not found among playlists owned by this channel")
        except Exception as error:
            history.close()
            print(f"Playlist setup failed: {error}")
            return 1

    def add_to_playlist(video_id):
        nonlocal playlist_id, playlist_channel_verified, playlist_channel_mismatch
        try:
            if not playlist_channel_verified:
                if not recorded_videos_match_channel(playlist_client, channel["id"], [video_id]):
                    playlist_channel_mismatch = True
                    raise ValueError("Playlist authorization cannot access the new upload on this channel")
                playlist_channel_verified = True
            if new_playlist and not playlist_id:
                playlist_id = create_private_playlist(playlist_client, new_playlist)
                print(f"Created private playlist: https://www.youtube.com/playlist?list={playlist_id}")
            if ensure_video_in_playlist(playlist_client, playlist_id, video_id):
                print(f"Added to playlist: https://www.youtube.com/playlist?list={playlist_id}")
                return 1, 0
            print("Already in playlist")
            return 0, 0
        except Exception as error:
            print(f"Could not add video {video_id} to playlist: {error}")
            return 0, 1

    successful = 0
    skipped = 0
    failed = 0
    playlist_added = 0
    playlist_failed = 0

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
                    if playlist_id or new_playlist:
                        added, error = add_to_playlist(duplicate[0])
                        playlist_added += added
                        playlist_failed += error
                        if playlist_channel_mismatch:
                            break
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
            if playlist_id or new_playlist:
                added, error = add_to_playlist(video_id)
                playlist_added += added
                playlist_failed += error
                if playlist_channel_mismatch:
                    break
    finally:
        history.close()

    print("\n----------------------------")
    print("UPLOAD SUMMARY")
    print(f"Successful: {successful}")
    print(f"Skipped: {skipped}")
    print(f"Failed: {failed}")
    if playlist_id or new_playlist:
        print(f"Added to playlist: {playlist_added}")
        print(f"Playlist additions failed: {playlist_failed}")
    print("----------------------------")

    return 1 if failed or playlist_failed else 0


def unescape_shell_path(value):
    """Turn a path pasted from a shell into the filename on disk.

    Terminal drag-and-drop and tab completion escape spaces and other
    characters with a backslash. The interactive prompt is not a shell, so
    those backslashes would otherwise be treated as part of the name.
    """
    if "\\" not in value:
        return value
    chars = []
    index = 0
    while index < len(value):
        if value[index] == "\\" and index + 1 < len(value):
            chars.append(value[index + 1])
            index += 2
            continue
        chars.append(value[index])
        index += 1
    return "".join(chars)


def normalize_interactive_path(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1]
    return unescape_shell_path(value)


def run_export():
    try:
        path, count = export_history()
    except (OSError, sqlite3.Error) as error:
        print(f"Could not export history: {error}")
        return 1
    print(f"Exported {count} upload(s) to {path}")
    return 0


def run_reset(confirmation):
    if confirmation != "DELETE":
        print("Reset cancelled. History was not changed.")
        return 0
    try:
        path, count = reset_history()
    except (OSError, sqlite3.Error, ValueError) as error:
        print(f"Could not reset history: {error}")
        return 1
    if count == 0:
        print("History is already empty. Existing Markdown export was left unchanged.")
        return 0
    print(f"Exported {count} upload(s) to {path}")
    print("Upload history has been reset.")
    return 0


def choose_playlist(questionary):
    action = questionary.select(
        "Add uploads to a playlist?",
        choices=["No playlist", "Choose existing playlist", "Create private playlist"]
    ).ask()
    if action is None:
        return None
    if action == "No playlist":
        return None, None, None
    if action == "Create private playlist":
        title = questionary.text("New private playlist name:").ask()
        return (None, title.strip(), None) if title and title.strip() else None

    try:
        client = authenticate_playlists()
        items = owned_playlists(client)
    except Exception as error:
        print(f"Could not list playlists: {error}")
        return None
    if not items:
        print("No selectable playlists found. Create a private playlist instead.")
        return None
    choices = [questionary.Choice(
        title=(f"{item.get('snippet', {}).get('title', 'Untitled')} "
               f"[{item.get('status', {}).get('privacyStatus', 'unknown')}, "
               f"{item.get('contentDetails', {}).get('itemCount', 0)} videos] "
               f"({item['id']})"),
        value=item["id"]
    ) for item in items]
    selected = questionary.select("Choose a playlist:", choices=choices).ask()
    return (selected, None, client) if selected else None


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
            choices=["Upload a video", "Upload a folder", "View upload history",
                     "Export history as Markdown", "Reset upload history", "Exit"]
        ).ask()
        if choice in (None, "Exit"):
            return 0
        if choice == "View upload history":
            try:
                show_history()
            except (OSError, sqlite3.Error) as error:
                print(f"Could not read history: {error}")
            continue
        if choice == "Export history as Markdown":
            run_export()
            continue
        if choice == "Reset upload history":
            confirmation = questionary.text("Type DELETE to export and reset all upload history:").ask()
            run_reset(confirmation)
            continue
        path = questionary.text("Path to video:" if choice == "Upload a video" else "Path to folder:").ask()
        if path:
            selection = choose_playlist(questionary)
            if selection is not None:
                playlist_id, new_playlist, client = selection
                run_upload(normalize_interactive_path(path), playlist_id=playlist_id,
                           new_playlist=new_playlist, playlist_client=client)


def main():
    parser = argparse.ArgumentParser(description="Upload videos privately to YouTube")
    parser.add_argument("path", nargs="?", help="Video file or directory")
    parser.add_argument("--history", action="store_true", help="Show recent uploads")
    parser.add_argument("--export-history", action="store_true", help="Export all history to upload-history.md")
    parser.add_argument("--reset-history", action="store_true", help="Export and reset history after typing DELETE")
    parser.add_argument("--limit", type=int, default=20, help="History rows to show (default: 20)")
    parser.add_argument("--force", action="store_true", help="Upload even if already in history")
    playlist_group = parser.add_mutually_exclusive_group()
    playlist_group.add_argument("--playlist-id", help="Add uploads to an existing owned playlist")
    playlist_group.add_argument("--new-playlist", help="Create a private playlist for these uploads")
    args = parser.parse_args()

    if args.limit < 1:
        parser.error("--limit must be at least 1")
    if args.playlist_id is not None and not args.playlist_id.strip():
        parser.error("--playlist-id cannot be empty")
    if args.new_playlist is not None and not args.new_playlist.strip():
        parser.error("--new-playlist cannot be empty")
    if (args.playlist_id or args.new_playlist) and not args.path:
        parser.error("playlist options require a video file or directory")
    if args.reset_history:
        if args.history or args.export_history or args.path or args.force:
            parser.error("--reset-history cannot be combined with other actions")
        if not sys.stdin.isatty():
            print("Reset requires an interactive terminal to type DELETE.")
            return 2
        try:
            confirmation = input("Type DELETE to export and reset all upload history: ")
        except (EOFError, KeyboardInterrupt):
            print("\nReset cancelled. History was not changed.")
            return 0
        return run_reset(confirmation)
    if args.export_history:
        if args.history or args.path or args.force:
            parser.error("--export-history cannot be combined with --history, a path, or --force")
        return run_export()
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
        return run_upload(args.path, args.force, playlist_id=args.playlist_id,
                          new_playlist=args.new_playlist)
    if args.force:
        parser.error("--force requires a path")
    return interactive_menu()


if __name__ == "__main__":
    sys.exit(main())
