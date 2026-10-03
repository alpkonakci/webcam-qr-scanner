import sys
import unittest
from unittest.mock import patch

from windows_startup import startup_command


class WindowsStartupTests(unittest.TestCase):
    def test_packaged_startup_command_uses_bridge_mode_without_camera(self) -> None:
        with patch.object(sys, "frozen", True, create=True):
            command = startup_command()

        self.assertIn(sys.executable, command)
        self.assertIn("--bridge", command)
        self.assertNotIn("--open-camera", command)


if __name__ == "__main__":
    unittest.main()
