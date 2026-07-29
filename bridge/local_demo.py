"""Run an encrypted fake-phone -> local-relay -> PC demonstration."""

from __future__ import annotations

import argparse
import asyncio
import socket

import uvicorn

from bridge.fake_phone import FakePhone
from bridge.protocol import ReceivedUrl
from bridge.provision import provision_local_pairing
from bridge.receiver import PcReceiver
from links import open_web_url
from native_dialogs import confirm_phone_url
from relay.app import create_app


async def run_demo(url: str, *, show_dialog: bool = True) -> None:
    port = _available_loopback_port()
    relay_origin = f"http://127.0.0.1:{port}"
    application = create_app()
    server = uvicorn.Server(
        uvicorn.Config(
            application,
            host="127.0.0.1",
            port=port,
            access_log=False,
            log_level="warning",
            lifespan="off",
        )
    )
    server_task = asyncio.create_task(server.serve())
    try:
        await _wait_until_started(server)
        pairing = await provision_local_pairing(relay_origin)

        def handle_url(received: ReceivedUrl) -> None:
            if not show_dialog:
                return
            if confirm_phone_url(
                received.url,
                received.hostname_ascii,
                phone_label="Local fake phone",
            ):
                open_web_url(received.url)

        receiver = PcReceiver(
            relay_origin=relay_origin,
            credentials=pairing.receiver,
            on_url=handle_url,
        )
        receiver_task = asyncio.create_task(receiver.run(stop_after=1))
        await asyncio.wait_for(receiver.connected.wait(), timeout=5)

        result = await FakePhone(
            relay_origin=relay_origin,
            credentials=pairing.sender,
        ).send_url(url)
        await asyncio.wait_for(receiver_task, timeout=5)
        snapshot = application.state.relay.safe_snapshot()
        if url in repr(snapshot):
            raise RuntimeError("relay diagnostics unexpectedly contain the URL")
        print(
            "Encrypted delivery verified: "
            f"{result.status}; relay retained no URL."
        )
    finally:
        server.should_exit = True
        await asyncio.wait_for(server_task, timeout=5)


async def _wait_until_started(
    server: uvicorn.Server,
    *,
    timeout_seconds: float = 5,
) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    while not server.started:
        if server_task_failed := getattr(server, "should_exit", False):
            raise RuntimeError(
                f"local relay stopped before startup: {server_task_failed}"
            )
        if loop.time() >= deadline:
            raise TimeoutError("local relay did not start in time")
        await asyncio.sleep(0.02)


def _available_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        default="https://example.com/phone-to-pc-demo",
        help="HTTP(S) URL to encrypt and deliver",
    )
    parser.add_argument(
        "--no-dialog",
        action="store_true",
        help="verify delivery without opening the PC confirmation dialog",
    )
    args = parser.parse_args()
    asyncio.run(run_demo(args.url, show_dialog=not args.no_dialog))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

