import sys
import unittest
from unittest.mock import patch

from process_launcher import LAUNCHER_PATH, application_command


class ProcessLauncherTests(unittest.TestCase):
    def test_source_command_uses_python_and_launcher(self) -> None:
        with patch.object(sys, "frozen", False, create=True):
            command = application_command(["--camera-process"])

        self.assertEqual(
            command,
            [sys.executable, str(LAUNCHER_PATH), "--camera-process"],
        )

    def test_packaged_command_reuses_same_executable(self) -> None:
        with patch.object(sys, "frozen", True, create=True):
            command = application_command(["--screen-process"])

        self.assertEqual(command, [sys.executable, "--screen-process"])


if __name__ == "__main__":
    unittest.main()
