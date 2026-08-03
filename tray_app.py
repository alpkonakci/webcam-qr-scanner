"""Windows system-tray controller for scanner modes and the future bridge."""

from __future__ import annotations

import subprocess
import threading
from collections.abc import Callable, Sequence
from enum import Enum

import pystray
from PIL import Image, ImageDraw

from bridge_signals import (
    consume_bridge_exit_request,
    consume_camera_closed,
    consume_open_camera_request,
)
from bridge.receiver_service import ReceiverService
from exit_codes import (
    APPLICATION_EXIT_REQUESTED,
    CONTROL_EXIT_REQUESTED,
    CONTROL_PAIR_PHONE,
    CONTROL_SCAN_CAMERA,
    CONTROL_SCAN_SCREEN,
)
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


class ChildRole(Enum):
    CAMERA = "camera"
    SCREEN = "screen"
    HOME = "home"


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
        process_spawner: Callable[
            [list[str]],
            subprocess.Popen[bytes],
        ] = spawn_application,
        pairing_runner: Callable[[], object] | None = None,
        receiver_service: ReceiverService | None = None,
    ) -> None:
        self.open_camera_on_start = open_camera_on_start
        self.camera_arguments = tuple(camera_arguments)
        self.process_spawner = process_spawner
        self.pairing_runner = pairing_runner or self._default_pairing_runner
        self._stop_event = threading.Event()
        self._pairing_cancel_event = threading.Event()
        self._pairing_window_closed = threading.Event()
        self._pairing_window_closed.set()
        self.receiver_service = receiver_service or ReceiverService(
            before_prompt=self._prepare_for_foreground_dialog,
            after_prompt=self._finish_foreground_dialog,
        )
        self._children: set[subprocess.Popen[bytes]] = set()
        self._camera_process: subprocess.Popen[bytes] | None = None
        self._home_process: subprocess.Popen[bytes] | None = None
        self._pairing_thread: threading.Thread | None = None
        self._children_lock = threading.RLock()
        self._exit_prompt_lock = threading.Lock()
        self._foreground_dialog_count = 0
        pairing_status = (
            "ready"
            if self.receiver_service.has_paired_phones()
            else "not paired"
        )
        self.icon = pystray.Icon(
            TRAY_ICON_NAME,
            create_tray_image(),
            f"{APPLICATION_NAME} — Phone-to-PC {pairing_status}",
            self._build_menu(),
        )

    def _build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem(
                "Open QR Scanner",
                self._open_home,
                default=True,
            ),
            pystray.MenuItem("Scan with Camera", self._scan_with_camera),
            pystray.MenuItem("Scan Screen", self._scan_screen),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Phone-to-PC: v0.2 preview",
                lambda *_: None,
                enabled=False,
            ),
            pystray.MenuItem(
                "Pair Phone...",
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
            self.receiver_service.stop()
            self._terminate_children()

    def _setup(self, icon: pystray.Icon) -> None:
        icon.visible = True
        self.receiver_service.start()
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

    def _open_home(
        self,
        _: pystray.Icon,
        __: pystray.MenuItem,
    ) -> None:
        self._launch_home()

    def _scan_screen(
        self,
        _: pystray.Icon,
        __: pystray.MenuItem,
    ) -> None:
        self._launch_screen()

    def _pair_phone(
        self,
        _: pystray.Icon,
        __: pystray.MenuItem,
    ) -> None:
        self._start_pairing()

    def _start_pairing(self) -> None:
        with self._children_lock:
            if (
                self._pairing_thread is not None
                and self._pairing_thread.is_alive()
            ):
                self._notify(
                    "A phone pairing window is already open.",
                    "QR Scanner",
                )
                return
            self._dismiss_home_locked()
            self._pairing_cancel_event.clear()
            self._pairing_window_closed.clear()
            self._pairing_thread = threading.Thread(
                target=self._run_pairing,
                name="phone-pairing",
                daemon=True,
            )
            self._pairing_thread.start()

    def _run_pairing(self) -> None:
        try:
            result = self.pairing_runner()
            status = getattr(getattr(result, "status", None), "value", "")
            phone_label = getattr(result, "phone_label", None)
            if status == "approved":
                self.receiver_service.request_refresh()
                self.icon.title = f"{APPLICATION_NAME} — Phone-to-PC ready"
                self._notify(
                    f"{phone_label or 'Phone'} was paired securely.",
                    "QR Scanner",
                )
            elif status == "rejected":
                self._notify(
                    "The phone pairing request was rejected.",
                    "QR Scanner",
                )
            elif status == "expired":
                self._notify(
                    "The pairing code expired. Open Pair Phone to try again.",
                    "QR Scanner",
                )
        except Exception as error:
            show_dialog(
                "QR Scanner - Pairing unavailable",
                _pairing_error_message(error),
                MB_ICONWARNING,
            )
        finally:
            self._pairing_window_closed.set()
            with self._children_lock:
                self._pairing_thread = None
            if not self._stop_event.is_set():
                self._launch_home()

    def _default_pairing_runner(self) -> object:
        from bridge.pairing_controller import (
            PairingController,
            configured_relay_origin,
        )

        return PairingController(
            relay_origin=configured_relay_origin(),
            cancel_event=self._pairing_cancel_event,
            window_closed_event=self._pairing_window_closed,
        ).run()

    def _prepare_for_foreground_dialog(self) -> None:
        """Remove transient UI before a modal security decision appears."""

        with self._children_lock:
            self._foreground_dialog_count += 1
        self._pairing_cancel_event.set()
        self._pairing_window_closed.wait(timeout=1.0)
        process = self._dismiss_home()
        self._wait_for_child_exit(process)

    def _finish_foreground_dialog(self, opened_external_window: bool) -> None:
        """Restore the control center only when no browser took focus."""

        with self._children_lock:
            self._foreground_dialog_count = max(
                0,
                self._foreground_dialog_count - 1,
            )
            should_restore = (
                self._foreground_dialog_count == 0
                and not opened_external_window
                and not self._stop_event.is_set()
            )
        if should_restore:
            self._launch_home()

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
        self._request_full_exit()

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

            self._dismiss_home_locked()
            camera_arguments = (
                self.camera_arguments if arguments is None else tuple(arguments)
            )
            self._launch_child(
                [
                    "--camera-process",
                    "--desktop",
                    *camera_arguments,
                ],
                role=ChildRole.CAMERA,
            )

    def _launch_screen(self) -> None:
        with self._children_lock:
            self._dismiss_home_locked()
            self._launch_child(
                ["--screen-process", "--desktop"],
                role=ChildRole.SCREEN,
            )

    def _launch_home(self) -> None:
        with self._children_lock:
            if self._stop_event.is_set() or self._foreground_dialog_count > 0:
                return
            if (
                self._home_process is not None
                and self._home_process.poll() is None
            ):
                return
            self._launch_child(
                ["--home-process"],
                role=ChildRole.HOME,
            )

    def _launch_child(
        self,
        arguments: list[str],
        *,
        role: ChildRole,
    ) -> subprocess.Popen[bytes]:
        process = self.process_spawner(arguments)
        with self._children_lock:
            self._children.add(process)
            if role is ChildRole.CAMERA:
                self._camera_process = process
            elif role is ChildRole.HOME:
                self._home_process = process
        threading.Thread(
            target=self._monitor_child,
            args=(process, role),
            name="scanner-child-monitor",
            daemon=True,
        ).start()
        return process

    def _monitor_child(
        self,
        process: subprocess.Popen[bytes],
        role: ChildRole,
    ) -> None:
        return_code = process.wait()
        with self._children_lock:
            self._children.discard(process)
            if process is self._camera_process:
                self._camera_process = None
            if process is self._home_process:
                self._home_process = None
        if return_code == APPLICATION_EXIT_REQUESTED:
            self._stop()
            return
        if self._stop_event.is_set():
            return
        if role is ChildRole.HOME:
            self._handle_home_action(return_code)
        elif role in {ChildRole.CAMERA, ChildRole.SCREEN}:
            self._launch_home()

    def _handle_home_action(self, return_code: int) -> None:
        if return_code == CONTROL_SCAN_CAMERA:
            self._launch_camera()
            return
        if return_code == CONTROL_SCAN_SCREEN:
            self._launch_screen()
            return
        if return_code == CONTROL_PAIR_PHONE:
            self._start_pairing()
            return
        if return_code == CONTROL_EXIT_REQUESTED:
            self._request_full_exit()

    def _request_full_exit(self) -> None:
        """Serialize full-exit requests and keep their question accessible."""

        if not self._exit_prompt_lock.acquire(blocking=False):
            return
        approved = False
        try:
            self._prepare_for_foreground_dialog()
            approved = confirm_application_exit()
            if approved:
                self._stop()
        finally:
            self._finish_foreground_dialog(approved)
            self._exit_prompt_lock.release()

    def _dismiss_home(self) -> subprocess.Popen[bytes] | None:
        with self._children_lock:
            return self._dismiss_home_locked()

    def _dismiss_home_locked(self) -> subprocess.Popen[bytes] | None:
        process = self._home_process
        if process is None:
            return None
        self._home_process = None
        if process.poll() is None:
            process.terminate()
        return process

    @staticmethod
    def _wait_for_child_exit(
        process: subprocess.Popen[bytes] | None,
    ) -> None:
        if process is None or process.poll() is not None:
            return
        try:
            process.wait(timeout=CHILD_EXIT_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            try:
                process.wait(timeout=CHILD_EXIT_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                pass

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
                self._launch_home()

    def _stop(self) -> None:
        if self._stop_event.is_set():
            return
        self._stop_event.set()
        self._pairing_cancel_event.set()
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


def _pairing_error_message(error: Exception) -> str:
    if error.__class__.__module__.startswith(("httpx", "httpcore")):
        return (
            "The Phone-to-PC relay could not be reached.\n\n"
            "Check your internet connection and try again. If you explicitly "
            "configured a local or self-hosted relay, verify "
            "WQRS_RELAY_ORIGIN."
        )
    code = getattr(error, "code", None)
    if code == "unauthorized":
        return (
            "The saved relay registration is no longer valid. Try pairing "
            "again after restarting the relay."
        )
    if error.__class__.__name__ == "SecureStorageError":
        return (
            "Windows could not read or save the protected Phone-to-PC "
            "credentials. No unprotected fallback was used."
        )
    return (
        "Phone-to-PC pairing stopped safely.\n\n"
        f"Technical reason: {error.__class__.__name__}"
    )
