from __future__ import annotations

import unittest
from unittest.mock import patch

from native_dialogs import (
    IDNO,
    IDYES,
    MB_DEFBUTTON3,
    MB_YESNOCANCEL,
    WindowCloseChoice,
    choose_home_window_close,
)


class NativeDialogTests(unittest.TestCase):
    def test_titlebar_close_has_three_unambiguous_outcomes(self) -> None:
        for response, expected in (
            (IDYES, WindowCloseChoice.BACKGROUND),
            (IDNO, WindowCloseChoice.EXIT),
            (2, WindowCloseChoice.CANCEL),
            (0, WindowCloseChoice.CANCEL),
        ):
            with self.subTest(response=response):
                with patch(
                    "native_dialogs.show_dialog",
                    return_value=response,
                ) as show_dialog:
                    choice = choose_home_window_close()

                self.assertIs(choice, expected)
                self.assertIn("Keep QR Scanner running", show_dialog.call_args.args[1])
                self.assertEqual(
                    show_dialog.call_args.args[2] & MB_YESNOCANCEL,
                    MB_YESNOCANCEL,
                )
                self.assertTrue(show_dialog.call_args.args[2] & MB_DEFBUTTON3)


if __name__ == "__main__":
    unittest.main()
