import argparse
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


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

    return build("youtube", "v3", credentials=credentials)


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


def main():
    parser = argparse.ArgumentParser(
        description="Upload videos privately to YouTube"
    )

    parser.add_argument(
        "path",
        help="Video file or directory"
    )

    args = parser.parse_args()
    path = Path(args.path).expanduser()

    if not path.exists():
        print("FAILED: Path does not exist")
        sys.exit(1)

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
        sys.exit(1)

    try:
        youtube = authenticate()
    except Exception as error:
        print(f"Authentication failed: {error}")
        sys.exit(1)

    successful = 0
    failed = 0

    for video in videos:
        try:
            upload_video(youtube, video)
            successful += 1

        except Exception as error:
            print(f"\nFAILED: {video.name}")
            print(f"Reason: {error}")
            failed += 1

    print("\n----------------------------")
    print("UPLOAD SUMMARY")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print("----------------------------")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()