"""Short-lived scanner-open acknowledgements; never create or replace a pair."""

from __future__ import annotations

import asyncio
import contextlib
import struct
import threading
from collections.abc import Callable

import httpx

from bridge.pairing import (
    PairingTransportError, PairingWaitCancelled, PairingWaitTimeout,
    cancel_pc_pairing, open_pc_pairing, wait_for_phone_request,
)
from bridge.protocol import PcPairingSession, b64url_decode, b64url_encode
from bridge.secure_storage import PairingStore


def scanner_return_url(session: PcPairingSession) -> str:
    # No receiver/sender token, root key, public key or pairing secret is shared.
    # This temporary relay token can only signal that the homepage was opened.
    qr = session.qr
    payload = (b"\x01" + b64url_decode(qr.pairing_id, expected_length=16)
               + b64url_decode(qr.pairing_token, expected_length=32)
               + struct.pack("!I", qr.expires_at))
    return f"{qr.relay_origin}/#open={b64url_encode(payload)}"


async def open_phone_scanner(
    origin: str,
    show_window: Callable[..., None],
    *,
    store: PairingStore | None = None,
) -> None:
    device = (store or PairingStore()).load().device_for(origin)
    if device is None:
        raise ValueError("No saved PC connection is available")
    session = await open_pc_pairing(
        relay_origin=origin, device_id=device.device_id,
        receiver_token=device.receiver_token,
    )
    phone_opened = threading.Event()
    stop = asyncio.Event()

    async def watch_opened() -> None:
        while not stop.is_set():
            try:
                # Existing authenticated polling is reused only for its opened
                # signal. No request is approved and no pairing store is written.
                await wait_for_phone_request(
                    session, cancellation_event=stop,
                    on_phone_opened=phone_opened.set,
                )
                return
            except httpx.HTTPError:
                # A brief connection interruption must not abandon the signal.
                await asyncio.sleep(0.5)
            except PairingTransportError as error:
                if error.status_code == 429 or error.status_code >= 500:
                    await asyncio.sleep(0.5)
                    continue
                return
            except (PairingWaitCancelled, PairingWaitTimeout, ValueError):
                return

    task = asyncio.create_task(watch_opened())
    try:
        await asyncio.to_thread(
            show_window, origin, launch_url=scanner_return_url(session),
            phone_opened=phone_opened, expires_at=session.qr.expires_at,
        )
    finally:
        stop.set()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        with contextlib.suppress(httpx.HTTPError, PairingTransportError, ValueError):
            await cancel_pc_pairing(session)
