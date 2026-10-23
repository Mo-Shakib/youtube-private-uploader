import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import history
import upload
import questionary


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

    def test_interactive_path_accepts_shell_style_outer_quotes(self):
        path = "/Volumes/SSD/batfiles/Video with spaces.m3u8.mp4"
        self.assertEqual(upload.normalize_interactive_path(f"'{path}'"), path)
        self.assertEqual(upload.normalize_interactive_path(f'"{path}"'), path)
        self.assertEqual(upload.normalize_interactive_path(path), path)
        self.assertEqual(upload.normalize_interactive_path("/Videos/Mom's video.mp4"), "/Videos/Mom's video.mp4")

    def test_menu_passes_unquoted_path_to_uploader(self):
        path = "/Volumes/SSD/batfiles/Video with spaces.m3u8.mp4"
        with patch.object(upload.sys.stdin, "isatty", return_value=True), \
             patch.object(upload.sys.stdout, "isatty", return_value=True), \
             patch.object(questionary, "select") as select, \
             patch.object(questionary, "text") as text, \
             patch.object(upload, "run_upload") as run:
            select.return_value.ask.side_effect = ["Upload a video", "Exit"]
            text.return_value.ask.return_value = f"'{path}'"
            self.assertEqual(upload.interactive_menu(), 0)
            run.assert_called_once_with(path)

    def test_history_is_a_table_and_truncates_long_filenames(self):
        long_name = "A very long video filename that should wrap cleanly.mp4"
        video = Path(self.temp.name) / long_name
        video.write_bytes(b"video")
        db = history.open_database()
        try:
            history.record_upload(db, "profile-key", video, "hash", 5, "abc123")
        finally:
            db.close()

        output = io.StringIO()
        with redirect_stdout(output):
            history.show_history()
        lines = output.getvalue().splitlines()
        self.assertIn("| Uploaded", output.getvalue())
        self.assertIn("Title (filename)", output.getvalue())
        self.assertIn("https://youtu.be/abc123", output.getvalue())
        self.assertIn(long_name[:50] + ".....", output.getvalue())
        self.assertNotIn(long_name, output.getvalue())
        self.assertEqual(sum(line.startswith("| ") for line in lines), 2)

    def test_markdown_export_includes_all_rows_and_escapes_table_cells(self):
        export_path = Path(self.temp.name) / "upload-history.md"
        db = history.open_database()
        try:
            first = Path(self.temp.name) / ("A" * 51 + "|.mp4")
            second = Path(self.temp.name) / "second.mp4"
            history.record_upload(db, "profile-key", first, "hash-a", 1, "first-id")
            history.record_upload(db, "profile-key", second, "hash-b", 1, "second-id")
        finally:
            db.close()

        with patch.object(history, "EXPORT_FILE", export_path):
            path, count = history.export_history()
        content = path.read_text()
        self.assertEqual(count, 2)
        self.assertTrue(content.startswith("# YouTube Private Uploader — Upload History\n"))
        self.assertIn("| Uploaded | Title (filename) | YouTube URL | Profile |", content)
        self.assertIn("https://youtu.be/first-id", content)
        self.assertIn("https://youtu.be/second-id", content)
        self.assertIn("A" * 50 + ".....", content)
        self.assertNotIn("A" * 51, content)
        self.assertRegex(content.splitlines()[-1], r"^\*\*Exported:\*\* \d{1,2} [A-Za-z]+ \d{4} at \d{1,2}:\d{2} (AM|PM) \(UTC[+-]\d{2}:\d{2}\)$")
        self.assertEqual(list(Path(self.temp.name).glob(".upload-history-*.tmp")), [])

        db = history.open_database()
        try:
            pipe_name = Path(self.temp.name) / "video|part.mp4"
            history.record_upload(db, "profile-key", pipe_name, "hash-c", 1, "third-id")
        finally:
            db.close()
        with patch.object(history, "EXPORT_FILE", export_path):
            history.export_history()
        self.assertIn("video\\|part.mp4", export_path.read_text())
        self.assertEqual(export_path.read_text().count("https://youtu.be/second-id"), 2)


if __name__ == "__main__":
    unittest.main()
