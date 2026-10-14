"""Behavior tests across the real Windows control interface."""
import os
import unittest


@unittest.skipUnless(os.name == "nt", "Native Windows controls")
class AccessibleControlTests(unittest.TestCase):
    def test_native_focus_cues_are_not_hidden(self):
        from accessible_controls import ControlWindow
        window = ControlWindow("Visible focus test", (420, 220))
        self.addCleanup(window.close)
        self.assertEqual(window.u.SendMessageW(window.hwnd, 0x0129, 0, 0) & 3, 0)

    def test_tab_skips_disabled_controls_and_enter_activates_focused_action(self):
        from accessible_controls import ControlWindow
        window = ControlWindow("Keyboard test", (420, 220))
        self.addCleanup(window.close)
        window.button("first", "First action", (20, 20, 160, 44), lambda: window.finish("first"))
        window.button("disabled", "Unavailable", (20, 75, 160, 44), lambda: window.finish("bad"), enabled=False)
        window.button("last", "Last action", (210, 20, 160, 44), lambda: window.finish("last"))
        window.focus("first")
        window.key("Tab")
        self.assertEqual(window.focused_name(), "last")
        window.key("Enter")
        self.assertEqual(window.result, "last")

    def test_home_keyboard_exit_cancel_and_background_are_distinct(self):
        from accessible_desktop import home_controls
        from home_ui import HomeAction
        from native_dialogs import WindowCloseChoice
        window = home_controls(pair_count=0, confirm_exit=lambda: False, choose_close=lambda: WindowCloseChoice.CANCEL)
        self.addCleanup(window.close)
        window.focus("exit")
        window.key("Enter")
        self.assertIsNone(window.result)
        window.key("Escape")
        self.assertIs(window.result, HomeAction.BACKGROUND)

    def test_phone_removal_still_requires_selection_and_confirmation(self):
        from accessible_desktop import phone_controls
        from paired_phones_ui import PairedPhoneView, PairedPhonesAction
        accepted = [False]
        phone = PairedPhoneView("https://qrwebcam.vercel.app", "a" * 22, "Test phone")
        window = phone_controls([phone], confirm_remove=lambda *_: accepted[0])
        self.addCleanup(window.close)
        window.selection("phones", 0, notify=True)
        window.focus("remove")
        window.key("Enter")
        self.assertIsNone(window.result)
        accepted[0] = True
        window.key("Enter")
        self.assertIs(window.result.action, PairedPhonesAction.REMOVE)
        self.assertEqual(window.result.phone, phone)

    def test_settings_creation_preserves_startup_and_explicit_toggle_changes_it(self):
        from accessible_desktop import settings_controls
        stored = [False]
        writes = []
        def save(value):
            writes.append(value)
            stored[0] = value
        window = settings_controls(startup_reader=lambda: stored[0], startup_writer=save)
        self.addCleanup(window.close)
        self.assertEqual(writes, [])
        window.focus("startup")
        window.key("Enter")
        self.assertEqual(writes, [True])
        self.assertTrue(window.check("startup"))

    def test_native_language_choices_retain_their_exact_unicode_text(self):
        from accessible_controls import ControlWindow
        window = ControlWindow("Language choices", (420, 220))
        self.addCleanup(window.close)
        window.choices("language", "Language", ["Türkçe", "English"], (20, 20, 220, 150), lambda: None, dropdown=True)
        window.selection("language", 0)
        self.assertEqual(window.value("language"), "Türkçe")
        window.selection("language", 1)
        self.assertEqual(window.value("language"), "English")
