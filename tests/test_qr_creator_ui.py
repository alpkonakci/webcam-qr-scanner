import queue
import unittest
from unittest.mock import Mock, patch

from qr_creator_ui import CreatorWindow


def window_fixture():
    window = CreatorWindow.__new__(CreatorWindow)
    window.root = Mock()
    window.input = Mock()
    window.input.get.return_value = "https://example.com/new"
    window.kind = Mock()
    window.kind.get.return_value = "link"
    window.revision = 3
    window.current = None
    window.timer = None
    window.pending = None
    window.worker_active = False
    window.closed = False
    window.results = queue.Queue()
    window.message = Mock()
    window.preview = Mock()
    window.blank = Mock()
    window._enable = Mock()
    return window


class CreatorUiTests(unittest.TestCase):
    def test_busy_worker_retains_only_newest_valid_job(self):
        window = window_fixture()
        window.worker_active = True
        with patch.object(window, "_start_worker") as start:
            window.generate()
            window.input.get.return_value = "https://example.com/latest"
            window.revision = 4
            window.generate()
        start.assert_not_called()
        self.assertEqual(window.pending, ("https://example.com/latest", "link", 4))

    def test_edit_invalidates_export_and_queued_work(self):
        window = window_fixture()
        window.current = Mock()
        window.pending = ("old", "text", 1)
        window.changed()
        self.assertIsNone(window.current)
        self.assertIsNone(window.pending)
        self.assertEqual(window.revision, 4)
        window._enable.assert_called_once_with(False)

    def test_stale_result_is_not_rendered_but_latest_job_is_started(self):
        window = window_fixture()
        window.worker_active = True
        window.results.put((2, Mock()))
        window.pending = ("https://example.com/new", "link", 3)
        with patch.object(window, "_start_worker") as start:
            window.poll()
        start.assert_called_once_with("https://example.com/new", "link", 3)
        self.assertIsNone(window.current)
        window._enable.assert_not_called()

    def test_cancelled_save_writes_nothing(self):
        window = window_fixture()
        window.current = Mock()
        with patch("qr_creator_ui.filedialog.asksaveasfilename", return_value=""):
            window.save()
        window.current.image.save.assert_not_called()

    def test_explicit_save_exports_png_only(self):
        window = window_fixture()
        window.current = Mock()
        with patch("qr_creator_ui.filedialog.asksaveasfilename", return_value="chosen.png"):
            window.save()
        window.current.image.save.assert_called_once_with("chosen.png", format="PNG")

    def test_image_copy_uses_the_owned_window(self):
        window = window_fixture()
        window.current = Mock()
        window.root.winfo_id.return_value = 123
        with patch("qr_creator_ui.copy_image") as copy:
            window.copy()
        copy.assert_called_once_with(window.current.image, owner=123)


if __name__ == "__main__":
    unittest.main()
