"""Optional YouTube playlist access, authorized separately from uploads."""

import json
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl"
BASE_DIR = Path(__file__).resolve().parent
TOKEN_FILE = BASE_DIR / "playlist_token.json"
CLIENT_FILE = BASE_DIR / "client_secret.json"


def authenticate():
    credentials = None
    if TOKEN_FILE.exists():
        saved = json.loads(TOKEN_FILE.read_text())
        if SCOPE in saved.get("scopes", []):
            credentials = Credentials.from_authorized_user_info(saved, [SCOPE])

    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_FILE), [SCOPE])
            credentials = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(credentials.to_json())
        if os.name != "nt":
            TOKEN_FILE.chmod(0o600)

    return build("youtube", "v3", credentials=credentials, cache_discovery=False)


def authorized_channel(youtube):
    response = youtube.channels().list(part="snippet,contentDetails", mine=True).execute()
    channels = response.get("items", [])
    if not channels:
        raise RuntimeError("No YouTube channel was found for playlist authorization")
    return channels[0]


def recorded_videos_match_channel(youtube, channel_id, video_ids):
    if not video_ids:
        return True
    response = youtube.videos().list(part="snippet", id=",".join(video_ids)).execute()
    items = response.get("items", [])
    return bool(items) and all(
        item.get("snippet", {}).get("channelId") == channel_id for item in items
    )


def owned_playlists(youtube):
    channel = authorized_channel(youtube)
    system_uploads_id = channel.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")

    results = []
    page_token = None
    while True:
        page = youtube.playlists().list(
            part="snippet,status,contentDetails", mine=True,
            maxResults=50, pageToken=page_token
        ).execute()
        results.extend(item for item in page.get("items", []) if item.get("id") != system_uploads_id)
        page_token = page.get("nextPageToken")
        if not page_token:
            return results


def create_private_playlist(youtube, title):
    title = title.strip()
    if not title:
        raise ValueError("Playlist title cannot be empty")
    response = youtube.playlists().insert(
        part="snippet,status",
        body={"snippet": {"title": title}, "status": {"privacyStatus": "private"}}
    ).execute()
    return response["id"]


def ensure_video_in_playlist(youtube, playlist_id, video_id):
    existing = youtube.playlistItems().list(
        part="id", playlistId=playlist_id, videoId=video_id, maxResults=1
    ).execute()
    if existing.get("items"):
        return False
    youtube.playlistItems().insert(
        part="snippet",
        body={"snippet": {
            "playlistId": playlist_id,
            "resourceId": {"kind": "youtube#video", "videoId": video_id}
        }}
    ).execute()
    return True
