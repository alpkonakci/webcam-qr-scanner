"""Development-only end-to-end provisioning against the local relay."""

from __future__ import annotations

import httpx

from bridge.pairing import (
    complete_pc_pairing,
    open_pc_pairing,
    submit_phone_pairing_request,
    wait_for_pc_result,
    wait_for_phone_request,
)
from bridge.protocol import (
    LocalPairing,
    create_phone_pairing_attempt,
    pairing_transcript,
)


async def provision_local_pairing(relay_origin: str) -> LocalPairing:
    """Run the real HTTP pairing flow with an explicit development approval."""

    async with httpx.AsyncClient(base_url=relay_origin, timeout=5) as client:
        device_response = await client.post("/v1/devices")
        device_response.raise_for_status()
        device = device_response.json()
    session = await open_pc_pairing(
        relay_origin=relay_origin,
        device_id=device["device_id"],
        receiver_token=device["receiver_token"],
    )
    phone = create_phone_pairing_attempt(
        session.pairing_uri,
        phone_label="Local fake phone",
    )
    await submit_phone_pairing_request(phone)
    request = await wait_for_phone_request(session, timeout_seconds=5)
    decision = await complete_pc_pairing(
        session,
        request,
        approved=True,
        pc_label="Local Windows PC",
    )
    sender = await wait_for_pc_result(phone, timeout_seconds=5)
    if decision.receiver is None or sender is None:
        raise RuntimeError("development pairing was unexpectedly rejected")
    if (
        decision.receiver.pair_id != sender.pair_id
        or decision.receiver.root_key != sender.root_key
    ):
        raise RuntimeError("pairing produced inconsistent phone and PC keys")
    return LocalPairing(
        receiver=decision.receiver,
        sender=sender,
        transcript=pairing_transcript(session.qr, phone.phone_public_key),
    )
