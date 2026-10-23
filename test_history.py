import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import history
import upload


class UploadHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        db_path = str(Path(self.temp.name) / "history.db")
        env = patch.dict(os.environ, {"YTUPLOAD_HISTORY_DB": db_path})
        env.start()
        self.addCleanup(env.stop)
        self.video = Path(self.temp.name) / "original.mp4"
        self.video.write_bytes(b"sample video")

    def test_duplicate_survives_rename_and_force_uploads_again(self):
        with patch.object(upload, "authenticate", return_value=(object(), "account-a")), \
             patch.object(upload, "upload_video", side_effect=["first-id", "second-id"]) as send:
            with redirect_stdout(io.StringIO()):
                self.assertEqual(upload.run_upload(self.video), 0)
                renamed = self.video.with_name("renamed.mp4")
                self.video.rename(renamed)
                self.assertEqual(upload.run_upload(renamed), 0)
                self.assertEqual(send.call_count, 1)
                self.assertEqual(upload.run_upload(renamed, force=True), 0)
                self.assertEqual(send.call_count, 2)

        db = history.open_database()
        try:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM uploads").fetchone()[0], 2)
        finally:
            db.close()

    def test_changed_file_and_other_grant_are_not_skipped(self):
        with patch.object(upload, "authenticate", side_effect=[
            (object(), "account-a"), (object(), "account-a"), (object(), "account-b")
        ]), patch.object(upload, "upload_video", side_effect=["one", "two", "three"]) as send:
            with redirect_stdout(io.StringIO()):
                self.assertEqual(upload.run_upload(self.video), 0)
                self.video.write_bytes(b"changed video")
                self.assertEqual(upload.run_upload(self.video), 0)
                self.assertEqual(upload.run_upload(self.video), 0)
            self.assertEqual(send.call_count, 3)

    def test_failed_upload_is_not_recorded(self):
        with patch.object(upload, "authenticate", return_value=(object(), "account-a")), \
             patch.object(upload, "upload_video", side_effect=[RuntimeError("offline"), "ok"]) as send:
            with redirect_stdout(io.StringIO()):
                self.assertEqual(upload.run_upload(self.video), 1)
                self.assertEqual(upload.run_upload(self.video), 0)
            self.assertEqual(send.call_count, 2)


if __name__ == "__main__":
    unittest.main()
