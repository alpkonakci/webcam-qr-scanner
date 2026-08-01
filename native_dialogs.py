"""Small native dialogs that do not import the camera stack."""

from __future__ import annotations

import ctypes
import os
import threading


MB_OK = 0x00
MB_YESNO = 0x04
MB_ICONERROR = 0x10
MB_ICONWARNING = 0x30
MB_DEFBUTTON2 = 0x100
MB_SETFOREGROUND = 0x10000
MB_TOPMOST = 0x40000
IDYES = 6


_DIALOG_LOCK = threading.RLock()


def show_dialog(title: str, message: str, style: int = MB_OK) -> int:
    """Show a native Windows message box and return the selected button."""

    if os.name != "nt":
        return 0
    # These dialogs are often requested by a tray or receiver thread. Without
    # foreground flags Windows may place an ownerless message box behind the
    # home or pairing window. Serializing them also prevents an exit question
    # and an incoming-link question from covering each other.
    with _DIALOG_LOCK:
        return int(
            ctypes.windll.user32.MessageBoxW(
                0,
                message,
                title,
                style | MB_SETFOREGROUND | MB_TOPMOST,
            )
        )


def show_error_dialog(title: str, message: str) -> None:
    """Show an error for a windowed application without a terminal."""

    show_dialog(title, message, MB_ICONERROR)


def confirm_application_exit() -> bool:
    """Confirm an action that stops every part of the application."""

    message = (
        "Exit QR Scanner completely?\n\n"
        "The background controller and any active Phone-to-PC connection will "
        "stop.\n\n"
        "Choose No to keep QR Scanner running in the system tray."
    )
    return (
        show_dialog(
            "QR Scanner - Exit",
            message,
            MB_YESNO | MB_ICONWARNING | MB_DEFBUTTON2,
        )
        == IDYES
    )


def confirm_phone_url(
    url: str,
    hostname_ascii: str,
    *,
    phone_label: str,
) -> bool:
    """Ask before opening a URL delivered by a paired phone."""

    secure_note = (
        ""
        if url.lower().startswith("https://")
        else "\n\nWarning: This website uses an unencrypted HTTP connection."
    )
    message = (
        f"{phone_label} sent this web address.\n\n"
        f"Website:\n{hostname_ascii}\n\n"
        f"Full address:\n{url[:900]}"
        f"{'...' if len(url) > 900 else ''}"
        f"{secure_note}\n\n"
        "Open it in the default browser?"
    )
    return (
        show_dialog(
            "QR Scanner - Phone-to-PC",
            message,
            MB_YESNO | MB_ICONWARNING | MB_DEFBUTTON2,
        )
        == IDYES
    )


def confirm_phone_pairing(
    phone_label: str,
    *,
    relay_origin: str,
) -> bool:
    """Ask before granting a mobile browser permission to send URLs."""

    message = (
        "A mobile browser wants to pair with this computer.\n\n"
        f"Device name:\n{phone_label}\n\n"
        "Client:\nMobile PWA\n\n"
        f"Relay:\n{relay_origin}\n\n"
        "Approve this device?\n\n"
        "Only approve while the pairing QR is visible on this computer."
    )
    return (
        show_dialog(
            "QR Scanner - Pair Phone",
            message,
            MB_YESNO | MB_ICONWARNING | MB_DEFBUTTON2,
        )
        == IDYES
    )
