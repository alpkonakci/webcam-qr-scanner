"""Small offline creator and read-only text result windows."""

from __future__ import annotations

from desktop_i18n import t

import queue
import threading
import tkinter as tk
from tkinter import filedialog

from PIL import Image, ImageTk

from clipboard_support import copy_image, copy_text
from qr_creator import CreatedQR, create_qr, validate_creation_value
from window_icon import icon_path, set_window_icon


BACKGROUND, PANEL, INK, MUTED, ACCENT = "#0B1220", "#111C2E", "#F8FAFC", "#A7B2C4", "#2DD4BF"


def _window(title: str, size: str) -> tk.Tk:
    root = tk.Tk()
    root.title(title)
    root.configure(bg=BACKGROUND)
    root.geometry(size)
    root.resizable(False, False)
    try:
        root.iconbitmap(default=str(icon_path()))
    except tk.TclError:
        pass  # A missing platform icon must not block offline QR creation.
    root.option_add("*Font", "{Segoe UI} 10")
    root.bind("<Escape>", lambda _: root.destroy())
    root.after(50, lambda: set_window_icon(title))
    return root


def _label(parent, text: str, *, size: int = 10, color: str = MUTED):
    return tk.Label(parent, text=t(text), bg=BACKGROUND, fg=color, font=("Segoe UI", size), anchor="w")


def _button(parent, text: str, command, *, primary: bool = False):
    return tk.Button(parent, text=t(text), command=command, bg=ACCENT if primary else PANEL,
                     fg=BACKGROUND if primary else INK, activebackground=ACCENT,
                     activeforeground=BACKGROUND, relief="flat", padx=16, pady=10,
                     cursor="hand2", disabledforeground=MUTED)


class CreatorWindow:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.kind = tk.StringVar(value="link")
        self.current: CreatedQR | None = None
        self.revision = 0
        self.timer = None
        self.closed = False
        self.worker_active = False
        self.pending = None
        self.results: queue.Queue = queue.Queue()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<Escape>", lambda _: self.close())
        body = tk.Frame(root, bg=BACKGROUND, padx=28, pady=22)
        body.pack(fill="both", expand=True)
        _label(body, t("CREATE QR"), size=22, color=INK).pack(fill="x")
        _label(body, t("A link or short text. Created only on this computer.")).pack(fill="x", pady=(5, 16))
        choices = tk.Frame(body, bg=BACKGROUND)
        choices.pack(fill="x")
        for value, title in (("link", t("Link")), ("text", t("Text"))):
            tk.Radiobutton(choices, text=title, value=value, variable=self.kind,
                           command=self.changed, bg=BACKGROUND, fg=INK, selectcolor=PANEL,
                           activebackground=BACKGROUND, activeforeground=INK).pack(side="left", padx=(0, 20))
        self.input = tk.Text(body, height=4, wrap="word", bg=PANEL, fg=INK, insertbackground=INK,
                             relief="flat", padx=12, pady=10, undo=True)
        self.input.pack(fill="x", pady=(10, 5))
        self.input.bind("<<Modified>>", self._modified)
        self.input.edit_modified(False)
        _label(body, t("Video, GIF or PDF? Paste its sharing link. No files are uploaded."), size=9).pack(fill="x")
        self.preview = tk.Label(body, bg=PANEL, fg=MUTED, text=t("Your QR preview appears here"), width=320, height=320)
        # Pixel dimensions require an image; avoid character-based label widths.
        self.blank = ImageTk.PhotoImage(Image.new("RGB", (320, 320), PANEL))
        self.preview.configure(image=self.blank, compound="center")
        self.preview.pack(pady=12)
        self.message = _label(body, "", size=9)
        self.message.pack(fill="x")
        actions = tk.Frame(body, bg=BACKGROUND)
        actions.pack(fill="x", pady=(12, 0))
        self.save_button = _button(actions, t("Save PNG"), self.save, primary=True)
        self.save_button.pack(side="left")
        self.copy_button = _button(actions, t("Copy QR"), self.copy)
        self.copy_button.pack(side="left", padx=10)
        _button(actions, t("Back"), self.close).pack(side="right")
        self._enable(False)
        root.after(50, self.poll)
        self.input.focus_set()

    def _enable(self, enabled: bool):
        for button in (self.save_button, self.copy_button):
            button.configure(state="normal" if enabled else "disabled")
        self.save_button.configure(bg=ACCENT if enabled else PANEL)

    def _modified(self, _):
        if self.input.edit_modified():
            self.input.edit_modified(False)
            self.changed()

    def changed(self):
        self.revision += 1
        self.pending = None
        self.current = None
        self._enable(False)
        self.preview.configure(image=self.blank, text=t("Your QR preview appears here"))
        if self.timer is not None:
            self.root.after_cancel(self.timer)
        self.timer = self.root.after(350, self.generate)

    def generate(self):
        self.timer = None
        value, kind, revision = self.input.get("1.0", "end-1c"), self.kind.get(), self.revision
        if not value.strip():
            self.message.configure(text=t("Enter a complete link or short text."), fg=MUTED)
            return
        try:
            validate_creation_value(value, kind)
        except ValueError as error:
            self.message.configure(text=t(str(error)), fg="#FBBF24")
            return
        if self.worker_active:
            self.pending = (value, kind, revision)
            return
        self._start_worker(value, kind, revision)

    def _start_worker(self, value, kind, revision):
        self.worker_active = True
        self.message.configure(text=t("Creating QR…"), fg=MUTED)
        def work():
            try:
                self.results.put((revision, create_qr(value, kind)))
            except Exception:
                self.results.put((revision, ValueError(t("Could not create this QR. Try shorter content."))))
        threading.Thread(target=work, name="offline-qr-create", daemon=True).start()

    def poll(self):
        if self.closed:
            return
        try:
            while True:
                revision, result = self.results.get_nowait()
                self.worker_active = False
                if self.pending is not None:
                    pending, self.pending = self.pending, None
                    self._start_worker(*pending)
                if revision != self.revision:
                    continue
                if isinstance(result, Exception):
                    self.message.configure(text=t(str(result)), fg="#FBBF24")
                    continue
                self.current = result
                # Nearest-neighbour resizing avoids blurring the preview.
                small = result.image.copy()
                small.thumbnail((320, 320), Image.Resampling.NEAREST)
                self.photo = ImageTk.PhotoImage(small)
                self.preview.configure(image=self.photo, text="")
                self.message.configure(text=t("Ready. Anyone who scans this QR can read its content."), fg=MUTED)
                self._enable(True)
        except queue.Empty:
            pass
        self.root.after(50, self.poll)

    def save(self):
        current = self.current
        if current is None:
            return
        destination = filedialog.asksaveasfilename(parent=self.root, title=t("Save QR as PNG"),
                    defaultextension=".png", initialfile="qr-code.png", filetypes=[(t("PNG image"), "*.png")])
        if not destination:
            return
        try:
            current.image.save(destination, format="PNG")
            self.message.configure(text=t("PNG saved."), fg=ACCENT)
        except OSError:
            self.message.configure(text=t("Could not save the PNG. Choose another location."), fg="#FBBF24")

    def copy(self):
        if self.current is None:
            return
        try:
            copy_image(self.current.image, owner=self.root.winfo_id())
            self.message.configure(text=t("QR copied. Paste it into a message or document."), fg=ACCENT)
        except OSError as error:
            self.message.configure(text=t(str(error)), fg="#FBBF24")

    def close(self):
        self.closed = True
        self.current = None
        self.root.destroy()


def show_creator_window() -> None:
    root = _window(t("QR Scanner - Create QR"), "620x710")
    CreatorWindow(root)
    root.mainloop()


def show_text_result(value: str) -> None:
    root = _window(t("QR Scanner - Text"), "620x420")
    body = tk.Frame(root, bg=BACKGROUND, padx=28, pady=22)
    body.pack(fill="both", expand=True)
    _label(body, t("TEXT QR"), size=22, color=INK).pack(fill="x")
    _label(body, t("Text only. Nothing was opened or sent.")).pack(fill="x", pady=(6, 16))
    field = tk.Text(body, height=9, wrap="word", bg=PANEL, fg=INK, relief="flat", padx=12, pady=12)
    field.insert("1.0", value)
    field.configure(state="disabled")
    field.pack(fill="both", expand=True)
    message = _label(body, t("Copy only content you trust."), size=9)
    message.pack(fill="x", pady=8)
    def copy():
        try:
            copy_text(value, owner=root.winfo_id())
            message.configure(text=t("Text copied."), fg=ACCENT)
        except (OSError, ValueError, UnicodeError):
            message.configure(text=t("Text could not be copied. Select and copy it manually."), fg="#FBBF24")
    _button(body, t("Copy text"), copy, primary=True).pack(side="left")
    _button(body, t("Back"), root.destroy).pack(side="right")
    root.mainloop()
