# YouTube Private Uploader

Upload videos to your YouTube channel as **private** videos from the terminal. Run an interactive menu with arrow keys, or pass a file or folder path directly.

The uploader uses the filename as the video title. It remembers successful uploads, skips duplicate files, and can add a batch to an existing or new private playlist.

## Get started

You need Python 3.9 or newer, a Google account with a YouTube channel, and a Google Cloud OAuth desktop client. If this is your first time, follow the [step-by-step Google Cloud setup guide](GOOGLE_CLOUD_SETUP.md). It explains how to download `client_secret.json` and enable playlist access.

### 1. Download and install

```bash
git clone https://github.com/Mo-Shakib/youtube-private-uploader.git
cd youtube-private-uploader
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

On Windows, create the environment with `python -m venv .venv` and activate it with `.\.venv\Scripts\Activate.ps1` in PowerShell. Then run the same `python -m pip install -r requirements.txt` command. Use `python` in place of `python3` in the examples below.

### 2. Add your Google credentials

Download a **Desktop app** OAuth JSON file using the [Google Cloud setup guide](GOOGLE_CLOUD_SETUP.md). Rename it to `client_secret.json` and place it beside `ytupload.py`.

### 3. Start the menu

```bash
python3 ytupload.py
```

Use the arrow keys to choose **Upload a video** or **Upload a folder**, enter the path, and choose whether to use a playlist. On the first use, your browser opens for Google authorization. Choose the YouTube channel you want to use.

If a path contains spaces, you can paste it with surrounding quotes; the menu accepts both quoted and unquoted paths.

## What you can do

| Task | Command or menu action |
| --- | --- |
| Open the arrow-key menu | `python3 ytupload.py` |
| Upload one video | `python3 ytupload.py "My Video.mp4"` |
| Upload files in a folder | `python3 ytupload.py ~/Movies/Vacation` |
| View upload history | `python3 ytupload.py --history` |
| View more history rows | `python3 ytupload.py --history --limit 50` |
| Export history to Markdown | `python3 ytupload.py --export-history` |
| Reset history after an export | `python3 ytupload.py --reset-history` |

The tool reads supported videos directly inside a folder; it does not search subfolders. Supported extensions are `.mp4`, `.mov`, `.mkv`, `.avi`, `.webm`, and `.m4v`. YouTube determines whether a particular video file can be processed.

The original `python3 upload.py` entry point still works. `ytupload.py` is the recommended command.

### Playlists

After entering a path in the interactive menu, select **No playlist**, **Choose existing playlist**, or **Create private playlist**. The chosen playlist applies to every video in that run. You can also use a direct command:

```bash
python3 ytupload.py ~/Movies/Vacation --playlist-id PLAYLIST_ID
python3 ytupload.py ~/Movies/Vacation --new-playlist "Vacation 2026"
```

Find an existing playlist ID at the end of its YouTube URL, after `list=`. The playlist must belong to the authorized channel. A new playlist is private. Videos remain private even if you choose an existing playlist with different visibility.

Playlist access asks for a separate Google authorization the first time you use it. The [setup guide](GOOGLE_CLOUD_SETUP.md#6-add-playlist-permission-optional) explains the extra permission. If a video is already in upload history, the tool skips uploading it again and can still add it to the playlist. If adding it fails, the upload stays in history; rerun the same command to retry the playlist step.

### History and duplicates

Successful uploads appear in a terminal table with the upload time, filename, YouTube link, and local profile. The tool compares file contents, so renaming or moving a video does not bypass duplicate detection for the same OAuth grant. To upload an unchanged file again intentionally, add `--force`:

```bash
python3 ytupload.py --force video.mp4
```

**Export history** writes `upload-history.md` in the project folder. It includes the full table and a readable export date and time. Exporting again replaces that file. **Reset history** first exports it, then requires you to type `DELETE` exactly before clearing the local database. Resetting does not delete videos from YouTube, but later runs may upload those files again.

History is stored outside the repository:

| System | Default history file |
| --- | --- |
| macOS | `~/Library/Application Support/youtube-private-uploader/history.db` |
| Windows | `%APPDATA%\youtube-private-uploader\history.db` |
| Linux | `~/.local/share/youtube-private-uploader/history.db` (or `$XDG_DATA_HOME/youtube-private-uploader/history.db`) |

You can set `YTUPLOAD_HISTORY_DB` to use another location. Back up this database if you want to keep your duplicate records. Only uploads made with this tool are recorded; it does not import videos already on YouTube. If a network error occurs after YouTube receives an upload, check [YouTube Studio](https://studio.youtube.com/) before retrying.

## Authentication and privacy

The uploader saves two separate local OAuth tokens:

| File | Used for |
| --- | --- |
| `token.json` | Private video uploads |
| `playlist_token.json` | Listing, creating, and updating playlists, when requested |

Both token files and `client_secret.json` are excluded from Git. Keep them private. If you need to authorize a different channel, remove the relevant token file and run the command again. Use the same channel for uploads and playlists. Reauthorizing uploads may start a new duplicate history profile.

Private uploads do not appear on the public channel page. View them in [YouTube Studio → Content](https://studio.youtube.com/) while signed in to the correct channel. Keep a separate copy of any irreplaceable original video files.

## Troubleshooting

| Problem | What to check |
| --- | --- |
| `Path does not exist` | Check the path and drive connection. In the menu, pasted paths may include surrounding quotes. |
| Google says access is denied | Confirm the YouTube Data API is enabled and your Google account is an OAuth test user. See the [setup guide](GOOGLE_CLOUD_SETUP.md#troubleshooting). |
| `redirect_uri_mismatch` | Download credentials for an OAuth client whose type is **Desktop app**. |
| Wrong YouTube channel | Remove the relevant token file and authorize again, selecting the intended channel. |
| Token is empty, malformed, or expired | Remove the affected `token.json` or `playlist_token.json` and authorize again. OAuth apps in Testing mode may require reauthorization after seven days. |
| Playlist addition failed | Confirm the playlist belongs to the authorized channel, then rerun the command. A successful upload will be skipped and the playlist addition retried. |

Google Cloud's quota and YouTube's account limits can also restrict uploads. Check your project's [YouTube Data API quota](https://console.cloud.google.com/apis/api/youtube.googleapis.com/quotas) and the API error message when an upload fails.

## License

[MIT](LICENSE)
