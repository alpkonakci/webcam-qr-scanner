"""Lightweight entry point for one executable with independent app modes."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from bridge_signals import (
    clear_control_requests,
    request_bridge_exit,
    request_camera_closed,
    request_open_camera,
    request_open_home,
)
from exit_codes import (
    APPLICATION_EXIT_REQUESTED,
    CAMERA_CLOSED,
    CONTROL_EXIT_REQUESTED,
    CONTROL_BACK_HOME,
    CONTROL_MANAGE_PHONES,
    CONTROL_PAIR_PHONE,
    CONTROL_REMOVE_PHONE,
    CONTROL_SCAN_CAMERA,
    CONTROL_SCAN_SCREEN,
)
from single_instance import BridgeInstanceGuard


def parse_launcher_args(
    argv: Sequence[str] | None = None,
) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--bridge", action="store_true")
    parser.add_argument("--open-camera", action="store_true")
    parser.add_argument("--camera-process", action="store_true")
    parser.add_argument("--screen-process", action="store_true")
    parser.add_argument("--home-process", action="store_true")
    parser.add_argument("--paired-phones-process", action="store_true")
    parser.add_argument("--paired-phone-count", type=int, default=0)
    return parser.parse_known_args(argv)


def run_bridge(
    *,
    open_camera: bool = False,
    open_home: bool = False,
    camera_arguments: Sequence[str] = (),
) -> int:
    """Start the sole controller or route a window request to the existing one."""

    with BridgeInstanceGuard() as guard:
        if guard.already_running:
            if open_camera:
                request_open_camera(camera_arguments)
            elif open_home:
                request_open_home()
            return 0

        clear_control_requests()
        from paired_phone_ipc import clear_paired_phone_requests

        clear_paired_phone_requests()
        from tray_app import TrayApplication

        TrayApplication(
            open_camera_on_start=open_camera,
            open_home_on_start=open_home,
            camera_arguments=camera_arguments,
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


def run_home(*, pair_count: int = 0) -> int:
    """Show the lightweight control center in its own GUI process."""

    from home_ui import HomeAction, show_home_window
    from native_dialogs import confirm_application_exit

    action = show_home_window(
        confirm_exit=confirm_application_exit,
        pair_count=max(0, pair_count),
    )
    return {
        HomeAction.BACKGROUND: 0,
        HomeAction.SCAN_CAMERA: CONTROL_SCAN_CAMERA,
        HomeAction.SCAN_SCREEN: CONTROL_SCAN_SCREEN,
        HomeAction.PAIR_PHONE: CONTROL_PAIR_PHONE,
        HomeAction.MANAGE_PHONES: CONTROL_MANAGE_PHONES,
        HomeAction.EXIT: APPLICATION_EXIT_REQUESTED,
    }[action]


def run_paired_phones() -> int:
    """Show the paired-phone view from a one-use credential-free snapshot."""

    from paired_phone_ipc import (
        consume_paired_phones_snapshot,
        request_phone_removal,
    )
    from paired_phones_ui import PairedPhonesAction, show_paired_phones_window

    decision = show_paired_phones_window(consume_paired_phones_snapshot())
    if decision.action is PairedPhonesAction.REMOVE:
        if decision.phone is None:
            return CONTROL_BACK_HOME
        request_phone_removal(decision.phone)
        return CONTROL_REMOVE_PHONE
    if decision.action is PairedPhonesAction.PAIR_ANOTHER:
        return CONTROL_PAIR_PHONE
    return CONTROL_BACK_HOME


def main(argv: Sequence[str] | None = None) -> int:
    args, remaining = parse_launcher_args(argv)

    if args.camera_process:
        return run_camera(remaining)
    if args.screen_process:
        return run_screen(remaining)
    if args.paired_phones_process:
        return run_paired_phones()
    if args.home_process:
        return run_home(pair_count=args.paired_phone_count)
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

    open_camera = args.open_camera or bool(remaining)
    return run_bridge(
        open_camera=open_camera,
        open_home=not open_camera,
        camera_arguments=remaining,
    )


if __name__ == "__main__":
    raise SystemExit(main())
