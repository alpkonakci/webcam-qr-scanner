import asyncio
import struct
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import urlsplit

import httpx

from bridge.protocol import b64url_decode, random_b64url
from bridge.scanner_return import open_phone_scanner, scanner_return_url
from bridge.pairing import open_pc_pairing
from tests.test_local_relay import LiveRelay


class ScannerReturnTests(unittest.IsolatedAsyncioTestCase):
    async def exercise_return(self, *, phone_opens):
        async with LiveRelay() as live:
            async with httpx.AsyncClient(base_url=live.origin) as client:
                device = (await client.post("/v1/devices")).json()
            store = Mock()
            store.load.return_value.device_for.return_value = SimpleNamespace(**device)
            loop = asyncio.get_running_loop()
            displayed = asyncio.Event()
            launch = {}

            def window(origin, *, launch_url, phone_opened, expires_at):
                launch["url"] = launch_url
                loop.call_soon_threadsafe(displayed.set)
                if phone_opens and not phone_opened.wait(3):
                    raise AssertionError("QR window did not receive phone-open signal")

            task = asyncio.create_task(open_phone_scanner(live.origin, window, store=store))
            await asyncio.wait_for(displayed.wait(), 2)
            payload = b64url_decode(urlsplit(launch["url"]).fragment.removeprefix("open="))
            self.assertEqual(len(payload), 53)
            self.assertEqual(payload[0], 1)
            from bridge.protocol import b64url_encode
            pairing_id = b64url_encode(payload[1:17])
            token = b64url_encode(payload[17:49])
            async with httpx.AsyncClient(base_url=live.origin) as client:
                if phone_opens:
                    response = await client.post(
                        f"/v1/pairings/{pairing_id}/opened",
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    self.assertEqual(response.status_code, 202)
                await asyncio.wait_for(task, 3)
                response = await client.post(
                    f"/v1/pairings/{pairing_id}/opened",
                    headers={"Authorization": f"Bearer {token}"},
                )
                self.assertNotEqual(response.status_code, 202)
            store.add_pair.assert_not_called()
            store.replace_device.assert_not_called()
            self.assertNotIn(device["receiver_token"], launch["url"])

    async def test_real_phone_open_closes_window_and_invalidates_temporary_token(self):
        await self.exercise_return(phone_opens=True)

    async def test_back_invalidates_temporary_token_without_changing_pair(self):
        await self.exercise_return(phone_opens=False)

    async def test_return_qr_omits_pairing_secret_and_device_credentials(self):
        async with LiveRelay() as live:
            async with httpx.AsyncClient(base_url=live.origin) as client:
                device = (await client.post("/v1/devices")).json()
            session = await open_pc_pairing(relay_origin=live.origin, **{
                key: device[key] for key in ("device_id", "receiver_token")
            })
            url = scanner_return_url(session)
            raw = b64url_decode(urlsplit(url).fragment.removeprefix("open="))
            self.assertEqual(struct.unpack("!I", raw[49:])[0], session.qr.expires_at)
            self.assertNotIn(session.qr.pairing_secret, raw)
            self.assertNotIn(session.receiver_token, url)

    async def test_missing_device_does_not_open_qr_or_register_a_device(self):
        store = Mock()
        store.load.return_value.device_for.return_value = None
        window = Mock()
        with self.assertRaises(ValueError):
            await open_phone_scanner("https://qrwebcam.vercel.app", window, store=store)
        window.assert_not_called()
