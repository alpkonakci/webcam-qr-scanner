from __future__ import annotations

import asyncio
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bridge.pairing import (
    submit_phone_pairing_request,
    wait_for_pc_result,
)
from bridge.pairing_controller import (
    LOCAL_DEVELOPMENT_RELAY_ORIGIN,
    PUBLIC_RELAY_ORIGIN,
    PairingController,
    PairingControllerStatus,
    configured_relay_origin,
)
from bridge.protocol import create_phone_pairing_attempt
from bridge.secure_storage import PairingStore
from pairing_ui import PairingWindowOutcome
from tests.test_local_relay import LiveRelay


class XorTestProtector:
    def protect(self, plaintext: bytes) -> bytes:
        return bytes(value ^ 0x5A for value in plaintext)

    def unprotect(self, ciphertext: bytes) -> bytes:
        return bytes(value ^ 0x5A for value in ciphertext)


class PairingConfigurationTests(unittest.TestCase):
    def test_public_beta_relay_is_the_default(self) -> None:
        self.assertEqual(configured_relay_origin({}), PUBLIC_RELAY_ORIGIN)

    def test_loopback_relay_remains_an_explicit_development_option(self) -> None:
        self.assertEqual(
            configured_relay_origin(
                {"WQRS_RELAY_ORIGIN": LOCAL_DEVELOPMENT_RELAY_ORIGIN}
            ),
            LOCAL_DEVELOPMENT_RELAY_ORIGIN,
        )

    def test_non_loopback_http_relay_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            configured_relay_origin(
                {"WQRS_RELAY_ORIGIN": "http://relay.example"}
            )


class PairingControllerTests(unittest.IsolatedAsyncioTestCase):
    async def test_phone_open_event_closes_qr_before_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = PairingStore(
                Path(directory) / "phone-to-pc.dat",
                protector=XorTestProtector(),
            )
            window_closed = threading.Event()

            async def fake_wait(*_, on_phone_opened, **__):
                on_phone_opened()
                return SimpleNamespace(phone_label="Lifecycle phone")

            def fake_window(*_, phone_opened, **__):
                if not phone_opened.wait(timeout=1):
                    raise TimeoutError("phone-open event did not reach the QR window")
                return PairingWindowOutcome.PHONE_OPENED

            async with LiveRelay() as live:
                controller = PairingController(
                    relay_origin=live.origin,
                    store=store,
                    pc_label="Test PC",
                    window_closed_event=window_closed,
                )
                with (
                    patch(
                        "bridge.pairing_controller.wait_for_phone_request",
                        side_effect=fake_wait,
                    ),
                    patch(
                        "bridge.pairing_controller.show_pairing_qr_window",
                        side_effect=fake_window,
                    ),
                    patch(
                        "bridge.pairing_controller.confirm_phone_pairing",
                        return_value=False,
                    ),
                    patch(
                        "bridge.pairing_controller.complete_pc_pairing",
                        new=AsyncMock(
                            return_value=SimpleNamespace(
                                approved=False,
                                phone_label="Lifecycle phone",
                            )
                        ),
                    ),
                ):
                    result = await asyncio.to_thread(controller.run)

            self.assertTrue(window_closed.is_set())
            self.assertEqual(result.status, PairingControllerStatus.REJECTED)

    async def test_closing_qr_immediately_revokes_relay_session(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = PairingStore(
                Path(directory) / "phone-to-pc.dat",
                protector=XorTestProtector(),
            )
            async with LiveRelay() as live:
                controller = PairingController(
                    relay_origin=live.origin,
                    store=store,
                    pc_label="Test PC",
                )
                with patch(
                    "bridge.pairing_controller.show_pairing_qr_window",
                    return_value=PairingWindowOutcome.CANCELLED,
                ):
                    result = await asyncio.to_thread(controller.run)

                self.assertEqual(
                    result.status,
                    PairingControllerStatus.CANCELLED,
                )
                self.assertEqual(
                    live.application.state.relay.safe_snapshot()[
                        "pairing_count"
                    ],
                    0,
                )

    async def test_approval_is_persisted_before_phone_receives_result(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = PairingStore(
                Path(directory) / "phone-to-pc.dat",
                protector=XorTestProtector(),
            )
            async with LiveRelay() as live:
                phone_holder = {}

                def fake_window(
                    pairing_uri,
                    *,
                    request_received,
                    **_,
                ):
                    phone = create_phone_pairing_attempt(
                        pairing_uri,
                        phone_label="Controller test phone",
                    )
                    phone_holder["attempt"] = phone
                    asyncio.run(submit_phone_pairing_request(phone))
                    if not request_received.wait(timeout=5):
                        raise TimeoutError("PC did not receive pairing request")
                    return PairingWindowOutcome.REQUEST_RECEIVED

                controller = PairingController(
                    relay_origin=live.origin,
                    store=store,
                    pc_label="Test PC",
                )
                with (
                    patch(
                        "bridge.pairing_controller.show_pairing_qr_window",
                        side_effect=fake_window,
                    ),
                    patch(
                        "bridge.pairing_controller.confirm_phone_pairing",
                        return_value=True,
                    ),
                ):
                    result = await asyncio.to_thread(controller.run)

                phone = phone_holder["attempt"]
                sender = await wait_for_pc_result(
                    phone,
                    timeout_seconds=5,
                )
                snapshot = store.load()

                self.assertEqual(
                    result.status,
                    PairingControllerStatus.APPROVED,
                )
                self.assertIsNotNone(sender)
                self.assertEqual(len(snapshot.devices), 1)
                self.assertEqual(len(snapshot.pairs), 1)
                assert sender is not None
                self.assertEqual(snapshot.pairs[0].pair_id, sender.pair_id)
                self.assertEqual(snapshot.pairs[0].root_key, sender.root_key)

    async def test_rejection_stores_no_pair_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = PairingStore(
                Path(directory) / "phone-to-pc.dat",
                protector=XorTestProtector(),
            )
            async with LiveRelay() as live:
                phone_holder = {}

                def fake_window(
                    pairing_uri,
                    *,
                    request_received,
                    **_,
                ):
                    phone = create_phone_pairing_attempt(
                        pairing_uri,
                        phone_label="Rejected controller phone",
                    )
                    phone_holder["attempt"] = phone
                    asyncio.run(submit_phone_pairing_request(phone))
                    if not request_received.wait(timeout=5):
                        raise TimeoutError("PC did not receive pairing request")
                    return PairingWindowOutcome.REQUEST_RECEIVED

                controller = PairingController(
                    relay_origin=live.origin,
                    store=store,
                    pc_label="Test PC",
                )
                with (
                    patch(
                        "bridge.pairing_controller.show_pairing_qr_window",
                        side_effect=fake_window,
                    ),
                    patch(
                        "bridge.pairing_controller.confirm_phone_pairing",
                        return_value=False,
                    ),
                ):
                    result = await asyncio.to_thread(controller.run)

                sender = await wait_for_pc_result(
                    phone_holder["attempt"],
                    timeout_seconds=5,
                )

                self.assertEqual(
                    result.status,
                    PairingControllerStatus.REJECTED,
                )
                self.assertIsNone(sender)
                self.assertEqual(store.load().pairs, ())


if __name__ == "__main__":
    unittest.main()
