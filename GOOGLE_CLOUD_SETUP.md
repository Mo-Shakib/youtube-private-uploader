# Google Cloud setup for YouTube Private Uploader

Follow this guide once to connect the CLI to your own YouTube channel. You will enable the YouTube Data API, create a Google OAuth **Desktop app** client, and download one JSON file. Playlist support needs one additional permission.

You need a Google account that can access the YouTube channel you intend to upload to. Keep the [Google Cloud Console](https://console.cloud.google.com/) open while following the steps. Console labels can change; look for the named Google Auth Platform sections if a menu looks different.

## 1. Create or select a Google Cloud project

1. Open [Google Cloud Console](https://console.cloud.google.com/) and sign in.
2. Use the project selector at the top of the page. Choose an existing project for this uploader or select **New Project**.
3. Give a new project a recognizable name, such as `YouTube Private Uploader`, and create it.
4. Confirm that the intended project name appears in the project selector before continuing. The API and OAuth client must be in the same project.

## 2. Enable YouTube Data API v3

1. In the navigation menu, open **APIs & Services → Library**.
2. Search for **YouTube Data API v3**.
3. Open its page and click **Enable**. If the button says **Manage**, it is already enabled.

The uploader uses OAuth credentials. You do **not** need to create an API key.

## 3. Set up the OAuth consent screen

1. Open **Google Auth Platform → Branding**. If the console says the platform is not configured, click **Get Started**.
2. Enter an app name, such as `YouTube Private Uploader`, and choose a user support email.
3. Fill in the contact email and complete any remaining setup prompts. Save or create the app.
4. Open **Google Auth Platform → Audience**. For a personal Google account, choose **External**. The **Internal** choice is for eligible Google Workspace organizations.
5. Keep the app in **Testing** while setting up personal use. Under **Test users**, add the Google account that can manage your YouTube channel, then save.

If you manage a YouTube Brand Account, add your own Google sign-in as the test user; choose the Brand Account's channel when Google asks which YouTube account to authorize.

## 4. Add the upload permission

1. Open **Google Auth Platform → Data Access**.
2. Click **Add or remove scopes**.
3. Find and select this YouTube Data API scope:

   ```text
   https://www.googleapis.com/auth/youtube.upload
   ```

4. Update or save the scope selection. Confirm that it appears on the Data Access page.

This is the permission used by ordinary private uploads.

## 5. Create and download a Desktop app client

1. Open **Google Auth Platform → Clients**.
2. Click **Create client** (or **Create OAuth client**).
3. Set **Application type** to **Desktop app**, give the client a name, and create it.
4. Download its JSON credentials file. It may have a name such as `client_secret_123456.json`.
5. Rename that downloaded file to **`client_secret.json`** and place it in the project folder beside `ytupload.py`.

The important files should be together like this (other project files are omitted):

```text
youtube-private-uploader/
├── client_secret.json
├── ytupload.py
├── upload.py
├── playlists.py
├── history.py
└── requirements.txt
```

The uploader creates `token.json` after upload authorization and `playlist_token.json` after playlist authorization. Neither exists in a fresh clone. Keep the credential and token files private; they are listed in this project's `.gitignore`.

## 6. Add playlist permission (optional)

Do this if you want to choose an existing playlist or create a private one during upload.

1. Return to **Google Auth Platform → Data Access** in the same Cloud project.
2. Click **Add or remove scopes**.
3. Find and select this scope **in addition to** the upload scope:

   ```text
   https://www.googleapis.com/auth/youtube.force-ssl
   ```

4. Update or save, then confirm that **both** scopes are listed on Data Access.

Google describes `youtube.force-ssl` as broad permission to see, edit, and permanently delete YouTube videos, ratings, comments, and captions. The CLI requests it only when you choose a playlist feature, because adding a video to a playlist requires a permission that `youtube.upload` alone does not provide. The project stores this separate authorization in `playlist_token.json`.

## 7. Run the uploader and authorize the channel

From the project folder, with the Python dependencies installed, run:

```bash
python3 ytupload.py
```

1. Choose **Upload a video** or **Upload a folder** and enter a path.
2. For your first test, choose **No playlist**. Your browser opens Google's consent screen for the upload permission.
3. Sign in as the Google account added under **Test users**. If Google offers multiple YouTube channels, choose the intended channel and approve access.
4. For playlist use, start another upload through the menu and choose **Choose existing playlist** or **Create private playlist**. Google asks once for the additional playlist permission.

The CLI saves `token.json` for uploads and `playlist_token.json` for playlists. Later runs reuse them until they expire or are removed. The upload and playlist authorizations must point to the same YouTube channel.

You can also run a direct command:

```bash
python3 ytupload.py "/absolute/path/to/video.mp4"
```

Check your private upload in [YouTube Studio → Content](https://studio.youtube.com/).

## Troubleshooting

| Message or symptom | Fix |
| --- | --- |
| `access_denied` or `403: access_denied` during Google sign-in | Confirm the app is in Testing and your Google sign-in is listed under **Audience → Test users**. |
| `redirect_uri_mismatch` | Use a **Desktop app** OAuth client and its downloaded JSON file. |
| YouTube API is disabled or access is forbidden | Check that **YouTube Data API v3** is enabled in the same project as your OAuth client. |
| Playlist authorization or listing fails | Confirm `youtube.force-ssl` is saved under **Data Access** and authorize the intended channel again. |
| Authorization worked, then expired | Google says Testing-mode authorizations for these scopes can expire after seven days. Remove the affected `token.json` or `playlist_token.json` and authorize again. |
| The wrong channel was selected | Remove the affected token file and rerun the command so Google asks you to choose a channel again. |

Remove only the token you want to renew. Keep `client_secret.json` unless you are replacing the OAuth client. Avoid sharing any of these files.

## Google documentation

- [YouTube Data API Python quickstart](https://developers.google.com/youtube/data/quickstart/python)
- [Google Auth Platform setup](https://support.google.com/cloud/answer/15544987)
- [Manage OAuth audience and test users](https://support.google.com/cloud/answer/15549945)
- [Manage OAuth data access and scopes](https://support.google.com/cloud/answer/15549135)
- [YouTube OAuth scopes for desktop apps](https://developers.google.com/youtube/data/guides/auth/installed-apps)
- [Playlist item authorization requirements](https://developers.google.com/youtube/data/reference/rest/v3/playlistItems/insert)
