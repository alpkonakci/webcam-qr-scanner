"""Real Win32 controls: standard UI Automation providers, keyboard and focus.

No owner-drawn buttons or accessibility-only mirror of a painted interface.
All calls belong to the creating UI thread; callbacks run on that same thread.
"""
from __future__ import annotations

import ctypes as c
from ctypes import wintypes as w
from collections.abc import Callable, Sequence
import os
import uuid


def available() -> bool:
    return os.name == "nt"


class ControlWindow:
    def __init__(self, title: str, size: tuple[int, int], *, on_close: Callable[[], None] | None = None,
                 on_escape: Callable[[], None] | None = None):
        if not available():
            raise OSError("Native controls require Windows")
        self.u, self.g, self.k = c.WinDLL("user32", use_last_error=True), c.WinDLL("gdi32"), c.WinDLL("kernel32")
        self._declare_functions()
        self.result = None
        self._closed = False
        self._running = False
        self._callbacks: dict[int, Callable[[], None]] = {}
        self._controls: dict[str, tuple[int, str, int]] = {}
        self._tab_order: list[str] = []
        self._fonts: list[int] = []
        self._on_close = on_close or self.close
        self._on_escape = on_escape or self._on_close
        self.on_tick: Callable[[], None] | None = None
        self._error: BaseException | None = None
        self._brush = self.g.CreateSolidBrush(0x20120B)
        self._procedure = c.WINFUNCTYPE(c.c_ssize_t, w.HWND, w.UINT, c.c_size_t, c.c_ssize_t)(self._dispatch)
        class WindowClass(c.Structure):
            _fields_ = [("style", w.UINT), ("procedure", c.c_void_p), ("classExtra", c.c_int),
                        ("windowExtra", c.c_int), ("instance", w.HINSTANCE), ("icon", w.HICON),
                        ("cursor", w.HANDLE), ("background", w.HBRUSH), ("menu", w.LPCWSTR), ("name", w.LPCWSTR)]
        self._class_name = "WqrsControls" + uuid.uuid4().hex
        self._instance = self.k.GetModuleHandleW(None)
        wc = WindowClass(0, c.cast(self._procedure, c.c_void_p), 0, 0, self._instance, None,
                         self.u.LoadCursorW(None, 32512), self._brush, None, self._class_name)
        self.u.RegisterClassW.argtypes = [c.POINTER(WindowClass)]
        if not self.u.RegisterClassW(c.byref(wc)):
            raise c.WinError(c.get_last_error())
        style = 0x00C00000 | 0x00080000 | 0x00020000  # Caption, system menu, minimize; fixed size.
        rect = w.RECT(0, 0, *size)
        self.u.AdjustWindowRect(c.byref(rect), style, False)
        width, height = rect.right - rect.left, rect.bottom - rect.top
        x = max(0, (self.u.GetSystemMetrics(0) - width) // 2)
        y = max(0, (self.u.GetSystemMetrics(1) - height) // 3)
        self.hwnd = self.u.CreateWindowExW(0x10000, self._class_name, title, style, x, y, width, height,
                                          None, None, self._instance, None)
        if not self.hwnd:
            self.close()
            raise c.WinError(c.get_last_error())
        self.font = self._font(16)
        # Clear hidden focus cues. Windows draws its own keyboard focus outline.
        self.u.SendMessageW(self.hwnd, 0x0127, 2 | (3 << 16), 0)  # UIS_CLEAR.
        from window_icon import set_window_icon
        set_window_icon(title)

    def _declare_functions(self):
        definitions = {
            "CreateWindowExW": ([w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD, c.c_int, c.c_int, c.c_int, c.c_int, w.HWND, w.HMENU, w.HINSTANCE, c.c_void_p], w.HWND),
            "DefWindowProcW": ([w.HWND, w.UINT, c.c_size_t, c.c_ssize_t], c.c_ssize_t),
            "SendMessageW": ([w.HWND, w.UINT, c.c_size_t, c.c_ssize_t], c.c_ssize_t),
            "SetFocus": ([w.HWND], w.HWND), "GetFocus": ([], w.HWND),
            "DestroyWindow": ([w.HWND], w.BOOL), "EnableWindow": ([w.HWND, w.BOOL], w.BOOL),
            "IsWindowEnabled": ([w.HWND], w.BOOL), "SetWindowTextW": ([w.HWND, w.LPCWSTR], w.BOOL),
            "LoadCursorW": ([w.HINSTANCE, c.c_size_t], w.HANDLE),
            "GetMessageW": ([c.POINTER(w.MSG), w.HWND, w.UINT, w.UINT], c.c_int),
            "IsDialogMessageW": ([w.HWND, c.POINTER(w.MSG)], w.BOOL),
            "TranslateMessage": ([c.POINTER(w.MSG)], w.BOOL), "DispatchMessageW": ([c.POINTER(w.MSG)], c.c_ssize_t),
            "ShowWindow": ([w.HWND, c.c_int], w.BOOL), "SetForegroundWindow": ([w.HWND], w.BOOL),
            "SetTimer": ([w.HWND, c.c_size_t, w.UINT, c.c_void_p], c.c_size_t),
            "KillTimer": ([w.HWND, c.c_size_t], w.BOOL),
            "UnregisterClassW": ([w.LPCWSTR, w.HINSTANCE], w.BOOL),
            "NotifyWinEvent": ([w.DWORD, w.HWND, c.c_long, c.c_long], None),
            "GetWindowTextLengthW": ([w.HWND], c.c_int),
            "GetWindowTextW": ([w.HWND, w.LPWSTR, c.c_int], c.c_int),
            "AdjustWindowRect": ([c.POINTER(w.RECT), w.DWORD, w.BOOL], w.BOOL),
            "GetSystemMetrics": ([c.c_int], c.c_int),
            "GetKeyState": ([c.c_int], c.c_short), "PostQuitMessage": ([c.c_int], None),
        }
        for name, (arguments, result) in definitions.items():
            function = getattr(self.u, name)
            function.argtypes, function.restype = arguments, result
        self.k.GetModuleHandleW.argtypes, self.k.GetModuleHandleW.restype = [w.LPCWSTR], w.HINSTANCE
        self.g.CreateSolidBrush.argtypes, self.g.CreateSolidBrush.restype = [w.DWORD], w.HBRUSH
        self.g.CreateFontW.argtypes = [c.c_int] * 5 + [w.DWORD] * 8 + [w.LPCWSTR]
        self.g.CreateFontW.restype = w.HANDLE
        self.g.DeleteObject.argtypes = [w.HANDLE]
        self.g.SetTextColor.argtypes = [w.HDC, w.DWORD]
        self.g.SetBkMode.argtypes = [w.HDC, c.c_int]

    def _font(self, height: int, bold: bool = False):
        font = self.g.CreateFontW(-height, 0, 0, 0, 600 if bold else 400, 0, 0, 0, 1, 0, 0, 5, 0, "Segoe UI")
        self._fonts.append(font)
        return font

    def _add(self, name: str, kind: str, text: str, bounds: tuple[int, int, int, int], style: int,
             callback: Callable[[], None] | None = None, *, enabled: bool = True, font: int | None = None):
        identifier = 100 + len(self._controls)
        hwnd = self.u.CreateWindowExW(0, kind, text, 0x50000000 | style, *bounds,
                                      self.hwnd, identifier, self._instance, None)
        if not hwnd:
            raise c.WinError(c.get_last_error())
        self._controls[name] = (hwnd, kind, identifier)
        self.u.SendMessageW(hwnd, 0x0030, font or self.font, 1)
        self.u.EnableWindow(hwnd, enabled)
        if style & 0x10000:
            self._tab_order.append(name)
        if callback:
            self._callbacks[identifier] = callback
        return hwnd

    def label(self, name: str, text: str, bounds: tuple[int, int, int, int], *, heading: bool = False):
        self._add(name, "Static", text, bounds, 0x80, font=self._font(28, True) if heading else None)

    def button(self, name: str, text: str, bounds: tuple[int, int, int, int], action: Callable[[], None], *, enabled: bool = True):
        self._add(name, "Button", text, bounds, 0x10000 | 0x2000, action, enabled=enabled)

    def choices(self, name: str, text: str, items: Sequence[str], bounds: tuple[int, int, int, int],
                on_change: Callable[[], None], *, dropdown: bool = False):
        hwnd = self._add(name, "ComboBox" if dropdown else "ListBox", text, bounds,
                         0x10000 | 0x200000 | (0x203 if dropdown else 0x00800041), on_change)
        message = 0x143 if dropdown else 0x180
        for item in items:
            # Keep the UTF-16 buffer alive for the synchronous native call.
            # A temporary pointer converted to int can be freed before dispatch.
            buffer = c.create_unicode_buffer(item)
            self.u.SendMessageW(hwnd, message, 0, c.cast(buffer, c.c_void_p).value)

    def checkbox(self, name: str, text: str, bounds: tuple[int, int, int, int], on_change: Callable[[], None], checked: bool):
        # Native toggle-button appearance keeps system text/focus contrast.
        # It is still an auto-checkbox with the standard Toggle/UIA provider.
        self._add(name, "Button", text, bounds, 0x11003, on_change)
        self.check(name, checked)

    def check(self, name: str, checked: bool | None = None) -> bool:
        hwnd = self._controls[name][0]
        if checked is not None:
            self.u.SendMessageW(hwnd, 0xF1, int(checked), 0)
        return bool(self.u.SendMessageW(hwnd, 0xF0, 0, 0))

    def selection(self, name: str, index: int | None = None, *, notify: bool = False) -> int:
        hwnd, kind, identifier = self._controls[name]
        dropdown = kind == "ComboBox"
        if index is not None:
            self.u.SendMessageW(hwnd, 0x14E if dropdown else 0x186, index, 0)
            if notify and identifier in self._callbacks:
                self._callbacks[identifier]()
        return int(self.u.SendMessageW(hwnd, 0x147 if dropdown else 0x188, 0, 0))

    def value(self, name: str) -> str:
        hwnd = self._controls[name][0]
        length = self.u.GetWindowTextLengthW(hwnd)
        buffer = c.create_unicode_buffer(length + 1)
        self.u.GetWindowTextW(hwnd, buffer, len(buffer))
        return buffer.value

    def text(self, name: str, value: str):
        hwnd = self._controls[name][0]
        # Only announce real changes, not every polling tick.
        if self.value(name) != value:
            self.u.SetWindowTextW(hwnd, value)
            self.u.NotifyWinEvent(0x800C, hwnd, -4, 0)

    def title(self, value: str):
        self.u.SetWindowTextW(self.hwnd, value)

    def enable(self, name: str, enabled: bool):
        self.u.EnableWindow(self._controls[name][0], enabled)

    def focus(self, name: str):
        self.u.SetFocus(self._controls[name][0])

    def focused_name(self) -> str | None:
        focused = self.u.GetFocus()
        return next((name for name, (hwnd, _, _) in self._controls.items() if hwnd == focused), None)

    def key(self, key: str, *, shift: bool = False) -> bool:
        if key == "Escape":
            self._on_escape()
            return True
        if key == "Tab":
            names = [name for name in self._tab_order if self.u.IsWindowEnabled(self._controls[name][0])]
            if names:
                current = self.focused_name()
                index = names.index(current) if current in names else (0 if shift else -1)
                self.focus(names[(index + (-1 if shift else 1)) % len(names)])
            return True
        if key == "Enter":
            name = self.focused_name()
            if name and self._controls[name][1] == "Button":
                self.u.SendMessageW(self._controls[name][0], 0xF5, 0, 0)  # Native BM_CLICK.
                return True
        return False

    def finish(self, result):
        self.result = result
        self.close()

    def _dispatch(self, hwnd, message, wp, lp):
        try:
            if message == 0x0111:  # WM_COMMAND: real controls invoke the same actions as the mouse.
                identifier, event = wp & 0xFFFF, (wp >> 16) & 0xFFFF
                if event in {0, 1} and identifier in self._callbacks:
                    self._callbacks[identifier]()
                return 0
            if message == 0x0010:
                self._on_close()
                return 0
            if message == 0x0113 and self.on_tick:
                self.on_tick()
                return 0
            if message == 0x0138:  # Static text uses the calm dark surface; controls remain native.
                self.g.SetTextColor(wp, 0xFCFAF8)
                self.g.SetBkMode(wp, 1)
                return self._brush
            if message == 0x0002 and self._running:
                self.u.PostQuitMessage(0)
                return 0
        except BaseException as error:
            self._error = error
            if getattr(self, "hwnd", None):
                self.close()
            return 0
        return self.u.DefWindowProcW(hwnd, message, wp, lp)

    def run(self):
        self._running = True
        self.u.ShowWindow(self.hwnd, 5)
        self.u.SetForegroundWindow(self.hwnd)
        if self._tab_order:
            self.focus(self._tab_order[0])
        self.u.SetTimer(self.hwnd, 1, 1000, None)
        message = w.MSG()
        try:
            while True:
                received = self.u.GetMessageW(c.byref(message), None, 0, 0)
                if received == -1:
                    raise c.WinError(c.get_last_error())
                if not received:
                    break
                if message.message == 0x100:
                    key = {9: "Tab", 13: "Enter", 27: "Escape"}.get(message.wParam)
                    if key and self.key(key, shift=bool(self.u.GetKeyState(16) & 0x8000)):
                        continue
                if not self.u.IsDialogMessageW(self.hwnd, c.byref(message)):
                    self.u.TranslateMessage(c.byref(message))
                    self.u.DispatchMessageW(c.byref(message))
            if self._error:
                raise self._error
            return self.result
        finally:
            self.close()

    def close(self):
        if self._closed:
            return
        self._closed = True
        hwnd = getattr(self, "hwnd", None)
        if hwnd:
            self.u.KillTimer(hwnd, 1)
            self.u.DestroyWindow(hwnd)
        for font in self._fonts:
            self.g.DeleteObject(font)
        self.g.DeleteObject(self._brush)
        self.u.UnregisterClassW(self._class_name, self._instance)
