"""Persistent background controller for all securely paired phones."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from dataclasses import dataclass

from bridge.protocol import ReceivedUrl, ReceiverCredentials
from bridge.receiver import PcReceiver
from bridge.secure_storage import (
    PairingStore,
    PairingStoreSnapshot,
    SecureStorageError,
)
from links import open_web_url
from native_dialogs import confirm_phone_url


RECONNECT_DELAYS_SECONDS = (1.0, 2.0, 5.0, 10.0)


@dataclass(frozen=True, slots=True)
class ReceiverGroup:
    relay_origin: str
    device_id: str
    credentials: tuple[ReceiverCredentials, ...]
    phone_labels: dict[str, str]


class ReceiverService:
    """Reconnect paired relay devices without keeping the camera open."""

    def __init__(
        self,
        *,
        store: PairingStore | None = None,
        receiver_factory: Callable[..., PcReceiver] = PcReceiver,
        confirmer: Callable[..., bool] = confirm_phone_url,
        url_opener: Callable[[str], bool] = open_web_url,
    ) -> None:
        self.store = store or PairingStore()
        self.receiver_factory = receiver_factory
        self.confirmer = confirmer
        self.url_opener = url_opener
        self._stop_event = threading.Event()
        self._refresh_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._labels_lock = threading.RLock()
        self._phone_labels: dict[str, str] = {}

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._refresh_event.set()
        self._thread = threading.Thread(
            target=self._thread_main,
            name="phone-to-pc-receiver",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._refresh_event.set()

    def request_refresh(self) -> None:
        self._refresh_event.set()

    def has_paired_phones(self) -> bool:
        try:
            return bool(self.store.load().pairs)
        except Exception:
            return False

    def _thread_main(self) -> None:
        asyncio.run(self._run())

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            self._refresh_event.clear()
            try:
                snapshot = await asyncio.to_thread(self.store.load)
            except SecureStorageError:
                await self._interruptible_delay(5.0)
                continue
            groups = receiver_groups(snapshot)
            with self._labels_lock:
                self._phone_labels = {
                    pair_id: label
                    for group in groups
                    for pair_id, label in group.phone_labels.items()
                }
            tasks = [
                asyncio.create_task(
                    self._run_group(group),
                    name=f"phone-to-pc-{group.device_id[:8]}",
                )
                for group in groups
            ]
            await self._wait_for_refresh_or_stop()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _run_group(self, group: ReceiverGroup) -> None:
        attempt = 0
        while not self._stop_event.is_set() and not self._refresh_event.is_set():
            receiver = self.receiver_factory(
                relay_origin=group.relay_origin,
                credentials=group.credentials,
                on_url=self._handle_url,
            )
            try:
                await receiver.run()
                attempt = 0
            except Exception:
                delay = RECONNECT_DELAYS_SECONDS[
                    min(attempt, len(RECONNECT_DELAYS_SECONDS) - 1)
                ]
                attempt += 1
                await self._interruptible_delay(delay)

    async def _wait_for_refresh_or_stop(self) -> None:
        while not self._stop_event.is_set() and not self._refresh_event.is_set():
            await asyncio.sleep(0.2)

    async def _interruptible_delay(self, delay: float) -> None:
        elapsed = 0.0
        while (
            elapsed < delay
            and not self._stop_event.is_set()
            and not self._refresh_event.is_set()
        ):
            step = min(0.2, delay - elapsed)
            await asyncio.sleep(step)
            elapsed += step

    def _handle_url(self, received: ReceivedUrl) -> None:
        with self._labels_lock:
            phone_label = self._phone_labels.get(
                received.pair_id,
                "Paired phone",
            )
        if self.confirmer(
            received.url,
            received.hostname_ascii,
            phone_label=phone_label,
        ):
            self.url_opener(received.url)


def receiver_groups(snapshot: PairingStoreSnapshot) -> tuple[ReceiverGroup, ...]:
    groups: list[ReceiverGroup] = []
    for device in snapshot.devices:
        pairs = tuple(
            pair
            for pair in snapshot.pairs
            if pair.relay_origin == device.relay_origin
            and pair.device_id == device.device_id
        )
        if not pairs:
            continue
        groups.append(
            ReceiverGroup(
                relay_origin=device.relay_origin,
                device_id=device.device_id,
                credentials=tuple(
                    ReceiverCredentials(
                        device_id=device.device_id,
                        receiver_token=device.receiver_token,
                        pair_id=pair.pair_id,
                        root_key=pair.root_key,
                        key_epoch=pair.key_epoch,
                    )
                    for pair in pairs
                ),
                phone_labels={
                    pair.pair_id: pair.phone_label for pair in pairs
                },
            )
        )
    return tuple(groups)
