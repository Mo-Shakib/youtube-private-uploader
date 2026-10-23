import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

import history
import playlists
import upload


class PlaylistTests(unittest.TestCase):
    def test_owned_playlists_paginates_and_omits_system_uploads(self):
        client = MagicMock()
        client.channels.return_value.list.return_value.execute.return_value = {
            "items": [{"contentDetails": {"relatedPlaylists": {"uploads": "system-id"}}}]
        }
        client.playlists.return_value.list.return_value.execute.side_effect = [
            {"items": [{"id": "system-id"}, {"id": "first"}], "nextPageToken": "next"},
            {"items": [{"id": "second"}]},
        ]
        self.assertEqual([item["id"] for item in playlists.owned_playlists(client)],
                         ["first", "second"])

    def test_create_private_and_avoid_duplicate_playlist_item(self):
        client = MagicMock()
        client.playlists.return_value.insert.return_value.execute.return_value = {"id": "playlist-id"}
        self.assertEqual(playlists.create_private_playlist(client, "  Vacation  "), "playlist-id")
        body = client.playlists.return_value.insert.call_args.kwargs["body"]
        self.assertEqual(body["snippet"]["title"], "Vacation")
        self.assertEqual(body["status"]["privacyStatus"], "private")

        client.playlistItems.return_value.list.return_value.execute.return_value = {"items": [{"id": "existing"}]}
        self.assertFalse(playlists.ensure_video_in_playlist(client, "playlist-id", "video-id"))
        client.playlistItems.return_value.insert.assert_not_called()

        client.playlistItems.return_value.list.return_value.execute.return_value = {"items": []}
        self.assertTrue(playlists.ensure_video_in_playlist(client, "playlist-id", "video-id"))
        body = client.playlistItems.return_value.insert.call_args.kwargs["body"]
        self.assertEqual(body["snippet"]["resourceId"]["videoId"], "video-id")

    def test_recorded_uploads_must_match_playlist_channel(self):
        client = MagicMock()
        client.videos.return_value.list.return_value.execute.return_value = {
            "items": [{"snippet": {"channelId": "channel-a"}}]
        }
        self.assertTrue(playlists.recorded_videos_match_channel(client, "channel-a", ["video-id"]))
        self.assertFalse(playlists.recorded_videos_match_channel(client, "channel-b", ["video-id"]))

    def test_skipped_upload_can_be_added_to_playlist_without_reupload(self):
        with tempfile.TemporaryDirectory() as temp:
            video = Path(temp) / "video.mp4"
            video.write_bytes(b"video data")
            with patch.dict(os.environ, {"YTUPLOAD_HISTORY_DB": str(Path(temp) / "history.db")}):
                digest, size, _ = history.fingerprint(video)
                db = history.open_database()
                history.record_upload(db, "account", video, digest, size, "video-id")
                db.close()

                playlist_client = MagicMock()
                with patch.object(upload, "authenticate", return_value=(object(), "account")), \
                     patch.object(upload, "owned_playlists", return_value=[{"id": "playlist-id"}]), \
                     patch.object(upload, "upload_video") as send, \
                     patch.object(upload, "ensure_video_in_playlist", return_value=True) as add, \
                     redirect_stdout(io.StringIO()):
                    self.assertEqual(upload.run_upload(video, playlist_id="playlist-id",
                                                       playlist_client=playlist_client), 0)
                send.assert_not_called()
                add.assert_called_once_with(playlist_client, "playlist-id", "video-id")

    def test_playlist_failure_does_not_erase_successful_upload_history(self):
        with tempfile.TemporaryDirectory() as temp:
            video = Path(temp) / "video.mp4"
            video.write_bytes(b"video data")
            with patch.dict(os.environ, {"YTUPLOAD_HISTORY_DB": str(Path(temp) / "history.db")}):
                client = MagicMock()
                with patch.object(upload, "authenticate", return_value=(object(), "account")), \
                     patch.object(upload, "owned_playlists", return_value=[{"id": "playlist-id"}]), \
                     patch.object(upload, "upload_video", return_value="video-id"), \
                     patch.object(upload, "ensure_video_in_playlist", side_effect=RuntimeError("offline")), \
                     redirect_stdout(io.StringIO()):
                    self.assertEqual(upload.run_upload(video, playlist_id="playlist-id",
                                                       playlist_client=client), 1)
                db = history.open_database()
                try:
                    self.assertEqual(db.execute("SELECT video_id FROM uploads").fetchone()[0], "video-id")
                finally:
                    db.close()

    def test_channel_mismatch_stops_before_upload(self):
        with tempfile.TemporaryDirectory() as temp:
            video = Path(temp) / "video.mp4"
            video.write_bytes(b"video data")
            with patch.dict(os.environ, {"YTUPLOAD_HISTORY_DB": str(Path(temp) / "history.db")}):
                db = history.open_database()
                digest, size, _ = history.fingerprint(video)
                history.record_upload(db, "account", video, digest, size, "old-id")
                db.close()
                with patch.object(upload, "authenticate", return_value=(object(), "account")), \
                     patch.object(upload, "authorized_channel", return_value={"id": "other-channel"}), \
                     patch.object(upload, "recorded_videos_match_channel", return_value=False), \
                     patch.object(upload, "upload_video") as send, \
                     redirect_stdout(io.StringIO()):
                    self.assertEqual(upload.run_upload(video, playlist_id="playlist-id",
                                                       playlist_client=MagicMock()), 1)
                send.assert_not_called()

    def test_new_channel_mismatch_stops_batch_after_first_upload(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "videos"
            folder.mkdir()
            (folder / "first.mp4").write_bytes(b"first")
            (folder / "second.mp4").write_bytes(b"second")
            with patch.dict(os.environ, {"YTUPLOAD_HISTORY_DB": str(Path(temp) / "history.db")}):
                with patch.object(upload, "authenticate", return_value=(object(), "account")), \
                     patch.object(upload, "authorized_channel", return_value={"id": "other-channel"}), \
                     patch.object(upload, "owned_playlists", return_value=[{"id": "playlist-id"}]), \
                     patch.object(upload, "recorded_videos_match_channel", side_effect=[True, False]), \
                     patch.object(upload, "upload_video", return_value="new-id") as send, \
                     patch.object(upload, "create_private_playlist") as create, \
                     patch.object(upload, "ensure_video_in_playlist") as add, \
                     redirect_stdout(io.StringIO()):
                    self.assertEqual(upload.run_upload(folder, new_playlist="New playlist",
                                                       playlist_client=MagicMock()), 1)
                self.assertEqual(send.call_count, 1)
                create.assert_not_called()
                add.assert_not_called()
                db = history.open_database()
                try:
                    self.assertEqual(db.execute("SELECT COUNT(*) FROM uploads").fetchone()[0], 1)
                finally:
                    db.close()


if __name__ == "__main__":
    unittest.main()
