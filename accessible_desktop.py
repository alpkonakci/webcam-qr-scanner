"""Accessible Windows control screens, keeping decisions in existing domains."""
from __future__ import annotations

from collections.abc import Callable, Sequence
import webbrowser

from accessible_controls import ControlWindow
from app_info import APP_VERSION, RELEASES_URL
from desktop_i18n import get_language, set_language, t
from native_dialogs import WindowCloseChoice
from paired_phone_ipc import PairedPhoneView
from windows_startup import is_startup_enabled, set_startup_enabled


def home_controls(*, pair_count: int, confirm_exit: Callable[[], bool] | None,
                  choose_close: Callable[[], WindowCloseChoice]) -> ControlWindow:
    from home_ui import HomeAction, action_cards
    from bridge.pairing_controller import configured_relay_origin
    from receiver_status import connection_confirmed

    window: ControlWindow
    def leave() -> None:
        choice = choose_close()
        if choice is WindowCloseChoice.BACKGROUND:
            window.finish(HomeAction.BACKGROUND)
        elif choice is WindowCloseChoice.EXIT:
            window.finish(HomeAction.EXIT)

    def exit_app() -> None:
        if confirm_exit is None or confirm_exit():
            window.finish(HomeAction.EXIT)

    window = ControlWindow("QR Scanner", (620, 585), on_close=leave,
                           on_escape=lambda: window.finish(HomeAction.BACKGROUND))
    window.label("title", "QR SCANNER", (28, 22, 330, 40), heading=True)
    window.label("intro", t("Choose what you want to do."), (28, 68, 560, 25))
    window.label("status", "", (28, 96, 560, 38))
    for index, card in enumerate(action_cards(pair_count)):
        y = 141 + index * 83
        window.button(card.action.value, t(card.title), (28, y, 564, 44),
                      lambda action=card.action: window.finish(action))
        window.label("help_" + card.action.value, t(card.description), (35, y + 46, 554, 34))
    window.button("settings", t("Settings and about"), (28, 486, 270, 42), lambda: window.finish(HomeAction.SETTINGS))
    window.button("exit", t("Exit"), (414, 486, 178, 42), exit_app)
    window.label("keyboard", t("Tab: move · Enter: select · ESC: background"), (28, 540, 560, 25))
    origin = configured_relay_origin()
    def update_status() -> None:
        if pair_count == 0:
            window.text("status", t("No saved phone pairing"))
            return
        connection_key = (
            "Receiver connection confirmed"
            if connection_confirmed(origin)
            else "Receiver connection not confirmed"
        )
        saved_pairings = t("{count} saved phone pairing(s)", count=pair_count)
        window.text("status", f"{saved_pairings} · {t(connection_key)}")
    window.on_tick = update_status
    update_status()
    return window


def pairing_controls(qr_image, *, expires_at: int, request_received,
                     cancel_requested, phone_opened, development_mode: bool) -> ControlWindow:
    """Accessible shell around the existing in-memory, one-time pairing QR."""
    from pairing_ui import PairingWindowOutcome, pairing_seconds_remaining
    window = ControlWindow(t("QR Scanner - Pair Phone"), (574, 624),
                           on_close=lambda: window.finish(PairingWindowOutcome.CANCELLED))
    try:
        window.label("title", t("PAIR A PHONE"), (28, 18, 518, 38), heading=True)
        window.label("instructions", t("Scan with your camera or Google Lens.") + "\n" +
                     t("Keep this window open until your phone connects."), (28, 61, 518, 46))
        window.image("qr", qr_image, (80, 114, 414, 414), description=t("Pair Phone"))
        window.label("timer", "", (28, 536, 518, 30))
        if development_mode:
            window.label("development", "Local test mode: a real phone cannot connect.", (28, 566, 518, 22))
        window.button("cancel", t("Cancel"), (28, 588 if development_mode else 576, 518, 36 if development_mode else 44),
                      lambda: window.finish(PairingWindowOutcome.CANCELLED))

        def update() -> None:
            if cancel_requested is not None and cancel_requested.is_set():
                window.finish(PairingWindowOutcome.CANCELLED)
            elif request_received.is_set():
                window.finish(PairingWindowOutcome.REQUEST_RECEIVED)
            elif phone_opened is not None and phone_opened.is_set():
                window.finish(PairingWindowOutcome.PHONE_OPENED)
            else:
                remaining = pairing_seconds_remaining(expires_at)
                if remaining <= 0:
                    window.finish(PairingWindowOutcome.EXPIRED)
                else:
                    window.text("timer", t("{seconds} seconds remaining", seconds=remaining))
        window.on_tick = update
        window.text("timer", t("{seconds} seconds remaining", seconds=pairing_seconds_remaining(expires_at)))
        return window
    except BaseException:
        window.close()
        raise


def scanner_return_controls(qr_image, *, phone_opened, expires_at: int | None) -> ControlWindow:
    import time
    window = ControlWindow(t("QR Scanner - Open Phone Scanner"), (574, 600))
    try:
        window.label("title", t("OPEN PHONE SCANNER"), (28, 20, 518, 38), heading=True)
        window.label("intro", t("Scan to reopen. No new pairing needed."), (28, 61, 518, 34))
        window.image("qr", qr_image, (112, 98, 350, 350), description=t("Open scanner on phone"))
        window.label("browser", t("Use the same phone browser you paired with."), (28, 465, 518, 34))
        window.label("next", t("Then tap Scan QR to send a link to this PC."), (28, 502, 518, 34))
        window.button("back", t("Back"), (28, 548, 518, 44), lambda: window.finish(None))
        def update() -> None:
            if phone_opened is not None and phone_opened.is_set():
                window.finish(None)
            elif expires_at is not None and time.time() >= expires_at:
                window.finish(None)
        window.on_tick = update
        return window
    except BaseException:
        window.close()
        raise


def phone_controls(
    phones: Sequence[PairedPhoneView],
    *,
    confirm_remove: Callable[[str, str], bool],
) -> ControlWindow:
    from paired_phones_ui import PairedPhonesAction, PairedPhonesDecision, abbreviated_pair_id
    items = tuple(phones)
    def finish(action: PairedPhonesAction) -> None:
        window.finish(PairedPhonesDecision(action))
    window = ControlWindow(t("QR Scanner - Paired Phones"), (620, 500),
                           on_close=lambda: finish(PairedPhonesAction.BACK))
    window.label("title", t("PAIRED PHONES"), (28, 22, 560, 40), heading=True)
    window.label("help", t("Select a phone to manage its access."), (28, 68, 560, 32))
    def selected_phone() -> PairedPhoneView | None:
        index = window.selection("phones")
        return items[index] if 0 <= index < len(items) else None
    def update_remove_access() -> None:
        window.enable("remove", selected_phone() is not None)
    window.choices("phones", t("Paired Phones"),
                   [f"{p.phone_label} — {abbreviated_pair_id(p.pair_id)}" for p in items],
                   (28, 110, 564, 252), update_remove_access)
    window.button("add", t("Add phone"), (28, 384, 214, 45), lambda: finish(PairedPhonesAction.PAIR_ANOTHER))
    window.button("back", t("Back"), (254, 384, 118, 45), lambda: finish(PairedPhonesAction.BACK))
    def remove() -> None:
        phone = selected_phone()
        if phone is not None and confirm_remove(phone.phone_label, abbreviated_pair_id(phone.pair_id)):
            window.finish(PairedPhonesDecision(PairedPhonesAction.REMOVE, phone))
    window.button("remove", t("Remove"), (384, 384, 208, 45), remove, enabled=False)
    window.button("scanner", t("Open scanner on phone"), (28, 442, 564, 42), lambda: finish(PairedPhonesAction.OPEN_SCANNER))
    return window


def settings_controls(
    *,
    startup_reader: Callable[[], bool] = is_startup_enabled,
    startup_writer: Callable[[bool], None] = set_startup_enabled,
    language_writer: Callable[[str], None] = set_language,
) -> ControlWindow:
    window = ControlWindow(t("Settings and about"), (620, 480))
    window.label("title", t("Settings and about"), (28, 24, 550, 42), heading=True)
    window.label("language_label", t("Language"), (28, 91, 230, 30))
    def language_changed() -> None:
        try:
            language_writer("tr" if window.selection("language") == 0 else "en")
            for name, key in labels.items():
                window.text(name, t(key))
            window.title(t("Settings and about"))
            window.text("version", f"{t('Version')}: {APP_VERSION}")
            update_startup_label()
        except OSError:
            window.text("message", t("Language preference could not be saved."))
        window.selection("language", 0 if get_language() == "tr" else 1)
    window.choices("language", t("Language"), ["Türkçe", "English"], (290, 84, 300, 190), language_changed, dropdown=True)
    window.selection("language", 0 if get_language() == "tr" else 1)
    def update_startup_label() -> None:
        window.text("startup", t("Start with Windows") + " · " + t("On" if startup_reader() else "Off"))
    def startup_changed() -> None:
        try:
            startup_writer(window.check("startup"))
            window.text("message", t("Preferences are saved on this device."))
        except OSError:
            window.text("message", t("Startup could not be changed. Try again."))
        window.check("startup", startup_reader())
        update_startup_label()
    window.checkbox("startup", t("Start with Windows"), (28, 152, 564, 40), startup_changed, startup_reader())
    update_startup_label()
    window.label("startup_help", t("Starts in the tray; the camera stays off."), (28, 199, 564, 30))
    window.label("version", f"{t('Version')}: {APP_VERSION}", (28, 251, 564, 32))
    window.button("downloads", t("Official downloads"), (28, 296, 300, 44), lambda: webbrowser.open(RELEASES_URL))
    window.label("license", t("MIT license · Free to use"), (28, 356, 560, 29))
    window.label("message", t("Preferences are saved on this device."), (28, 393, 560, 30))
    window.button("back", t("Back"), (412, 430, 180, 40), lambda: window.finish(None))
    labels = {"title": "Settings and about", "language_label": "Language", "startup": "Start with Windows",
              "startup_help": "Starts in the tray; the camera stays off.", "downloads": "Official downloads",
              "license": "MIT license · Free to use", "message": "Preferences are saved on this device.", "back": "Back"}
    return window
