"""Calm, package-friendly control center shown after the camera closes."""

from __future__ import annotations

import ctypes
import os
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


WINDOW_TITLE = "QR Scanner"
WINDOW_WIDTH = 620
WINDOW_HEIGHT = 540
WINDOW_BACKGROUND = "#0B1220"
PANEL_BACKGROUND = "#111C2E"
PANEL_HOVER = "#17263D"
PRIMARY_TEXT = "#F8FAFC"
SECONDARY_TEXT = "#A7B2C4"
ACCENT = "#2DD4BF"
WARNING = "#FBBF24"
DEFAULT_SCREEN_SIZE = (1280, 720)


class HomeAction(Enum):
    BACKGROUND = "background"
    SCAN_CAMERA = "scan_camera"
    SCAN_SCREEN = "scan_screen"
    PAIR_PHONE = "pair_phone"
    EXIT = "exit"


@dataclass(frozen=True, slots=True)
class ActionCard:
    action: HomeAction
    bounds: tuple[int, int, int, int]
    title: str
    description: str
    accent: str = ACCENT


ACTION_CARDS = (
    ActionCard(
        HomeAction.SCAN_CAMERA,
        (32, 116, 588, 206),
        "Scan with Camera",
        "Open the webcam and place a QR code inside the frame.",
    ),
    ActionCard(
        HomeAction.SCAN_SCREEN,
        (32, 220, 588, 310),
        "Scan Computer Screen",
        "Read a QR code that is currently visible on this PC.",
    ),
    ActionCard(
        HomeAction.PAIR_PHONE,
        (32, 324, 588, 414),
        "Pair a Phone",
        "Connect a mobile browser securely. v0.2 preview",
        WARNING,
    ),
)
EXIT_BOUNDS = (456, 470, 588, 510)


@dataclass(slots=True)
class HomeWindowState:
    hover_action: HomeAction | None = None
    selected_action: HomeAction | None = None


def action_at_point(x: int, y: int) -> HomeAction | None:
    """Return an action only when the pointer is inside a visible control."""

    for card in ACTION_CARDS:
        if _contains(card.bounds, x, y):
            return card.action
    if _contains(EXIT_BOUNDS, x, y):
        return HomeAction.EXIT
    return None


def build_home_canvas(
    *,
    hover_action: HomeAction | None = None,
) -> np.ndarray:
    """Render the complete control center with sharp system-font text."""

    canvas = Image.new(
        "RGB",
        (WINDOW_WIDTH, WINDOW_HEIGHT),
        WINDOW_BACKGROUND,
    )
    draw = ImageDraw.Draw(canvas)
    title_font = _load_font(29, semibold=True)
    subtitle_font = _load_font(16)
    card_title_font = _load_font(19, semibold=True)
    card_body_font = _load_font(14)
    small_font = _load_font(13)
    button_font = _load_font(14, semibold=True)

    draw.text(
        (32, 26),
        "QR SCANNER",
        font=title_font,
        fill=PRIMARY_TEXT,
    )
    draw.text(
        (32, 70),
        "Choose what you want to do.",
        font=subtitle_font,
        fill=SECONDARY_TEXT,
    )

    for card in ACTION_CARDS:
        hovered = card.action is hover_action
        draw.rounded_rectangle(
            card.bounds,
            radius=16,
            fill=PANEL_HOVER if hovered else PANEL_BACKGROUND,
            outline=card.accent if hovered else None,
            width=2 if hovered else 1,
        )
        left, top, _, _ = card.bounds
        draw.rounded_rectangle(
            (left + 18, top + 18, left + 24, top + 72),
            radius=3,
            fill=card.accent,
        )
        draw.text(
            (left + 42, top + 17),
            card.title,
            font=card_title_font,
            fill=PRIMARY_TEXT,
        )
        draw.text(
            (left + 42, top + 53),
            card.description,
            font=card_body_font,
            fill=SECONDARY_TEXT,
        )

    draw.text(
        (32, 478),
        "Close this window to keep QR Scanner running in the tray.",
        font=small_font,
        fill=SECONDARY_TEXT,
    )
    exit_hovered = hover_action is HomeAction.EXIT
    draw.rounded_rectangle(
        EXIT_BOUNDS,
        radius=11,
        fill=PANEL_HOVER if exit_hovered else PANEL_BACKGROUND,
        outline=WARNING if exit_hovered else None,
        width=2 if exit_hovered else 1,
    )
    exit_text = "Exit"
    exit_width = draw.textlength(exit_text, font=button_font)
    left, top, right, bottom = EXIT_BOUNDS
    draw.text(
        (
            left + (right - left - exit_width) / 2,
            top + (bottom - top - _font_line_height(button_font)) / 2 - 2,
        ),
        exit_text,
        font=button_font,
        fill=PRIMARY_TEXT,
    )

    rgb = np.asarray(canvas, dtype=np.uint8)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def show_home_window(
    *,
    confirm_exit: Callable[[], bool] | None = None,
) -> HomeAction:
    """Show the control center; Escape and window close keep the tray alive."""

    state = HomeWindowState()

    def handle_mouse(
        event: int,
        x: int,
        y: int,
        _: int,
        __: object,
    ) -> None:
        state.hover_action = action_at_point(x, y)
        if event == cv2.EVENT_LBUTTONUP:
            state.selected_action = state.hover_action

    cv2.namedWindow(WINDOW_TITLE, cv2.WINDOW_AUTOSIZE)
    cv2.setMouseCallback(WINDOW_TITLE, handle_mouse)
    screen_width, screen_height = _primary_screen_size()
    cv2.moveWindow(
        WINDOW_TITLE,
        max(0, (screen_width - WINDOW_WIDTH) // 2),
        max(0, (screen_height - WINDOW_HEIGHT) // 3),
    )

    try:
        first_frame = True
        while True:
            cv2.imshow(
                WINDOW_TITLE,
                build_home_canvas(hover_action=state.hover_action),
            )
            if first_frame:
                _bring_home_window_to_front()
                first_frame = False
            if cv2.waitKey(16) & 0xFF == 27:
                return HomeAction.BACKGROUND
            if (
                cv2.getWindowProperty(
                    WINDOW_TITLE,
                    cv2.WND_PROP_VISIBLE,
                )
                < 1
            ):
                return HomeAction.BACKGROUND
            if state.selected_action is None:
                continue
            if (
                state.selected_action is HomeAction.EXIT
                and confirm_exit is not None
                and not confirm_exit()
            ):
                state.selected_action = None
                state.hover_action = None
                continue
            return state.selected_action
    finally:
        try:
            cv2.destroyWindow(WINDOW_TITLE)
        except cv2.error:
            pass


def _contains(
    bounds: tuple[int, int, int, int],
    x: int,
    y: int,
) -> bool:
    left, top, right, bottom = bounds
    return left <= x <= right and top <= y <= bottom


def _load_font(size: int, *, semibold: bool = False) -> ImageFont.ImageFont:
    windows_directory = Path(os.environ.get("WINDIR", r"C:\Windows"))
    filename = "seguisb.ttf" if semibold else "segoeui.ttf"
    try:
        return ImageFont.truetype(
            str(windows_directory / "Fonts" / filename),
            size=size,
        )
    except OSError:
        return ImageFont.load_default()


def _font_line_height(font: ImageFont.ImageFont) -> int:
    _, top, _, bottom = font.getbbox("Ag")
    return max(1, bottom - top)


def _primary_screen_size() -> tuple[int, int]:
    if os.name != "nt":
        return DEFAULT_SCREEN_SIZE
    try:
        user32 = ctypes.windll.user32
        width = int(user32.GetSystemMetrics(0))
        height = int(user32.GetSystemMetrics(1))
        if width > 0 and height > 0:
            return width, height
    except (AttributeError, OSError):
        pass
    return DEFAULT_SCREEN_SIZE


def _bring_home_window_to_front() -> None:
    """Raise the control center once without leaving it always on top."""

    try:
        cv2.setWindowProperty(WINDOW_TITLE, cv2.WND_PROP_TOPMOST, 1)
    except cv2.error:
        pass

    try:
        if os.name == "nt":
            user32 = ctypes.windll.user32
            find_window = user32.FindWindowW
            find_window.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p)
            find_window.restype = ctypes.c_void_p
            window_handle = find_window(None, WINDOW_TITLE)
            if window_handle:
                user32.ShowWindow(window_handle, 9)  # SW_RESTORE
                user32.BringWindowToTop(window_handle)
                user32.SetForegroundWindow(window_handle)
    except (AttributeError, OSError, TypeError, ValueError):
        pass
    finally:
        try:
            cv2.setWindowProperty(WINDOW_TITLE, cv2.WND_PROP_TOPMOST, 0)
        except cv2.error:
            pass
