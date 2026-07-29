"""Lightweight entry point for one executable with independent app modes."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from app_settings import SettingsStore
from bridge_signals import (
    clear_control_requests,
    request_bridge_exit,
    request_camera_closed,
    request_open_camera,
)
from exit_codes import APPLICATION_EXIT_REQUESTED, CAMERA_CLOSED
from single_instance import BridgeInstanceGuard


def parse_launcher_args(
    argv: Sequence[str] | None = None,
) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--bridge", action="store_true")
    parser.add_argument("--open-camera", action="store_true")
    parser.add_argument("--camera-process", action="store_true")
    parser.add_argument("--screen-process", action="store_true")
    return parser.parse_known_args(argv)


def run_bridge(
    *,
    open_camera: bool = False,
    camera_arguments: Sequence[str] = (),
) -> int:
    """Start the sole tray controller or ask the existing one for a camera."""

    with BridgeInstanceGuard() as guard:
        if guard.already_running:
            if open_camera:
                request_open_camera(camera_arguments)
            return 0

        clear_control_requests()
        settings_store = SettingsStore()
        from tray_app import TrayApplication

        TrayApplication(
            open_camera_on_start=open_camera,
            camera_arguments=camera_arguments,
            settings_store=settings_store,
        ).run()
    return 0


def run_camera(
    arguments: Sequence[str],
    *,
    signal_controller: bool = True,
) -> int:
    """Load OpenCV only inside the camera child process."""

    from app import main as camera_main

    return_code = camera_main(arguments)
    if not signal_controller:
        return return_code
    if return_code == APPLICATION_EXIT_REQUESTED:
        request_bridge_exit()
    elif return_code == CAMERA_CLOSED:
        request_camera_closed()
    return return_code


def run_screen(arguments: Sequence[str]) -> int:
    """Load desktop capture dependencies only for a one-shot screen scan."""

    from app import main as camera_main

    return camera_main(["--screen", *arguments])


def main(argv: Sequence[str] | None = None) -> int:
    args, remaining = parse_launcher_args(argv)

    if args.camera_process:
        return run_camera(remaining)
    if args.screen_process:
        return run_screen(remaining)
    if args.bridge:
        return run_bridge(
            open_camera=args.open_camera,
            camera_arguments=remaining,
        )
    if "--screen" in remaining:
        forwarded = [value for value in remaining if value != "--screen"]
        return run_screen(forwarded)
    if "--self-test" in remaining:
        return run_camera(remaining, signal_controller=False)

    return run_bridge(open_camera=True, camera_arguments=remaining)


if __name__ == "__main__":
    raise SystemExit(main())
