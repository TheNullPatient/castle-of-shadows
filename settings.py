"""Пользовательские настройки, которые сохраняются между запусками."""
from __future__ import annotations

import json
from pathlib import Path

from constants import (
    DEFAULT_DISPLAY_MODE,
    DEFAULT_MAP_STYLE,
    DISPLAY_MODES,
    MAP_STYLES,
)

ROOT = Path(__file__).resolve().parent
SETTINGS_PATH = ROOT / "settings.json"


def default_settings() -> dict:
    return {
        "display_mode": DEFAULT_DISPLAY_MODE,
        "map_style": DEFAULT_MAP_STYLE,
    }


def normalize_display_mode(mode: object) -> str:
    """Вернуть известный ключ режима или значение по умолчанию."""
    if isinstance(mode, str) and mode in DISPLAY_MODES:
        return mode
    return DEFAULT_DISPLAY_MODE


def normalize_map_style(style: object) -> str:
    """Вернуть известный стиль карты или значение по умолчанию."""
    if isinstance(style, str) and style in MAP_STYLES:
        return style
    return DEFAULT_MAP_STYLE


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
        settings["map_style"] = normalize_map_style(raw.get("map_style"))
    return settings


def save_settings(settings: dict) -> bool:
    """Записать настройки; ошибки записи не должны ронять игру.

    Недостающие ключи берутся из файла, поэтому сохранение одной настройки
    не сбрасывает остальные.
    """
    data = load_settings()
    data["display_mode"] = normalize_display_mode(
        settings.get("display_mode", data["display_mode"])
    )
    data["map_style"] = normalize_map_style(
        settings.get("map_style", data["map_style"])
    )
    try:
        SETTINGS_PATH.write_text(
            json.dumps(data, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError:
        return False
    return True
