"""Behavior tests across the real Windows control interface."""
import os
import unittest


@unittest.skipUnless(os.name == "nt", "Native Windows controls")
class AccessibleControlTests(unittest.TestCase):
    def test_reactivating_the_window_restores_the_selected_button(self):
        from accessible_controls import ControlWindow
        window = ControlWindow("Restore keyboard focus", (420, 220))
        self.addCleanup(window.close)
        window.button("first", "First", (20, 20, 160, 44), lambda: None)
        window.button("last", "Last", (210, 20, 160, 44), lambda: None)
        window.focus("last")
        window.u.SetFocus(window.hwnd)  # Actual native WM_SETFOCUS, not key().
        self.assertEqual(window.focused_name(), "last")

    def test_tab_clears_hidden_native_focus_cues(self):
        from accessible_controls import ControlWindow
        window = ControlWindow("Visible keyboard focus", (420, 220))
        self.addCleanup(window.close)
        window.button("first", "First", (20, 20, 160, 44), lambda: None)
        window.button("last", "Last", (210, 20, 160, 44), lambda: None)
        window.focus("first")
        window.u.SendMessageW(window.hwnd, 0x0127, 1 | (1 << 16), 0)  # UIS_SET / HIDEFOCUS
        self.assertTrue(window.u.SendMessageW(window.hwnd, 0x0129, 0, 0) & 1)
        window.key("Tab")
        self.assertEqual(window.focused_name(), "last")
        self.assertFalse(window.u.SendMessageW(window.hwnd, 0x0129, 0, 0) & 1)

    def test_message_loop_routes_tab_and_enter_after_window_reactivation(self):
        import ctypes
        from ctypes import wintypes
        import time
        from accessible_controls import ControlWindow
        window = ControlWindow("Real message loop", (420, 220))
        self.addCleanup(window.close)
        window.button("first", "First", (20, 20, 160, 44), lambda: window.finish("first"))
        window.button("last", "Last", (210, 20, 160, 44), lambda: window.finish("last"))
        window.u.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t]
        deadline = time.monotonic() + 2
        sent = False
        def tick():
            nonlocal sent
            if time.monotonic() > deadline:
                window.finish("timeout")
            elif not sent:
                sent = True
                window.focus("first")
                window.u.SetFocus(window.hwnd)
                window.u.PostMessageW(window.hwnd, 0x0100, 9, 0)
                window.u.PostMessageW(window.hwnd, 0x0100, 13, 0)
        window.on_tick = tick
        self.assertEqual(window.run(poll_interval_ms=10), "last")

    def test_qr_factories_close_native_resources_when_image_construction_fails(self):
        import threading
        from unittest.mock import patch
        from PIL import Image
        from accessible_controls import ControlWindow
        from accessible_desktop import pairing_controls, scanner_return_controls
        created = []
        def create_window(*args, **kwargs):
            window = ControlWindow(*args, **kwargs)
            created.append(window)
            self.addCleanup(window.close)
            return window
        for factory, kwargs in (
            (pairing_controls, dict(expires_at=9999999999, request_received=threading.Event(),
                                   cancel_requested=None, phone_opened=None, development_mode=False)),
            (scanner_return_controls, dict(phone_opened=None, expires_at=None)),
        ):
            with self.subTest(factory=factory.__name__):
                with patch("accessible_desktop.ControlWindow", side_effect=create_window):
                    with self.assertRaisesRegex(ValueError, "bounds must match"):
                        factory(Image.new("RGB", (8, 8)), **kwargs)
                self.assertTrue(created[-1]._closed, "Failed factory must release its real window")

    def test_native_text_measurement_counts_complete_emoji_text(self):
        import ctypes
        from ctypes import wintypes
        from accessible_controls import ControlWindow
        window = ControlWindow("Unicode measurement", (420, 400))
        self.addCleanup(window.close)
        text = "📱 PC 😀 " * 25
        window.label("unicode", text, (20, 20, 160, 330))
        hwnd = window._controls["unicode"].handle
        dc = window.u.GetDC(hwnd)
        old_font = window.g.SelectObject(dc, window.u.SendMessageW(hwnd, 0x0031, 0, 0))
        try:
            bounds = wintypes.RECT(0, 0, 160, 0)
            window.u.DrawTextW(dc, text, -1, ctypes.byref(bounds), 0x10 | 0x400 | 0x800)
            self.assertEqual(window.text_height("unicode"), bounds.bottom)
        finally:
            window.g.SelectObject(dc, old_font)
            window.u.ReleaseDC(hwnd, dc)

    def test_pairing_cancel_is_a_real_keyboard_action(self):
        import threading
        from PIL import Image
        from accessible_desktop import pairing_controls
        from pairing_ui import PairingWindowOutcome
        window = pairing_controls(Image.new("RGB", (414, 414), "white"),
                                  expires_at=9999999999, request_received=threading.Event(),
                                  cancel_requested=None, phone_opened=None, development_mode=False)
        self.addCleanup(window.close)
        window.focus("cancel")
        window.key("Enter")
        self.assertIs(window.result, PairingWindowOutcome.CANCELLED)

    def test_pairing_request_wins_over_opened_and_expiry(self):
        import threading
        from PIL import Image
        from accessible_desktop import pairing_controls
        from pairing_ui import PairingWindowOutcome
        request, opened = threading.Event(), threading.Event()
        request.set()
        opened.set()
        window = pairing_controls(Image.new("RGB", (414, 414), "white"), expires_at=1,
                                  request_received=request, cancel_requested=None,
                                  phone_opened=opened, development_mode=False)
        self.addCleanup(window.close)
        window.on_tick()
        self.assertIs(window.result, PairingWindowOutcome.REQUEST_RECEIVED)

    def test_phone_return_back_and_acknowledgement_close_native_window(self):
        import threading
        from PIL import Image
        from accessible_desktop import scanner_return_controls
        for acknowledge in (False, True):
            with self.subTest(acknowledge=acknowledge):
                opened = threading.Event()
                window = scanner_return_controls(Image.new("RGB", (350, 350), "white"),
                                                 phone_opened=opened, expires_at=None)
                self.addCleanup(window.close)
                if acknowledge:
                    opened.set()
                    window.on_tick()
                else:
                    window.focus("back")
                    window.key("Enter")
                self.assertTrue(window._closed)

    def test_long_native_label_fits_within_its_reserved_height(self):
        from accessible_controls import ControlWindow
        window = ControlWindow("Fitting text", (620, 200))
        self.addCleanup(window.close)
        window.label("help", "Choose a screenshot or saved QR code and select the area to scan.",
                     (28, 20, 300, 40))
        self.assertLessEqual(window.text_height("help"), 40)

    def test_both_languages_fit_native_screen_labels(self):
        import threading
        from unittest.mock import patch
        from PIL import Image
        from accessible_desktop import home_controls, settings_controls, pairing_controls, scanner_return_controls
        from native_dialogs import WindowCloseChoice
        for language in ("en", "tr"):
            with patch.dict(os.environ, {"WQRS_UI_LANGUAGE": language}):
                screens = [
                    home_controls(pair_count=999, confirm_exit=None, choose_close=lambda: WindowCloseChoice.CANCEL),
                    settings_controls(startup_reader=lambda: False),
                    pairing_controls(Image.new("RGB", (414, 414), "white"), expires_at=9999999999,
                                     request_received=threading.Event(), cancel_requested=None,
                                     phone_opened=None, development_mode=False),
                    scanner_return_controls(Image.new("RGB", (350, 350), "white"),
                                            phone_opened=None, expires_at=None),
                ]
                for window in screens:
                    self.addCleanup(window.close)
                    for name, bounds in window._label_bounds.items():
                        with self.subTest(language=language, label=name, text=window.value(name)):
                            self.assertLessEqual(window.text_height(name), bounds[3])

    def test_pairing_cancel_and_expiry_keep_original_outcomes(self):
        import threading
        from PIL import Image
        from accessible_desktop import pairing_controls
        from pairing_ui import PairingWindowOutcome
        for cancel in (False, True):
            event = threading.Event()
            if cancel:
                event.set()
            window = pairing_controls(Image.new("RGB", (414, 414), "white"), expires_at=1,
                                      request_received=threading.Event(), cancel_requested=event,
                                      phone_opened=None, development_mode=False)
            self.addCleanup(window.close)
            window.on_tick()
            self.assertIs(window.result, PairingWindowOutcome.CANCELLED if cancel else PairingWindowOutcome.EXPIRED)

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
