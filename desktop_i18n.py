"""One shared TR/EN catalogue for desktop and phone; payloads stay untouched."""
from __future__ import annotations
import json
import os
from pathlib import Path
import sys
import time

from app_settings import SettingsStore

_root = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
_catalog_path = (_root / "assets/translations.tr.json" if getattr(sys, "frozen", False)
                 else _root / "pwa/lib/translations.tr.json")
CATALOG = json.loads(_catalog_path.read_text(encoding="utf-8"))
EN_CATALOG = json.loads(_catalog_path.with_name("translations.en.json").read_text(encoding="utf-8"))
_language = "en"
_checked = float("-inf")


def get_language() -> str:
    global _language, _checked
    override = os.environ.get("WQRS_UI_LANGUAGE")
    if override in {"en", "tr"}:
        return override
    if time.monotonic() - _checked >= 1:
        _language = SettingsStore().load().language
        _checked = time.monotonic()
    return _language


def set_language(language: str) -> None:
    global _language, _checked
    if language not in {"en", "tr"}:
        raise ValueError("Unsupported language")
    SettingsStore().update(language=language)
    _language, _checked = language, time.monotonic()


def reload_language() -> None:
    global _checked
    _checked = float("-inf")


def t(text: str, *, language: str | None = None, **values: object) -> str:
    key = " ".join(text.split())
    translated = text
    catalogue = CATALOG if (language or get_language()) == "tr" else EN_CATALOG
    if key in catalogue:
        translated = text[:len(text) - len(text.lstrip())] + catalogue[key] + text[len(text.rstrip()):]
    return translated.format(**values) if values else translated
