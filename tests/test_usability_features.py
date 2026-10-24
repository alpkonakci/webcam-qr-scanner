import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import numpy as np
from app_settings import AppSettings, SettingsStore
from desktop_i18n import CATALOG, t
from receiver_status import connection_confirmed, record_connection
from app_info import APP_VERSION, RELEASES_URL
from home_ui import action_at_point, HomeAction, build_home_canvas


class UsabilityFeatureTests(unittest.TestCase):
    def test_saved_language_round_trip_and_legacy_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            store = SettingsStore(path)
            path.write_text('{"version":1,"camera_closed_notice_shown":true}', encoding="utf-8")
            self.assertEqual(store.load(), AppSettings(camera_closed_notice_shown=True))
            store.update(language="tr")
            self.assertEqual(store.load().language, "tr")
            self.assertTrue(store.load().camera_closed_notice_shown)

    def test_invalid_language_falls_back_without_erasing_other_preference(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text('{"version":1,"language":"unknown","camera_closed_notice_shown":true}', encoding="utf-8")
            self.assertEqual(SettingsStore(path).load(), AppSettings(camera_closed_notice_shown=True))
            path.write_text('{"version":1,"language":[],"camera_closed_notice_shown":true}', encoding="utf-8")
            self.assertEqual(SettingsStore(path).load(), AppSettings(camera_closed_notice_shown=True))

    def test_translations_keep_names_and_addresses_exact(self):
        self.assertEqual(t("Remove access for {phone} ({id})?", language="tr", phone="My iPhone", id="ABC"), "My iPhone (ABC) erişimi kaldırılsın mı?")
        self.assertEqual(t("https://example.com/?key=Back", language="tr"), "https://example.com/?key=Back")
        self.assertEqual(t("\nWebsite:\n", language="tr"), "\nWeb sitesi:\n")

    def test_catalogue_placeholders_match_in_both_languages(self):
        from string import Formatter
        def fields(value): return {name for _, name, _, _ in Formatter().parse(value) if name}
        for english, turkish in CATALOG.items(): self.assertEqual(fields(english), fields(turkish), english)

    def test_receiver_status_expires_and_does_not_come_from_pair_count(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "status.json"
            origin = "https://relay.example"
            self.assertFalse(connection_confirmed(origin, path=path, now=100))
            record_connection(origin, True, path=path, now=100)
            self.assertTrue(connection_confirmed(origin, path=path, now=174))
            self.assertFalse(connection_confirmed(origin, path=path, now=175))
            self.assertFalse(connection_confirmed(origin, path=path, now=99))
            record_connection(origin, False, path=path, now=176)
            self.assertFalse(connection_confirmed(origin, path=path, now=176))
            self.assertEqual(set(json.loads(path.read_text())[origin]), {"reachable", "checked_at"})

    def test_settings_click_and_language_canvases(self):
        self.assertIs(action_at_point(500, 45), HomeAction.SETTINGS)
        with patch.dict("os.environ", {"WQRS_UI_LANGUAGE": "tr"}):
            turkish = build_home_canvas(pair_count=1, receiver_ready=False)
        with patch.dict("os.environ", {"WQRS_UI_LANGUAGE": "en"}):
            english = build_home_canvas(pair_count=1, receiver_ready=False)
        self.assertEqual(turkish.shape, english.shape)
        self.assertFalse(np.array_equal(turkish, english))

    def test_unicode_camera_text_draws_without_question_mark_substitution(self):
        from ui import put_text
        canvas = np.zeros((100, 350, 3), dtype=np.uint8)
        put_text(canvas, "QR kodunu çerçeveye yerleştir", (8, 40), 0, .6, (255, 255, 255))
        self.assertGreater(int(canvas.max()), 0)

    def test_public_version_matches_browser_and_windows_metadata(self):
        root = Path(__file__).resolve().parents[1]
        self.assertIn(APP_VERSION, (root / "pwa/lib/app-info.ts").read_text())
        self.assertIn(APP_VERSION, (root / "assets/windows-version-info.txt").read_text())
        self.assertEqual(RELEASES_URL, "https://github.com/alpkonakci/webcam-qr-scanner/releases")


class SettingsWindowTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)

    def test_creation_never_changes_startup_and_explicit_toggle_uses_writer(self):
        from settings_ui import SettingsWindow
        reader, writer = Mock(return_value=False), Mock()
        window = SettingsWindow(self.root, startup_reader=reader, startup_writer=writer)
        writer.assert_not_called()
        window.startup.set(True)
        window.toggle_startup()
        writer.assert_called_once_with(True)

    def test_failed_startup_change_restores_actual_state(self):
        from settings_ui import SettingsWindow
        window = SettingsWindow(self.root, startup_reader=lambda: False, startup_writer=Mock(side_effect=OSError()))
        window.startup.set(True)
        window.toggle_startup()
        self.assertFalse(window.startup.get())

    def test_language_change_is_explicit(self):
        from settings_ui import SettingsWindow
        writer = Mock()
        window = SettingsWindow(self.root, startup_reader=lambda: False, startup_writer=Mock(), language_writer=writer)
        writer.assert_not_called()
        window.choose_language("Türkçe")
        writer.assert_called_once_with("tr")
