"""Real Win32 controls: standard UI Automation providers, keyboard and focus.

No owner-drawn buttons or accessibility-only mirror of a painted interface.
All calls belong to the creating UI thread; callbacks run on that same thread.
"""
from __future__ import annotations

import ctypes as c
from ctypes import wintypes as w
from collections.abc import Callable, Sequence
from dataclasses import dataclass
import os
import uuid


# Win32 constants stay here, not in screen construction or domain decisions.
WS_CAPTION = 0x00C00000
WS_SYSMENU = 0x00080000
WS_MINIMIZEBOX = 0x00020000
WS_TABSTOP = 0x00010000
WS_CHILD = 0x40000000
WS_VISIBLE = 0x10000000
WS_VSCROLL = 0x00200000
WS_BORDER = 0x00800000
WS_EX_CONTROLPARENT = 0x00010000
BS_MULTILINE = 0x2000
BS_AUTOCHECKBOX = 0x0003
BS_PUSHLIKE = 0x1000
SS_NOPREFIX = 0x0080
CBS_DROPDOWNLIST = 0x0003
CBS_HASSTRINGS = 0x0200
LBS_NOTIFY = 0x0001
LBS_NOINTEGRALHEIGHT = 0x0040
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_SETFONT = 0x0030
WM_KEYDOWN = 0x0100
WM_COMMAND = 0x0111
WM_TIMER = 0x0113
WM_CHANGEUISTATE = 0x0127
WM_CTLCOLORSTATIC = 0x0138
BM_GETCHECK = 0x00F0
BM_SETCHECK = 0x00F1
BM_CLICK = 0x00F5
CB_ADDSTRING = 0x0143
CB_GETCURSEL = 0x0147
CB_SETCURSEL = 0x014E
LB_ADDSTRING = 0x0180
LB_SETCURSEL = 0x0186
LB_GETCURSEL = 0x0188
UIS_CLEAR = 2
UISF_HIDEFOCUS = 1
UISF_HIDEACCEL = 2
EVENT_OBJECT_NAMECHANGE = 0x800C
OBJID_CLIENT = -4
IDC_ARROW = 32512
SW_SHOW = 5
VK_SHIFT = 16
KEY_PRESSED = 0x8000
TRANSPARENT = 1
COLOR_SURFACE = 0x20120B
COLOR_TEXT = 0xFCFAF8
REFRESH_TIMER_ID = 1
REFRESH_INTERVAL_MS = 1000
KEY_NAMES = {9: "Tab", 13: "Enter", 27: "Escape"}

Bounds = tuple[int, int, int, int]
Action = Callable[[], None]


@dataclass(frozen=True)
class _Control:
    handle: int
    kind: str
    identifier: int


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
        self._controls: dict[str, _Control] = {}
        self._tab_order: list[str] = []
        self._fonts: list[int] = []
        self._font_cache: dict[tuple[int, bool], int] = {}
        self._bitmaps: list[int] = []
        self._label_bounds: dict[str, Bounds] = {}
        self._label_heading: dict[str, bool] = {}
        self._on_close = on_close or self.close
        self._on_escape = on_escape or self._on_close
        self.on_tick: Callable[[], None] | None = None
        self._error: BaseException | None = None
        self._brush = self.g.CreateSolidBrush(COLOR_SURFACE)
        self._procedure = c.WINFUNCTYPE(c.c_ssize_t, w.HWND, w.UINT, c.c_size_t, c.c_ssize_t)(self._dispatch)
        class WindowClass(c.Structure):
            _fields_ = [("style", w.UINT), ("procedure", c.c_void_p), ("classExtra", c.c_int),
                        ("windowExtra", c.c_int), ("instance", w.HINSTANCE), ("icon", w.HICON),
                        ("cursor", w.HANDLE), ("background", w.HBRUSH), ("menu", w.LPCWSTR), ("name", w.LPCWSTR)]
        self._class_name = "WqrsControls" + uuid.uuid4().hex
        self._instance = self.k.GetModuleHandleW(None)
        wc = WindowClass(0, c.cast(self._procedure, c.c_void_p), 0, 0, self._instance, None,
                         self.u.LoadCursorW(None, IDC_ARROW), self._brush, None, self._class_name)
        self.u.RegisterClassW.argtypes = [c.POINTER(WindowClass)]
        if not self.u.RegisterClassW(c.byref(wc)):
            raise c.WinError(c.get_last_error())
        style = WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX  # Fixed size.
        rect = w.RECT(0, 0, *size)
        self.u.AdjustWindowRect(c.byref(rect), style, False)
        width, height = rect.right - rect.left, rect.bottom - rect.top
        x = max(0, (self.u.GetSystemMetrics(0) - width) // 2)
        y = max(0, (self.u.GetSystemMetrics(1) - height) // 3)
        self.hwnd = self.u.CreateWindowExW(WS_EX_CONTROLPARENT, self._class_name, title, style, x, y, width, height,
                                          None, None, self._instance, None)
        if not self.hwnd:
            self.close()
            raise c.WinError(c.get_last_error())
        self.font = self._font(16)
        # Clear hidden focus cues. Windows draws its own keyboard focus outline.
        hidden_cues = UISF_HIDEFOCUS | UISF_HIDEACCEL
        self.u.SendMessageW(self.hwnd, WM_CHANGEUISTATE, UIS_CLEAR | (hidden_cues << 16), 0)
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
            "GetDC": ([w.HWND], w.HDC), "ReleaseDC": ([w.HWND, w.HDC], c.c_int),
            "DrawTextW": ([w.HDC, w.LPCWSTR, c.c_int, c.POINTER(w.RECT), w.UINT], c.c_int),
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
        self.g.SelectObject.argtypes, self.g.SelectObject.restype = [w.HDC, w.HANDLE], w.HANDLE
        self.g.CreateDIBSection.argtypes = [w.HDC, c.c_void_p, w.UINT, c.POINTER(c.c_void_p), w.HANDLE, w.DWORD]
        self.g.CreateDIBSection.restype = w.HANDLE

    def _font(self, height: int, bold: bool = False):
        key = (height, bold)
        if key in self._font_cache:
            return self._font_cache[key]
        font = self.g.CreateFontW(-height, 0, 0, 0, 600 if bold else 400, 0, 0, 0, 1, 0, 0, 5, 0, "Segoe UI")
        self._fonts.append(font)
        self._font_cache[key] = font
        return font

    def _add(self, name: str, kind: str, text: str, bounds: Bounds, style: int,
             callback: Action | None = None, *, enabled: bool = True, font: int | None = None) -> int:
        identifier = 100 + len(self._controls)
        hwnd = self.u.CreateWindowExW(0, kind, text, WS_CHILD | WS_VISIBLE | style, *bounds,
                                      self.hwnd, identifier, self._instance, None)
        if not hwnd:
            raise c.WinError(c.get_last_error())
        self._controls[name] = _Control(hwnd, kind, identifier)
        self.u.SendMessageW(hwnd, WM_SETFONT, font or self.font, 1)
        self.u.EnableWindow(hwnd, enabled)
        if style & WS_TABSTOP:
            self._tab_order.append(name)
        if callback:
            self._callbacks[identifier] = callback
        return hwnd

    def label(self, name: str, text: str, bounds: Bounds, *, heading: bool = False) -> None:
        self._add(name, "Static", text, bounds, SS_NOPREFIX, font=self._font(28, True) if heading else None)
        self._label_bounds[name] = bounds
        self._label_heading[name] = heading
        self._fit_label(name)

    def text_height(self, name: str) -> int:
        """Measure native wrapped text with the control's actual GDI font."""
        hwnd = self._controls[name].handle
        dc = self.u.GetDC(hwnd)
        old_font = self.g.SelectObject(dc, self.u.SendMessageW(hwnd, 0x0031, 0, 0))  # WM_GETFONT
        try:
            rect = w.RECT(0, 0, self._label_bounds[name][2], 0)
            text = self.value(name)
            self.u.DrawTextW(dc, text, -1, c.byref(rect), 0x10 | 0x400 | 0x800)
            return rect.bottom - rect.top
        finally:
            self.g.SelectObject(dc, old_font)
            self.u.ReleaseDC(hwnd, dc)

    def _fit_label(self, name: str) -> None:
        heading = self._label_heading[name]
        for height in range(28 if heading else 16, 21 if heading else 13, -1):
            font = self._font(height, heading)
            self.u.SendMessageW(self._controls[name].handle, WM_SETFONT, font, 1)
            if self.text_height(name) <= self._label_bounds[name][3]:
                break

    def image(self, name: str, image, bounds: Bounds, *, description: str) -> None:
        """Keep a QR bitmap in memory, using a standard Static image control."""
        class BitmapHeader(c.Structure):
            _fields_ = [("size", w.DWORD), ("width", w.LONG), ("height", w.LONG),
                        ("planes", w.WORD), ("bits", w.WORD), ("compression", w.DWORD),
                        ("image_size", w.DWORD), ("x_ppm", w.LONG), ("y_ppm", w.LONG),
                        ("used", w.DWORD), ("important", w.DWORD)]
        rgb = image.convert("RGB")
        if rgb.size != bounds[2:]:
            raise ValueError("QR bitmap bounds must match its pixel size")
        pixels = rgb.tobytes("raw", "BGRX")
        header = BitmapHeader(c.sizeof(BitmapHeader), rgb.width, -rgb.height, 1, 32,
                              0, len(pixels), 0, 0, 0, 0)
        address = c.c_void_p()
        bitmap = self.g.CreateDIBSection(None, c.byref(header), 0, c.byref(address), None, 0)
        if not bitmap:
            raise c.WinError(c.get_last_error())
        self._bitmaps.append(bitmap)
        c.memmove(address, pixels, len(pixels))
        hwnd = self._add(name, "Static", description, bounds, 0x000E | 0x0200)
        self.u.SendMessageW(hwnd, 0x0172, 0, bitmap)  # STM_SETIMAGE / IMAGE_BITMAP

    def button(self, name: str, text: str, bounds: Bounds, action: Action, *, enabled: bool = True) -> None:
        self._add(name, "Button", text, bounds, WS_TABSTOP | BS_MULTILINE, action, enabled=enabled)

    def choices(self, name: str, text: str, items: Sequence[str], bounds: Bounds,
                on_change: Action, *, dropdown: bool = False) -> None:
        choice_style = CBS_DROPDOWNLIST | CBS_HASSTRINGS if dropdown else WS_BORDER | LBS_NOTIFY | LBS_NOINTEGRALHEIGHT
        hwnd = self._add(name, "ComboBox" if dropdown else "ListBox", text, bounds,
                         WS_TABSTOP | WS_VSCROLL | choice_style, on_change)
        message = CB_ADDSTRING if dropdown else LB_ADDSTRING
        for item in items:
            # Keep the UTF-16 buffer alive for the synchronous native call.
            # A temporary pointer converted to int can be freed before dispatch.
            buffer = c.create_unicode_buffer(item)
            self.u.SendMessageW(hwnd, message, 0, c.cast(buffer, c.c_void_p).value)

    def checkbox(self, name: str, text: str, bounds: Bounds, on_change: Action, checked: bool) -> None:
        # Native toggle-button appearance keeps system text/focus contrast.
        # It is still an auto-checkbox with the standard Toggle/UIA provider.
        self._add(name, "Button", text, bounds, WS_TABSTOP | BS_PUSHLIKE | BS_AUTOCHECKBOX, on_change)
        self.check(name, checked)

    def check(self, name: str, checked: bool | None = None) -> bool:
        hwnd = self._controls[name].handle
        if checked is not None:
            self.u.SendMessageW(hwnd, BM_SETCHECK, int(checked), 0)
        return bool(self.u.SendMessageW(hwnd, BM_GETCHECK, 0, 0))

    def selection(self, name: str, index: int | None = None, *, notify: bool = False) -> int:
        control = self._controls[name]
        dropdown = control.kind == "ComboBox"
        if index is not None:
            self.u.SendMessageW(control.handle, CB_SETCURSEL if dropdown else LB_SETCURSEL, index, 0)
            if notify and control.identifier in self._callbacks:
                self._callbacks[control.identifier]()
        return int(self.u.SendMessageW(control.handle, CB_GETCURSEL if dropdown else LB_GETCURSEL, 0, 0))

    def value(self, name: str) -> str:
        hwnd = self._controls[name].handle
        length = self.u.GetWindowTextLengthW(hwnd)
        buffer = c.create_unicode_buffer(length + 1)
        self.u.GetWindowTextW(hwnd, buffer, len(buffer))
        return buffer.value

    def text(self, name: str, value: str) -> None:
        hwnd = self._controls[name].handle
        # Only announce real changes, not every polling tick.
        if self.value(name) != value:
            self.u.SetWindowTextW(hwnd, value)
            if name in self._label_bounds:
                self._fit_label(name)
            self.u.NotifyWinEvent(EVENT_OBJECT_NAMECHANGE, hwnd, OBJID_CLIENT, 0)

    def title(self, value: str) -> None:
        self.u.SetWindowTextW(self.hwnd, value)

    def enable(self, name: str, enabled: bool) -> None:
        self.u.EnableWindow(self._controls[name].handle, enabled)

    def focus(self, name: str) -> None:
        self.u.SetFocus(self._controls[name].handle)

    def focused_name(self) -> str | None:
        focused = self.u.GetFocus()
        return next((name for name, control in self._controls.items() if control.handle == focused), None)

    def key(self, key: str, *, shift: bool = False) -> bool:
        if key == "Escape":
            self._on_escape()
            return True
        if key == "Tab":
            names = [name for name in self._tab_order if self.u.IsWindowEnabled(self._controls[name].handle)]
            if names:
                current = self.focused_name()
                index = names.index(current) if current in names else (0 if shift else -1)
                self.focus(names[(index + (-1 if shift else 1)) % len(names)])
            return True
        if key == "Enter":
            name = self.focused_name()
            if name and self._controls[name].kind == "Button":
                self.u.SendMessageW(self._controls[name].handle, BM_CLICK, 0, 0)
                return True
        return False

    def finish(self, result):
        self.result = result
        self.close()

    def _dispatch(self, hwnd, message, wp, lp):
        try:
            if message == WM_COMMAND:  # Real controls invoke the same actions as the mouse.
                identifier, event = wp & 0xFFFF, (wp >> 16) & 0xFFFF
                if event in {0, 1} and identifier in self._callbacks:
                    self._callbacks[identifier]()
                return 0
            if message == WM_CLOSE:
                self._on_close()
                return 0
            if message == WM_TIMER and self.on_tick:
                self.on_tick()
                return 0
            if message == WM_CTLCOLORSTATIC:  # Controls remain native.
                self.g.SetTextColor(wp, COLOR_TEXT)
                self.g.SetBkMode(wp, TRANSPARENT)
                return self._brush
            if message == WM_DESTROY and self._running:
                self.u.PostQuitMessage(0)
                return 0
        except BaseException as error:
            self._error = error
            if getattr(self, "hwnd", None):
                self.close()
            return 0
        return self.u.DefWindowProcW(hwnd, message, wp, lp)

    def run(self, *, poll_interval_ms: int = REFRESH_INTERVAL_MS):
        self._running = True
        self.u.ShowWindow(self.hwnd, SW_SHOW)
        self.u.SetForegroundWindow(self.hwnd)
        if self._tab_order:
            self.focus(self._tab_order[0])
        self.u.SetTimer(self.hwnd, REFRESH_TIMER_ID, poll_interval_ms, None)
        message = w.MSG()
        try:
            while True:
                received = self.u.GetMessageW(c.byref(message), None, 0, 0)
                if received == -1:
                    raise c.WinError(c.get_last_error())
                if not received:
                    break
                if message.message == WM_KEYDOWN:
                    key = KEY_NAMES.get(message.wParam)
                    if key and self.key(key, shift=bool(self.u.GetKeyState(VK_SHIFT) & KEY_PRESSED)):
                        continue
                if not self.u.IsDialogMessageW(self.hwnd, c.byref(message)):
                    self.u.TranslateMessage(c.byref(message))
                    self.u.DispatchMessageW(c.byref(message))
            if self._error:
                raise self._error
            return self.result
        finally:
            self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        hwnd = getattr(self, "hwnd", None)
        if hwnd:
            self.u.KillTimer(hwnd, REFRESH_TIMER_ID)
            self.u.DestroyWindow(hwnd)
        for font in self._fonts:
            self.g.DeleteObject(font)
        for bitmap in self._bitmaps:
            self.g.DeleteObject(bitmap)
        self.g.DeleteObject(self._brush)
        self.u.UnregisterClassW(self._class_name, self._instance)
