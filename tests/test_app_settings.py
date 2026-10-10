import json
import tempfile
import unittest
from pathlib import Path

from app_settings import AppSettings, SettingsStore, settings_directory


class SettingsStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.path = Path(self.temporary_directory.name) / "settings.json"
        self.store = SettingsStore(self.path)

    def test_missing_file_uses_privacy_safe_defaults(self) -> None:
        self.assertEqual(self.store.load(), AppSettings())
        self.assertFalse(self.store.load().camera_closed_notice_shown)

    def test_round_trip_persists_known_preference(self) -> None:
        expected = AppSettings(camera_closed_notice_shown=True)

        self.store.save(expected)

        self.assertEqual(self.store.load(), expected)
        self.assertNotIn("bridge_enabled", self.path.read_text(encoding="utf-8"))

    def test_malformed_json_falls_back_to_defaults(self) -> None:
        self.path.write_text("{broken", encoding="utf-8")

        self.assertEqual(self.store.load(), AppSettings())

    def test_invalid_field_type_falls_back_to_defaults(self) -> None:
        self.path.write_text(
            json.dumps({"version": 1, "camera_closed_notice_shown": "yes"}),
            encoding="utf-8",
        )

        self.assertEqual(self.store.load(), AppSettings())

    def test_unknown_legacy_fields_are_ignored(self) -> None:
        self.path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "bridge_enabled": True,
                    "start_with_windows": True,
                    "camera_closed_notice_shown": True,
                }
            ),
            encoding="utf-8",
        )

        self.assertEqual(
            self.store.load(),
            AppSettings(camera_closed_notice_shown=True),
        )

    def test_local_app_data_selects_per_user_directory(self) -> None:
        root = Path(self.temporary_directory.name)

        self.assertEqual(
            settings_directory({"LOCALAPPDATA": str(root)}),
            root / "Webcam QR Scanner",
        )


if __name__ == "__main__":
    unittest.main()
