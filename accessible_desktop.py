"""Accessible Windows control screens, keeping decisions in existing domains."""
from collections.abc import Callable, Sequence

from accessible_controls import ControlWindow
from desktop_i18n import t
from native_dialogs import WindowCloseChoice
from windows_startup import is_startup_enabled, set_startup_enabled
from desktop_i18n import get_language, set_language
from app_info import APP_VERSION, RELEASES_URL
import webbrowser


def home_controls(*, pair_count: int, confirm_exit: Callable[[], bool] | None,
                  choose_close: Callable[[], WindowCloseChoice]) -> ControlWindow:
    from home_ui import HomeAction, action_cards
    from bridge.pairing_controller import configured_relay_origin
    from receiver_status import connection_confirmed

    window: ControlWindow
    def leave():
        choice = choose_close()
        if choice is WindowCloseChoice.BACKGROUND:
            window.finish(HomeAction.BACKGROUND)
        elif choice is WindowCloseChoice.EXIT:
            window.finish(HomeAction.EXIT)

    def exit_app():
        if confirm_exit is None or confirm_exit():
            window.finish(HomeAction.EXIT)

    window = ControlWindow("QR Scanner", (620, 575), on_close=leave,
                           on_escape=lambda: window.finish(HomeAction.BACKGROUND))
    window.label("title", "QR SCANNER", (28, 22, 330, 40), heading=True)
    window.label("intro", t("Choose what you want to do."), (28, 68, 560, 25))
    window.label("status", "", (28, 96, 560, 28))
    for index, card in enumerate(action_cards(pair_count)):
        y = 137 + index * 83
        window.button(card.action.value, t(card.title), (28, y, 564, 44),
                      lambda action=card.action: window.finish(action))
        window.label("help_" + card.action.value, t(card.description), (35, y + 48, 554, 28))
    window.button("settings", t("Settings and about"), (28, 486, 270, 42), lambda: window.finish(HomeAction.SETTINGS))
    window.button("exit", t("Exit"), (414, 486, 178, 42), exit_app)
    window.label("keyboard", t("Tab: move · Enter: select · ESC: background"), (28, 540, 560, 25))
    origin = configured_relay_origin()
    def update_status():
        text = t("No saved phone pairing") if pair_count == 0 else (
            t("{count} saved phone pairing(s)", count=pair_count) + " · " +
            t("Receiver connection confirmed" if connection_confirmed(origin) else "Receiver connection not confirmed"))
        window.text("status", text)
    window.on_tick = update_status
    update_status()
    return window


def phone_controls(phones: Sequence, *, confirm_remove: Callable[[str, str], bool]) -> ControlWindow:
    from paired_phones_ui import PairedPhonesAction, PairedPhonesDecision, abbreviated_pair_id
    items = tuple(phones)
    def finish(action):
        window.finish(PairedPhonesDecision(action))
    window = ControlWindow(t("QR Scanner - Paired Phones"), (620, 500),
                           on_close=lambda: finish(PairedPhonesAction.BACK))
    window.label("title", t("PAIRED PHONES"), (28, 22, 560, 40), heading=True)
    window.label("help", t("Select a phone to manage its access."), (28, 68, 560, 32))
    def selected_phone():
        index = window.selection("phones")
        return items[index] if 0 <= index < len(items) else None
    def selected():
        window.enable("remove", selected_phone() is not None)
    window.choices("phones", t("Paired Phones"),
                   [f"{p.phone_label} — {abbreviated_pair_id(p.pair_id)}" for p in items],
                   (28, 110, 564, 252), selected)
    window.button("add", t("Add phone"), (28, 384, 214, 45), lambda: finish(PairedPhonesAction.PAIR_ANOTHER))
    window.button("back", t("Back"), (254, 384, 118, 45), lambda: finish(PairedPhonesAction.BACK))
    def remove():
        phone = selected_phone()
        if phone is not None and confirm_remove(phone.phone_label, abbreviated_pair_id(phone.pair_id)):
            window.finish(PairedPhonesDecision(PairedPhonesAction.REMOVE, phone))
    window.button("remove", t("Remove"), (384, 384, 208, 45), remove, enabled=False)
    window.button("scanner", t("Open scanner on phone"), (28, 442, 564, 42), lambda: finish(PairedPhonesAction.OPEN_SCANNER))
    return window


def settings_controls(*, startup_reader=is_startup_enabled, startup_writer=set_startup_enabled,
                      language_writer=set_language) -> ControlWindow:
    window = ControlWindow(t("Settings and about"), (620, 480))
    window.label("title", t("Settings and about"), (28, 24, 550, 42), heading=True)
    window.label("language_label", t("Language"), (28, 91, 230, 30))
    def language_changed():
        try:
            language_writer("tr" if window.selection("language") == 0 else "en")
            for name, key in labels.items():
                window.text(name, t(key))
            window.title(t("Settings and about"))
            window.text("version", f"{t('Version')}: {APP_VERSION}")
            startup_label()
        except OSError:
            window.text("message", t("Language preference could not be saved."))
        window.selection("language", 0 if get_language() == "tr" else 1)
    window.choices("language", t("Language"), ["Türkçe", "English"], (290, 84, 300, 190), language_changed, dropdown=True)
    window.selection("language", 0 if get_language() == "tr" else 1)
    def startup_label():
        window.text("startup", t("Start with Windows") + " · " + t("On" if startup_reader() else "Off"))
    def startup_changed():
        try:
            startup_writer(window.check("startup"))
            window.text("message", t("Preferences are saved on this device."))
        except OSError:
            window.text("message", t("Startup could not be changed. Try again."))
        window.check("startup", startup_reader())
        startup_label()
    window.checkbox("startup", t("Start with Windows"), (28, 152, 564, 40), startup_changed, startup_reader())
    startup_label()
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
