from __future__ import annotations

import unittest
from unittest.mock import Mock

from bridge.protocol import ReceivedUrl, random_b64url
from bridge.receiver_service import ReceiverService, receiver_groups
from bridge.secure_storage import (
    PairingStoreSnapshot,
    RelayDevice,
    StoredPair,
)


class ReceiverServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.origin = "https://relay.example"
        self.device = RelayDevice(
            relay_origin=self.origin,
            device_id=random_b64url(16),
            receiver_token=random_b64url(32),
        )
        self.first_pair = StoredPair(
            relay_origin=self.origin,
            device_id=self.device.device_id,
            pair_id=random_b64url(16),
            root_key=b"a" * 32,
            phone_label="First phone",
        )
        self.second_pair = StoredPair(
            relay_origin=self.origin,
            device_id=self.device.device_id,
            pair_id=random_b64url(16),
            root_key=b"b" * 32,
            phone_label="Second phone",
        )

    def test_pairs_for_one_device_share_one_receiver_connection(self) -> None:
        groups = receiver_groups(
            PairingStoreSnapshot(
                devices=(self.device,),
                pairs=(self.first_pair, self.second_pair),
            )
        )

        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0].credentials), 2)
        self.assertEqual(
            groups[0].phone_labels[self.second_pair.pair_id],
            "Second phone",
        )
        self.assertTrue(
            all(
                credential.receiver_token == self.device.receiver_token
                for credential in groups[0].credentials
            )
        )

    def test_received_url_uses_authenticated_phone_label_and_confirmation(
        self,
    ) -> None:
        confirmer = Mock(return_value=True)
        opener = Mock(return_value=True)
        service = ReceiverService(confirmer=confirmer, url_opener=opener)
        service._phone_labels = {self.first_pair.pair_id: "First phone"}
        received = ReceivedUrl(
            pair_id=self.first_pair.pair_id,
            message_id=random_b64url(16),
            url="https://example.com/private",
            hostname_ascii="example.com",
            is_secure=True,
        )

        service._handle_url(received)

        confirmer.assert_called_once_with(
            received.url,
            "example.com",
            phone_label="First phone",
        )
        opener.assert_called_once_with(received.url)

    def test_rejected_confirmation_never_opens_browser(self) -> None:
        opener = Mock()
        service = ReceiverService(
            confirmer=Mock(return_value=False),
            url_opener=opener,
        )
        service._handle_url(
            ReceivedUrl(
                pair_id=self.first_pair.pair_id,
                message_id=random_b64url(16),
                url="http://example.com/",
                hostname_ascii="example.com",
                is_secure=False,
            )
        )

        opener.assert_not_called()

    def test_transient_windows_are_dismissed_before_url_confirmation(
        self,
    ) -> None:
        order: list[str] = []
        service = ReceiverService(
            before_prompt=lambda: order.append("dismiss"),
            after_prompt=lambda opened: order.append(f"restore:{opened}"),
            confirmer=lambda *_, **__: order.append("confirm") or False,
        )

        service._handle_url(
            ReceivedUrl(
                pair_id=self.first_pair.pair_id,
                message_id=random_b64url(16),
                url="https://example.com/",
                hostname_ascii="example.com",
                is_secure=True,
            )
        )

        self.assertEqual(order, ["dismiss", "confirm", "restore:False"])

    def test_prompt_cleanup_knows_when_browser_was_opened(self) -> None:
        outcomes: list[bool] = []
        service = ReceiverService(
            confirmer=Mock(return_value=True),
            url_opener=Mock(return_value=True),
            after_prompt=outcomes.append,
        )

        service._handle_url(
            ReceivedUrl(
                pair_id=self.first_pair.pair_id,
                message_id=random_b64url(16),
                url="https://example.com/",
                hostname_ascii="example.com",
                is_secure=True,
            )
        )

        self.assertEqual(outcomes, [True])


if __name__ == "__main__":
    unittest.main()
