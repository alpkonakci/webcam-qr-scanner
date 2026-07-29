"""Windows system-tray controller for scanner modes and the future bridge."""

from __future__ import annotations

import subprocess
import threading
from collections.abc import Callable, Sequence

import pystray
from PIL import Image, ImageDraw

from app_settings import SettingsStore
from bridge_signals import (
    consume_bridge_exit_request,
    consume_camera_closed,
    consume_open_camera_request,
)
from exit_codes import APPLICATION_EXIT_REQUESTED
from native_dialogs import (
    MB_ICONWARNING,
    confirm_application_exit,
    show_dialog,
)
from process_launcher import spawn_application
from windows_startup import is_startup_enabled, set_startup_enabled


APPLICATION_NAME = "QR Scanner"
TRAY_ICON_NAME = "webcam-qr-scanner"
CONTROL_POLL_SECONDS = 0.4
CHILD_EXIT_TIMEOUT_SECONDS = 2.0


def create_tray_image(size: int = 64) -> Image.Image:
    """Create a small high-contrast QR-style tray icon."""

    image = Image.new("RGBA", (size, size), (11, 18, 32, 255))
    draw = ImageDraw.Draw(image)
    accent = (45, 212, 191, 255)
    inset = max(5, size // 8)
    marker_size = max(10, size // 4)
    stroke = max(3, size // 16)
    for left, top in (
        (inset, inset),
        (size - inset - marker_size, inset),
        (inset, size - inset - marker_size),
    ):
        draw.rectangle(
            (left, top, left + marker_size, top + marker_size),
            outline=accent,
            width=stroke,
        )
    draw.rectangle(
        (
            size // 2,
            size // 2,
            size - inset,
            size - inset,
        ),
        fill=accent,
    )
    return image


class TrayApplication:
    """Own the tray lifecycle and independent camera/screen child processes."""

    def __init__(
        self,
        *,
        open_camera_on_start: bool = False,
        camera_arguments: Sequence[str] = (),
        settings_store: SettingsStore | None = None,
        process_spawner: Callable[
            [list[str]],
            subprocess.Popen[bytes],
        ] = spawn_application,
    ) -> None:
        self.open_camera_on_start = open_camera_on_start
        self.camera_arguments = tuple(camera_arguments)
        self.settings_store = settings_store or SettingsStore()
        self.process_spawner = process_spawner
        self._stop_event = threading.Event()
        self._children: set[subprocess.Popen[bytes]] = set()
        self._camera_process: subprocess.Popen[bytes] | None = None
        self._children_lock = threading.RLock()
        self.icon = pystray.Icon(
            TRAY_ICON_NAME,
            create_tray_image(),
            f"{APPLICATION_NAME} — Phone-to-PC not paired",
            self._build_menu(),
        )

    def _build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem(
                "Scan with Camera",
                self._scan_with_camera,
                default=True,
            ),
            pystray.MenuItem("Scan Screen", self._scan_screen),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Phone-to-PC: Not paired",
                lambda *_: None,
                enabled=False,
            ),
            pystray.MenuItem(
                "Pair Phone... (coming in v0.2)",
                self._pair_phone,
            ),
            pystray.MenuItem(
                "Start with Windows",
                self._toggle_startup,
                checked=lambda _: is_startup_enabled(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit QR Scanner", self._exit_from_menu),
        )

    def run(self) -> None:
        """Run until the user explicitly exits or a camera requests full exit."""

        try:
            self.icon.run(setup=self._setup)
        finally:
            self._stop_event.set()
            self._terminate_children()

    def _setup(self, icon: pystray.Icon) -> None:
        icon.visible = True
        threading.Thread(
            target=self._watch_control_requests,
            name="bridge-control",
            daemon=True,
        ).start()
        if self.open_camera_on_start:
            self._launch_camera()

    def _scan_with_camera(
        self,
        _: pystray.Icon,
        __: pystray.MenuItem,
    ) -> None:
        self._launch_camera()

    def _scan_screen(
        self,
        _: pystray.Icon,
        __: pystray.MenuItem,
    ) -> None:
        self._launch_child(["--screen-process", "--desktop"])

    def _pair_phone(
        self,
        _: pystray.Icon,
        __: pystray.MenuItem,
    ) -> None:
        show_dialog(
            "QR Scanner - Pair Phone",
            (
                "Phone-to-PC pairing is not enabled in this development "
                "build yet.\n\n"
                "The encrypted relay and mobile PWA must be connected and "
                "tested before this option can be released safely."
            ),
            MB_ICONWARNING,
        )

    def _toggle_startup(
        self,
        icon: pystray.Icon,
        __: pystray.MenuItem,
    ) -> None:
        enabled = not is_startup_enabled()
        try:
            set_startup_enabled(enabled)
        except OSError as error:
            show_dialog(
                "QR Scanner - Startup error",
                str(error),
                MB_ICONWARNING,
            )
        icon.update_menu()

    def _exit_from_menu(
        self,
        _: pystray.Icon,
        __: pystray.MenuItem,
    ) -> None:
        if confirm_application_exit():
            self._stop()

    def _launch_camera(
        self,
        arguments: Sequence[str] | None = None,
    ) -> None:
        with self._children_lock:
            if (
                self._camera_process is not None
                and self._camera_process.poll() is None
            ):
                self._notify(
                    "The camera scanner is already open.",
                    "QR Scanner",
                )
                return

            camera_arguments = (
                self.camera_arguments if arguments is None else tuple(arguments)
            )
            self._launch_child(
                [
                    "--camera-process",
                    "--desktop",
                    *camera_arguments,
                ],
                camera=True,
            )

    def _launch_child(
        self,
        arguments: list[str],
        *,
        camera: bool = False,
    ) -> subprocess.Popen[bytes]:
        process = self.process_spawner(arguments)
        with self._children_lock:
            self._children.add(process)
            if camera:
                self._camera_process = process
        threading.Thread(
            target=self._monitor_child,
            args=(process,),
            name="scanner-child-monitor",
            daemon=True,
        ).start()
        return process

    def _monitor_child(
        self,
        process: subprocess.Popen[bytes],
    ) -> None:
        return_code = process.wait()
        with self._children_lock:
            self._children.discard(process)
            if process is self._camera_process:
                self._camera_process = None
        if return_code == APPLICATION_EXIT_REQUESTED:
            self._stop()

    def _show_camera_closed_notice_once(self) -> None:
        settings = self.settings_store.load()
        if settings.camera_closed_notice_shown:
            return
        notification_was_sent = self._notify(
            (
                "Camera closed. QR Scanner is still running in the system "
                "tray. Use the tray icon to scan again or exit completely."
            ),
            "QR Scanner",
        )
        if notification_was_sent:
            self.settings_store.update(camera_closed_notice_shown=True)

    def _notify(self, message: str, title: str) -> bool:
        if not self.icon.HAS_NOTIFICATION:
            return False
        try:
            self.icon.notify(message, title)
            return True
        except (NotImplementedError, OSError):
            return False

    def _watch_control_requests(self) -> None:
        while not self._stop_event.wait(CONTROL_POLL_SECONDS):
            if consume_bridge_exit_request():
                self._stop()
                return
            camera_arguments = consume_open_camera_request()
            if camera_arguments is not None:
                self._launch_camera(camera_arguments)
            if consume_camera_closed():
                self._show_camera_closed_notice_once()

    def _stop(self) -> None:
        if self._stop_event.is_set():
            return
        self._stop_event.set()
        self.icon.stop()

    def _terminate_children(self) -> None:
        with self._children_lock:
            processes = tuple(self._children)
            self._children.clear()
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            if process.poll() is not None:
                continue
            try:
                process.wait(timeout=CHILD_EXIT_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                process.kill()
