"""Small settings/about window; startup changes only on an explicit click."""
from __future__ import annotations
import tkinter as tk
import webbrowser
from collections.abc import Callable
from app_info import APP_VERSION, RELEASES_URL
from desktop_i18n import get_language, set_language, t
from qr_creator_ui import _window, _label, _button, BACKGROUND, PANEL, INK, MUTED, ACCENT
from windows_startup import is_startup_enabled, set_startup_enabled


class SettingsWindow:
    def __init__(self, root: tk.Tk, *, startup_reader: Callable[[], bool] = is_startup_enabled,
                 startup_writer: Callable[[bool], None] = set_startup_enabled,
                 language_writer: Callable[[str], None] = set_language):
        self.root, self.reader, self.writer, self.language_writer = root, startup_reader, startup_writer, language_writer
        self.body: tk.Frame | None = None
        self.build()

    def build(self):
        if self.body is not None: self.body.destroy()
        self.root.title(t("Settings and about"))
        body = self.body = tk.Frame(self.root, bg=BACKGROUND, padx=28, pady=22)
        body.pack(fill="both", expand=True)
        _label(body, t("Settings and about"), size=23, color=INK).pack(fill="x", pady=(0, 24))
        row = tk.Frame(body, bg=BACKGROUND); row.pack(fill="x", pady=8)
        _label(row, t("Language"), size=12, color=INK).pack(side="left")
        selected = tk.StringVar(value="Türkçe" if get_language() == "tr" else "English")
        menu = tk.OptionMenu(row, selected, "Türkçe", "English", command=self.choose_language)
        menu.configure(bg=PANEL, fg=INK, activebackground=ACCENT, relief="flat", highlightthickness=1)
        menu.pack(side="right")
        self.startup = tk.BooleanVar(value=self.reader())
        tk.Checkbutton(body, text=t("Start with Windows"), variable=self.startup, command=self.toggle_startup,
                       bg=BACKGROUND, fg=INK, selectcolor=PANEL, activebackground=BACKGROUND,
                       activeforeground=INK, anchor="w").pack(fill="x", pady=(20, 3))
        _label(body, t("Starts in the tray; the camera stays off.")).pack(fill="x")
        _label(body, f"{t('Version')}: {APP_VERSION}", color=INK, size=12).pack(fill="x", pady=(28, 12))
        _button(body, t("Official downloads"), lambda: webbrowser.open(RELEASES_URL)).pack(anchor="w")
        _label(body, t("MIT license · Free to use")).pack(fill="x", pady=(15, 0))
        self.message = _label(body, t("Preferences are saved on this device."), size=9)
        self.message.pack(fill="x", pady=(4, 15))
        _button(body, t("Back"), self.root.destroy, primary=True).pack(side="right")

    def choose_language(self, value: str):
        try:
            self.language_writer("tr" if value == "Türkçe" else "en")
            self.build()
        except OSError:
            self.message.configure(text=t("Language preference could not be saved."), fg="#FBBF24")

    def toggle_startup(self):
        try:
            self.writer(bool(self.startup.get()))
            self.startup.set(self.reader())
        except OSError:
            self.startup.set(self.reader())
            self.message.configure(text=t("Startup could not be changed. Try again."), fg="#FBBF24")


def show_settings_window() -> None:
    from accessible_controls import available
    if available():
        from accessible_desktop import settings_controls
        settings_controls().run()
        return
    root = _window("Settings and about", "620x490")
    SettingsWindow(root)
    root.mainloop()
