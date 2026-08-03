"""Persistent background controller for all securely paired phones."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from dataclasses import dataclass

from bridge.protocol import ReceivedUrl, ReceiverCredentials
from bridge.receiver import PcReceiver
from bridge.realtime import RealtimeSession
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
    realtime_session: RealtimeSession | None = None


class ReceiverService:
    """Reconnect paired relay devices without keeping the camera open."""

    def __init__(
        self,
        *,
        store: PairingStore | None = None,
        receiver_factory: Callable[..., PcReceiver] = PcReceiver,
        confirmer: Callable[..., bool] = confirm_phone_url,
        url_opener: Callable[[str], bool] = open_web_url,
        before_prompt: Callable[[], None] | None = None,
        after_prompt: Callable[[bool], None] | None = None,
    ) -> None:
        self.store = store or PairingStore()
        self.receiver_factory = receiver_factory
        self.confirmer = confirmer
        self.url_opener = url_opener
        self.before_prompt = before_prompt
        self.after_prompt = after_prompt
        self._stop_event = threading.Event()
        self._refresh_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._labels_lock = threading.RLock()
        self._phone_labels: dict[str, str] = {}
        self._prompt_lock = threading.Lock()

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
        current_realtime_session = group.realtime_session

        def persist_realtime_session(session: RealtimeSession) -> None:
            nonlocal current_realtime_session
            self.store.update_realtime_session(group.relay_origin, session)
            current_realtime_session = session

        while not self._stop_event.is_set() and not self._refresh_event.is_set():
            receiver = self.receiver_factory(
                relay_origin=group.relay_origin,
                credentials=group.credentials,
                on_url=self._handle_url,
                realtime_session=current_realtime_session,
                on_realtime_session=persist_realtime_session,
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
        # Multiple relay groups may deliver at nearly the same time. Present
        # one security decision at a time and dismiss transient scanner UI
        # before asking it so the question cannot be hidden behind that UI.
        with self._prompt_lock:
            opened = False
            try:
                if self.before_prompt is not None:
                    self.before_prompt()
                if self.confirmer(
                    received.url,
                    received.hostname_ascii,
                    phone_label=phone_label,
                ):
                    opened = self.url_opener(received.url)
            finally:
                if self.after_prompt is not None:
                    self.after_prompt(opened)


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
                realtime_session=(
                    RealtimeSession(
                        access_token=device.realtime_access_token,
                        refresh_token=device.realtime_refresh_token,
                        expires_at=device.realtime_expires_at,
                        user_id=device.realtime_user_id,
                    )
                    if device.realtime_access_token is not None
                    and device.realtime_refresh_token is not None
                    and device.realtime_expires_at is not None
                    and device.realtime_user_id is not None
                    else None
                ),
            )
        )
    return tuple(groups)
