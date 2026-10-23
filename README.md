# YouTube Private Uploader

A lightweight Python CLI tool for uploading videos to YouTube as **private videos** using the YouTube Data API v3.

Upload individual videos or entire directories directly from your terminal. The tool automatically uses filenames as video titles, handles Google OAuth authentication, displays upload progress, and reports successful or failed uploads.

## Features

- 🔒 **Private by Default:** All videos are uploaded with private visibility.
- 📁 **Batch Uploads:** Upload a single video or multiple videos from a directory.
- 🏷️ **Automatic Titles:** Uses the original filename (without extension) as the YouTube video title.
- 🔑 **OAuth 2.0 Authentication:** Secure Google authentication with locally cached credentials.
- 📊 **Upload Progress:** Displays upload progress in the terminal.
- ✅ **Upload Reports:** Shows successful and failed uploads.
- 🔗 **Video Links:** Returns a YouTube URL for each successful upload.
- 🧾 **Upload History:** Records successful uploads in a local SQLite database.
- ⏭️ **Duplicate Detection:** Skips videos already uploaded with the current OAuth grant, even after a rename or move.
- ⌨️ **Interactive Menu:** Run without arguments to select actions with arrow keys.
- 💻 **Cross-Platform:** Compatible with macOS, Linux, and Windows.

## Requirements

- Python 3.9 or newer
- Google account with a YouTube channel
- Google Cloud project
- YouTube Data API v3 enabled
- OAuth 2.0 Desktop Client credentials

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/mo-shakib/youtube-private-uploader.git
cd youtube-private-uploader
```

### 2. Create a virtual environment

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows**

```powershell
python -m venv .venv
.venv\Scripts\activate
```

### 3. Install dependencies

Install the Python packages listed in `requirements.txt`:

```bash
python -m pip install -r requirements.txt
```

## Google Cloud Configuration

### Step 1: Create a Google Cloud project

1. Visit [Google Cloud Console](https://console.cloud.google.com/).
2. Click **New Project**.
3. Name the project `YouTube Private Uploader`.
4. Create and select the project.

### Step 2: Enable YouTube Data API v3

1. Navigate to **APIs & Services → Library**.
2. Search for `YouTube Data API v3`.
3. Click **Enable**.

### Step 3: Configure OAuth consent

1. Open **Google Auth Platform → Branding**.
2. Configure the application name and support email.
3. Set the audience to **External**.
4. Add your Google account under **Audience → Test users**.
5. Under **Data Access**, configure the following OAuth scope:

```text
https://www.googleapis.com/auth/youtube.upload
```

### Step 4: Create OAuth credentials

1. Navigate to **Google Auth Platform → Clients**.
2. Click **Create Client**.
3. Select **Desktop app**.
4. Name the client `YouTube Private Uploader`.
5. Download the OAuth credentials JSON file.
6. Rename it to `client_secret.json`.
7. Place it in the project's root directory.

**Never commit OAuth credentials or authentication tokens to a public repository.**

## Project Structure

```text
youtube-private-uploader/
├── ytupload.py           # Recommended command-line entry point
├── upload.py             # Upload implementation and original command
├── history.py             # Local history and duplicate detection
├── requirements.txt      # Python dependencies
├── client_secret.json    # Google OAuth client credentials
├── token.json            # Generated automatically
├── .venv/                # Python virtual environment
├── .gitignore
├── LICENSE
└── README.md
```

The `token.json` file is automatically generated after your first successful authentication.

## Usage

### Upload a single video

```bash
python3 ytupload.py video.mp4
```

You can also provide an absolute path:

```bash
python3 ytupload.py ~/Movies/vacation.mp4
```

The filename becomes the YouTube title.

**Example:**

```text
Filename: Summer Vacation 2026.mp4
YouTube Title: Summer Vacation 2026
Visibility: Private
```

### Upload an entire directory

```bash
python3 ytupload.py ~/Movies/Vacation
```

Example directory:

```text
Vacation/
├── Day 1.mp4
├── Day 2.mov
├── Beach Sunset.mp4
└── Hotel Tour.mp4
```

All supported video files directly inside the specified directory will be uploaded individually.

### Interactive menu and history

Run `python3 ytupload.py` in a terminal to select **Upload a video**, **Upload a folder**, or **View upload history** with the arrow keys. The path-based commands above still work without the menu.

The original `python3 upload.py` command still works. `ytupload.py` runs the same implementation through a shorter entry point.

To view recent uploads directly:

```bash
python3 ytupload.py --history
python3 ytupload.py --history --limit 50
```

History appears as a table with upload time, Title (filename), YouTube URL, and local profile. Filenames longer than 50 characters show their first 50 characters followed by `.....`.

After a successful upload, the tool records the file's SHA-256 fingerprint, name, path, upload time, YouTube video ID, and URL. On later runs, it skips matching file contents and prints the existing URL. A changed file can be uploaded again. To intentionally upload an unchanged file again, use `python3 ytupload.py --force video.mp4`.

History is stored outside the repository: `~/Library/Application Support/youtube-private-uploader/history.db` on macOS, `%APPDATA%\youtube-private-uploader\history.db` on Windows, or `${XDG_DATA_HOME:-~/.local/share}/youtube-private-uploader/history.db` on Linux. Set `YTUPLOAD_HISTORY_DB` to use another path. Back up this file if you want to preserve the history. It stores no video contents or OAuth tokens.

Only successful uploads made by this version of the tool are recorded. Existing YouTube videos and uploads made before this feature are not discovered automatically. Duplicate checks are scoped to the current OAuth grant; reauthorizing may create a new history profile. If an upload reaches YouTube but the result is lost to a network error, check YouTube Studio before rerunning it.

### Supported file extensions

The script recognizes:

```text
.mp4
.mov
.mkv
.avi
.webm
.m4v
```

Actual upload compatibility depends on YouTube's supported video formats.

## Authentication

The first time you run the uploader:

1. Your browser opens Google's OAuth authorization page.
2. Sign in with your Google account.
3. Select your YouTube channel if prompted.
4. Grant the requested upload permission.
5. The application saves authentication credentials in `token.json`.

Subsequent uploads reuse the saved credentials.

### Reauthenticate or switch channels

Delete the existing token:

```bash
rm token.json
```

Run the uploader again:

```bash
python3 ytupload.py video.mp4
```

Google will request authorization again.

**Note:** If your Google account has multiple YouTube channels, ensure that you authorize the intended channel.

## Example Output

```text
Uploading: vacation
Progress: 100%

SUCCESS: vacation
URL: https://youtu.be/XXXXXXXXXXX
Privacy: Private

----------------------------
UPLOAD SUMMARY
Successful: 1
Failed: 0
----------------------------
```

For directory uploads, the script processes each supported video and displays a final summary.

## Viewing Uploaded Videos

Private videos do not appear on your channel's public-facing Home or Videos tabs.

To access them:

1. Open [YouTube Studio](https://studio.youtube.com/).
2. Select the correct YouTube channel.
3. Navigate to **Content → Videos**.
4. Find your uploaded videos with **Private** visibility.

You can also open the video URLs returned by the script while authenticated to the authorized YouTube channel.

## API Quotas and Limitations

The YouTube Data API is available without charge within its standard quota allocation.

However, several limitations apply:

| Feature | Limit |
|---|---|
| API access | Free within standard quota |
| Private uploads | Supported |
| Maximum upload size | 256 GB |
| Maximum video duration | 12 hours for verified accounts |
| Unverified account duration | 15 minutes |
| API upload quota | Subject to Google Cloud project limits |
| Total storage | No published fixed storage capacity |

Google may impose additional daily upload limits based on account history, verification status, and API usage.

### OAuth Testing Mode

Google OAuth applications in Testing mode generally issue refresh tokens that expire after seven days when requesting YouTube upload permissions.

If authentication expires, delete `token.json` and authenticate again.

### Private Upload Restriction

Videos uploaded through unverified API projects created after July 28, 2020, are restricted to private visibility until the project completes Google's required API compliance audit.

This does not prevent the tool from being used for private video uploads.

## Security

The project uses OAuth 2.0 rather than storing your Google account password.

Keep the following files private:

- `client_secret.json`: Contains Google OAuth client configuration.
- `token.json`: Contains access and refresh tokens.

### Recommended .gitignore

```gitignore
# Authentication
client_secret.json
token.json

# Virtual environment
.venv/
venv/

# Python
__pycache__/
*.py[cod]

# macOS
.DS_Store

# IDE
.vscode/
.idea/
```

Never share your authentication tokens or commit them to version control.

## Known Limitations

The current implementation has a few limitations:

- No automatic retries after failed uploads.
- No persistent resumable session recovery after restarting the script.
- Directory uploads are not recursive.
- Uploaded videos are always private.
- Authentication is tied to the authorized YouTube channel.
- No automatic deletion or archiving of local files.

## Troubleshooting

### Authentication failed: Expecting value

This usually indicates an empty or malformed JSON file.

If `token.json` is empty or corrupted, delete it:

```bash
rm -f token.json
```

Then rerun the uploader.

### Error 403: Access Denied

Check that:

- YouTube Data API v3 is enabled.
- Your Google account is listed as an OAuth test user.
- The correct OAuth permissions are configured.
- Your Google account has access to a YouTube channel.

### Error 400: redirect_uri_mismatch

Ensure that your OAuth client was created with the application type **Desktop app**.

### Video not visible on channel

Private videos are not displayed on public-facing channel pages.

Open **YouTube Studio → Content** to view uploaded private videos.

## Roadmap

Potential future improvements:

- [x] SQLite-based upload history
- [x] Duplicate video detection
- [ ] Automatic retry mechanism
- [ ] Persistent resumable uploads
- [ ] Recursive directory uploads
- [ ] Multiple YouTube channel profiles
- [ ] Automatic folder monitoring
- [ ] Upload logs and statistics
- [ ] Installable CLI command (`ytupload`)
- [ ] Optional upload scheduling

## Disclaimer

This project uses YouTube as a convenient platform for privately hosting personal videos.

**YouTube should not be treated as a guaranteed backup or archival storage service.**

YouTube processes and transcodes uploaded videos, which may affect quality and metadata. Content remains subject to YouTube's Terms of Service, community guidelines, and applicable account restrictions.

For irreplaceable videos, maintain an additional backup of the original files.

## References

- [YouTube Data API v3](https://developers.google.com/youtube/v3)
- [Upload a Video](https://developers.google.com/youtube/v3/guides/uploading_a_video)
- [OAuth 2.0 for Desktop Applications](https://developers.google.com/identity/protocols/oauth2/native-app)
- [YouTube API Quota](https://developers.google.com/youtube/v3/determine_quota_cost)
- [YouTube Studio](https://studio.youtube.com/)

## License

MIT License

Copyright (c) 2026 Mohamed Shakib

---

**Built with Python and YouTube Data API v3.**
