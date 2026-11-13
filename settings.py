"""Пользовательские настройки, которые сохраняются между запусками."""
from __future__ import annotations

import json
from pathlib import Path

from constants import DEFAULT_DISPLAY_MODE, DISPLAY_MODES

ROOT = Path(__file__).resolve().parent
SETTINGS_PATH = ROOT / "settings.json"


def default_settings() -> dict:
    return {"display_mode": DEFAULT_DISPLAY_MODE}


def normalize_display_mode(mode: object) -> str:
    """Вернуть известный ключ режима или значение по умолчанию."""
    if isinstance(mode, str) and mode in DISPLAY_MODES:
        return mode
    return DEFAULT_DISPLAY_MODE


def load_settings() -> dict:
    """Прочитать settings.json, молча откатившись к значениям по умолчанию."""
    settings = default_settings()
    try:
        raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return settings
    if isinstance(raw, dict):
        settings["display_mode"] = normalize_display_mode(
            raw.get("display_mode")
        )
    return settings


def save_settings(settings: dict) -> bool:
    """Записать настройки; ошибки записи не должны ронять игру."""
    data = default_settings()
    data["display_mode"] = normalize_display_mode(settings.get("display_mode"))
    try:
        SETTINGS_PATH.write_text(
            json.dumps(data, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError:
        return False
    return True


def load_display_mode() -> str:
    return load_settings()["display_mode"]


def save_display_mode(mode: str) -> bool:
    return save_settings({"display_mode": mode})
