"""Fail the release gate if receiver recreation accepts an already accepted ID.

Run from the repository root with:
    python -m protocol.check_receiver_restart_replay

Uses synthetic credentials, a temporary DPAPI ledger, and no network/camera/UI.
Recreating PcReceiver follows ReceiverService's reconstruction path; not a real
Windows reboot test. This is deliberately separate from ordinary unit tests:
an exit code of 1 is an unresolved release gate, not an expected-success test.
"""

from bridge.protocol import (
    ReceiverCredentials,
    ReplayDetected,
    SenderCredentials,
    build_url_envelope,
    random_b64url,
)
from bridge.receiver import PcReceiver
from bridge.receiver_service import ReceiverGroup, ReceiverService
from bridge.secure_storage import PairingStore
from pathlib import Path
from tempfile import TemporaryDirectory


def check(directory: Path) -> int:
    credentials = ReceiverCredentials(
        device_id=random_b64url(16),
        receiver_token=random_b64url(32),
        pair_id=random_b64url(16),
        root_key=b"r" * 32,
    )
    envelope = build_url_envelope(
        SenderCredentials(
            pair_id=credentials.pair_id,
            sender_token=random_b64url(32),
            root_key=credentials.root_key,
        ),
        "https://example.com/release-replay-probe",
    )
    event = {
        "event": "url_message",
        "delivery_id": random_b64url(16),
        "envelope": envelope,
    }
    group = ReceiverGroup(
        relay_origin="https://relay.example", device_id=credentials.device_id,
        credentials=(credentials,), phone_labels={credentials.pair_id: "Synthetic phone"},
    )

    def receiver():
        # Recreate the service/store as well as the receiver; no shared objects.
        service = ReceiverService(store=PairingStore(directory / "synthetic-pair.dat"))
        return PcReceiver(
            relay_origin="https://relay.example",
            credentials=credentials,
            on_url=lambda _: None,
            replay_guards=service.replay_guards_for(group),
        )

    first = receiver()
    first._decrypt_event(event)
    try:
        first._decrypt_event(event)
    except ReplayDetected:
        print("PASS: one receiver rejects a repeated authenticated message.")
    else:
        print("FAIL: same-receiver replay protection is missing.")
        return 1
    try:
        receiver()._decrypt_event(event)
    except ReplayDetected:
        print("PASS: reconstructed receiver preserves replay protection.")
        return 0
    print("FAIL: reconstructed receiver accepts the same authenticated message.")
    print("Persistent replay protection is required before closing this release gate.")
    return 1


def main() -> int:
    with TemporaryDirectory(prefix="wqrs-replay-gate-") as directory:
        return check(Path(directory))


if __name__ == "__main__":
    raise SystemExit(main())
