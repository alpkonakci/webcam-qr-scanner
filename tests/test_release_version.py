import os
from pathlib import Path
import subprocess
import unittest

from app_info import APP_VERSION


@unittest.skipUnless(os.name == "nt", "requires Windows PowerShell")
class ReleaseVersionTests(unittest.TestCase):
    def resolve(self, requested=""):
        root = Path(__file__).resolve().parents[1]
        helper = str(root / "scripts/release_version.ps1").replace("'", "''")
        directory = str(root).replace("'", "''")
        return subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command",
             f"$ErrorActionPreference='Stop'; . '{helper}'; "
             f"Resolve-ReleaseVersion -ProjectDirectory '{directory}' -RequestedVersion '{requested}'"],
            capture_output=True, text=True, timeout=15,
        )

    def test_default_and_explicit_version_match_application(self):
        for requested in ("", f"v{APP_VERSION}"):
            result = self.resolve(requested)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), f"v{APP_VERSION}")

    def test_stale_or_path_like_version_cannot_label_a_package(self):
        for requested in ("v0.2.0-beta.8-preview.2", "../escape"):
            result = self.resolve(requested)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("does not match application version", result.stderr)


if __name__ == "__main__":
    unittest.main()
