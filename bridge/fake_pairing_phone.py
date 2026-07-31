"""Development fake phone that reads the visible PC pairing QR from the screen."""

from __future__ import annotations

import argparse
import asyncio

from bridge.pairing import (
    submit_phone_pairing_request,
    wait_for_pc_result,
)
from bridge.protocol import create_phone_pairing_attempt
from qr_reader import QRReader
from screen_capture import capture_virtual_screen


def find_visible_pairing_uri() -> str:
    """Capture once and require exactly one visible WQRS pairing QR."""

    frame = capture_virtual_screen()
    values = {
        result.data
        for result in QRReader().scan_all(frame)
        if result.data.startswith("wqrs://pair?")
    }
    if not values:
        raise RuntimeError(
            "No pairing QR was found. Keep the Pair Phone window visible."
        )
    if len(values) != 1:
        raise RuntimeError(
            "Multiple pairing QR codes are visible. Keep only one on screen."
        )
    return next(iter(values))


async def run(phone_label: str) -> bool:
    pairing_uri = find_visible_pairing_uri()
    attempt = create_phone_pairing_attempt(
        pairing_uri,
        phone_label=phone_label,
    )
    await submit_phone_pairing_request(attempt)
    sender = await wait_for_pc_result(attempt, timeout_seconds=120)
    return sender is not None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--phone-label",
        default="Local fake phone",
        help="label shown in the PC approval dialog",
    )
    args = parser.parse_args()
    try:
        approved = asyncio.run(run(args.phone_label))
    except Exception as error:
        print(f"Pairing test failed safely: {error}")
        return 1
    if not approved:
        print("Pairing request was rejected. No credentials were stored.")
        return 2
    print("Pairing approved and verified. No secret was printed or copied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
