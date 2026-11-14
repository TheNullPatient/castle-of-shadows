"""Подбор размера окна для режима отображения ``auto``.

SDL инициализируется здесь до создания игрового окна: это позволяет узнать
размер рабочего стола и заранее выбрать ширину консоли. Если дисплей
недоступен (например, в тестах или при запуске без видеодрайвера), берётся
безопасное значение по умолчанию.
"""
from __future__ import annotations

import tcod

from constants import SCREEN_H, TILE_H, TILE_W, VIEW_W

SDL_INIT_VIDEO = 0x20
MIN_AUTO_WIDTH = VIEW_W
MAX_AUTO_WIDTH = 320
FALLBACK_AUTO_WIDTH = 98

# Доля рабочего стола, которую должно занимать окно по высоте и ширине.
WINDOW_HEIGHT_RATIO = 0.88
WINDOW_WIDTH_RATIO = 0.92


def desktop_size() -> tuple[int, int] | None:
    """Размер рабочей области основного монитора в точках или None."""
    try:
        if not tcod.lib.SDL_WasInit(SDL_INIT_VIDEO):
            if not tcod.lib.SDL_InitSubSystem(SDL_INIT_VIDEO):
                return None
        display = tcod.lib.SDL_GetPrimaryDisplay()
        if not display:
            return None
        rect = tcod.ffi.new("SDL_Rect *")
        if tcod.lib.SDL_GetDisplayUsableBounds(display, rect):
            width, height = int(rect.w), int(rect.h)
            if width > 0 and height > 0:
                return width, height
        mode = tcod.lib.SDL_GetDesktopDisplayMode(display)
        if mode:
            width, height = int(mode.w), int(mode.h)
            if width > 0 and height > 0:
                return width, height
    except Exception:  # pragma: no cover - зависит от платформы и драйвера
        return None
    return None


def auto_columns(desktop: tuple[int, int] | None = None) -> int:
    """Подобрать число колонок так, чтобы окно помещалось на экране.

    Высота консоли фиксирована (33 строки), поэтому масштаб клетки считается
    от высоты рабочего стола, а ширина — от оставшегося места по горизонтали.
    """
    if desktop is None:
        desktop = desktop_size()
    if desktop is None:
        return FALLBACK_AUTO_WIDTH
    width, height = desktop
    target_height = max(1.0, height * WINDOW_HEIGHT_RATIO)
    scale = target_height / (SCREEN_H * TILE_H)
    columns = int((width * WINDOW_WIDTH_RATIO) / (TILE_W * scale))
    return max(MIN_AUTO_WIDTH, min(MAX_AUTO_WIDTH, columns))


def auto_window_size(
    columns: int,
    rows: int = SCREEN_H,
    desktop: tuple[int, int] | None = None,
) -> tuple[int, int]:
    """Размер окна в пикселях для режима ``auto``.

    Колонки уже подобраны под рабочую область, поэтому здесь остаётся
    вписать окно в те же пропорции по высоте и ширине. Если дисплей
    недоступен, используется естественный размер клеток 12×20.
    """
    columns = max(1, int(columns))
    rows = max(1, int(rows))
    if desktop is None:
        desktop = desktop_size()
    if desktop is None:
        return columns * TILE_W, rows * TILE_H
    width, height = desktop
    target_w = max(1.0, width * WINDOW_WIDTH_RATIO)
    target_h = max(1.0, height * WINDOW_HEIGHT_RATIO)
    scale = min(
        target_w / (columns * TILE_W),
        target_h / (rows * TILE_H),
    )
    return max(1, int(columns * TILE_W * scale)), max(
        1, int(rows * TILE_H * scale)
    )


def columns_for_window(
    window_width: int,
    window_height: int,
    rows: int = SCREEN_H,
) -> int:
    """Столбцы консоли под текущее соотношение сторон окна.

    В ``auto`` высота консоли фиксирована, а ширина подбирается так, чтобы
    клетки сохраняли пропорции 12×20 при любом размере окна. Это позволяет
    заполнить окно целиком, не растягивая шрифт по одной оси.
    """
    rows = max(1, int(rows))
    if window_width <= 0 or window_height <= 0:
        return MIN_AUTO_WIDTH
    scale = window_height / (rows * TILE_H)
    if scale <= 0:
        return MIN_AUTO_WIDTH
    columns = round(window_width / (TILE_W * scale))
    return max(MIN_AUTO_WIDTH, min(MAX_AUTO_WIDTH, columns))


def minimum_window_size(
    columns: int, rows: int = SCREEN_H
) -> tuple[int, int]:
    """Минимальный размер окна, при котором клетки остаются 12×20."""
    columns = max(1, int(columns))
    rows = max(1, int(rows))
    return columns * TILE_W, rows * TILE_H
