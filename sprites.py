"""Запечённые спрайты предметов и врагов.

В клетке tcod живёт один символ и один цвет текста, поэтому картинка
запекается прямо в тайлсет (как ниша с факелом). Спрайты рисуются
векторно в увеличенном буфере: эллипсы, многоугольники и линии с
затемнённым контуром. Цвет клетки задаёт ui.py, а уровни серого в спрайте
дают объём, тени и блики, поэтому один и тот же силуэт работает для
зелья, врага и босса любого цвета.

Рисование идёт в долях клетки (0..1), поэтому спрайты одинаково выглядят
при любой высоте шрифта и не зависят от масштаба окна.
"""
from __future__ import annotations

from typing import Callable, Iterable

import numpy as np

# Уровни серого: цвет клетки умножается на них, поэтому 1.0 — чистый цвет
# предмета, 0.5 — тень, 0.26 — контур.
GLOW = 1.00
LIGHT = 0.86
BODY = 0.62
SHADOW = 0.42
DARK = 0.24
MUTED = 0.34
OUTLINE = 0.16

_SUPERSAMPLE = 4


class _Canvas:
    """Мини-холст в долях клетки с мягким контуром и суперсэмплингом."""

    def __init__(self, width: int, height: int, ss: int = _SUPERSAMPLE):
        self.width = max(1, width)
        self.height = max(1, height)
        self.ss = max(1, ss)
        w = self.width * self.ss
        h = self.height * self.ss
        self.rgb = np.zeros((h, w, 3), dtype=np.float32)
        self.alpha = np.zeros((h, w), dtype=np.float32)
        yy, xx = np.mgrid[0:h, 0:w]
        # Координаты центров пикселей в долях клетки.
        self.x = (xx + 0.5) / (self.width * self.ss)
        self.y = (yy + 0.5) / (self.height * self.ss)

    # --- примитивы -----------------------------------------------------
    def ellipse(
        self,
        cx: float,
        cy: float,
        rx: float,
        ry: float,
        shade: float = BODY,
    ) -> None:
        mask = (
            ((self.x - cx) / max(rx, 1e-6)) ** 2
            + ((self.y - cy) / max(ry, 1e-6)) ** 2
            <= 1.0
        )
        self._paint(mask, shade)

    def rect(
        self,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        shade: float = BODY,
    ) -> None:
        mask = (
            (self.x >= min(x0, x1))
            & (self.x <= max(x0, x1))
            & (self.y >= min(y0, y1))
            & (self.y <= max(y0, y1))
        )
        self._paint(mask, shade)

    def poly(self, points: Iterable[tuple[float, float]], shade: float) -> None:
        pts = list(points)
        inside = np.zeros_like(self.x, dtype=bool)
        count = len(pts)
        for i in range(count):
            x0, y0 = pts[i]
            x1, y1 = pts[(i + 1) % count]
            crosses = (y0 > self.y) != (y1 > self.y)
            denom = y1 - y0
            if abs(denom) < 1e-9:
                continue
            cut = x0 + (self.y - y0) * (x1 - x0) / denom
            inside ^= crosses & (self.x < cut)
        self._paint(inside, shade)

    def line(
        self,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        width: float,
        shade: float = BODY,
    ) -> None:
        dx = x1 - x0
        dy = y1 - y0
        length_sq = dx * dx + dy * dy
        if length_sq < 1e-12:
            self.ellipse(x0, y0, width / 2, width / 2, shade)
            return
        t = ((self.x - x0) * dx + (self.y - y0) * dy) / length_sq
        t = np.clip(t, 0.0, 1.0)
        px = x0 + t * dx
        py = y0 + t * dy
        mask = (self.x - px) ** 2 + (self.y - py) ** 2 <= (width / 2) ** 2
        self._paint(mask, shade)

    def arc(
        self,
        cx: float,
        cy: float,
        rx: float,
        ry: float,
        start: float,
        end: float,
        width: float,
        shade: float = BODY,
        steps: int = 28,
    ) -> None:
        prev: tuple[float, float] | None = None
        for i in range(steps + 1):
            angle = start + (end - start) * i / steps
            point = (cx + rx * np.cos(angle), cy + ry * np.sin(angle))
            if prev is not None:
                self.line(*prev, *point, width, shade)
            prev = point

    def _paint(self, mask: np.ndarray, shade: float) -> None:
        self.rgb[mask] = shade
        self.alpha[mask] = 1.0

    # --- финализация ---------------------------------------------------
    def _add_outline(self) -> None:
        """Обвести силуэт тёмной каймой в один пиксель клетки."""
        filled = self.alpha > 0
        grown = filled.copy()
        radius = self.ss
        for _ in range(radius):
            for shift_y, shift_x in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                shifted = np.roll(grown, shift_y, axis=0)
                shifted = np.roll(shifted, shift_x, axis=1)
                grown |= shifted
        edge = grown & ~filled
        self.rgb[edge] = OUTLINE
        self.alpha[edge] = 1.0

    def finish(self) -> np.ndarray:
        self._add_outline()
        # Лёгкий вертикальный градиент: верх чуть светлее, низ темнее.
        self.rgb *= (1.05 - 0.12 * self.y)[..., None]
        np.clip(self.rgb, 0.0, 1.0, out=self.rgb)

        ss = self.ss
        h = self.height
        w = self.width
        alpha = self.alpha.reshape(h, ss, w, ss).mean(axis=(1, 3))
        prem = (self.rgb * self.alpha[..., None]).reshape(
            h, ss, w, ss, 3
        ).mean(axis=(1, 3))
        rgb = prem / np.maximum(alpha, 1e-6)[..., None]
        return np.dstack([np.clip(rgb, 0.0, 1.0) * 255.0, alpha * 255.0]).astype(
            np.uint8
        )


def _eyes(
    canvas: _Canvas,
    y: float,
    spread: float = 0.05,
    radius: float = 0.035,
    shade: float = GLOW,
) -> None:
    canvas.ellipse(0.5 - spread, y, radius, radius * 1.15, shade)
    canvas.ellipse(0.5 + spread, y, radius, radius * 1.15, shade)


def _legs(
    canvas: _Canvas,
    top: float = 0.76,
    bottom: float = 0.96,
    spread: float = 0.075,
    width: float = 0.075,
    shade: float = SHADOW,
) -> None:
    canvas.rect(0.5 - spread - width / 2, top, 0.5 - spread + width / 2, bottom, shade)
    canvas.rect(0.5 + spread - width / 2, top, 0.5 + spread + width / 2, bottom, shade)


# --- предметы ---------------------------------------------------------


def _sword(c: _Canvas) -> None:
    c.poly([(0.50, 0.01), (0.60, 0.08), (0.60, 0.60), (0.40, 0.60), (0.40, 0.08)], LIGHT)
    c.line(0.50, 0.06, 0.50, 0.57, 0.025, GLOW)
    c.rect(0.24, 0.60, 0.76, 0.67, BODY)  # гарда
    c.rect(0.45, 0.67, 0.55, 0.86, SHADOW)  # рукоять
    c.ellipse(0.50, 0.90, 0.065, 0.05, BODY)  # навершие


def _axe(c: _Canvas) -> None:
    c.rect(0.60, 0.14, 0.68, 0.96, SHADOW)  # рукоять
    c.poly(
        [
            (0.62, 0.12),
            (0.34, 0.14),
            (0.14, 0.24),
            (0.10, 0.36),
            (0.18, 0.48),
            (0.40, 0.52),
            (0.62, 0.46),
        ],
        LIGHT,
    )
    c.poly(
        [(0.60, 0.18), (0.42, 0.20), (0.30, 0.32), (0.42, 0.44), (0.60, 0.42)],
        BODY,
    )
    c.line(0.14, 0.25, 0.17, 0.45, 0.03, GLOW)  # кромка
    c.rect(0.56, 0.44, 0.62, 0.56, BODY)  # крепление


def _spear(c: _Canvas) -> None:
    c.line(0.5, 0.96, 0.5, 0.22, 0.055, SHADOW)
    c.poly([(0.5, 0.03), (0.36, 0.26), (0.44, 0.23), (0.5, 0.30), (0.56, 0.23), (0.64, 0.26)], LIGHT)
    c.poly([(0.5, 0.10), (0.42, 0.25), (0.5, 0.22)], BODY)


def _hammer(c: _Canvas) -> None:
    c.line(0.5, 0.98, 0.5, 0.32, 0.07, SHADOW)
    c.rect(0.16, 0.10, 0.84, 0.34, LIGHT)
    c.rect(0.20, 0.13, 0.80, 0.19, GLOW)
    c.rect(0.22, 0.28, 0.78, 0.34, BODY)
    c.line(0.16, 0.34, 0.84, 0.34, 0.03, DARK)


def _bow(c: _Canvas) -> None:
    c.arc(0.46, 0.5, 0.32, 0.46, 3.14159 - 1.15, 3.14159 + 1.15, 0.055, BODY)
    c.arc(0.46, 0.5, 0.32, 0.46, 3.14159 - 1.15, 3.14159 + 1.15, 0.02, LIGHT)
    c.line(0.32, 0.08, 0.32, 0.92, 0.018, SHADOW)
    c.line(0.34, 0.5, 0.52, 0.5, 0.035, LIGHT)


def _armor(c: _Canvas) -> None:
    c.poly(
        [
            (0.34, 0.14),
            (0.5, 0.10),
            (0.66, 0.14),
            (0.80, 0.24),
            (0.79, 0.40),
            (0.68, 0.52),
            (0.62, 0.76),
            (0.5, 0.83),
            (0.38, 0.76),
            (0.32, 0.52),
            (0.21, 0.40),
            (0.20, 0.24),
        ],
        BODY,
    )
    c.ellipse(0.5, 0.17, 0.10, 0.06, DARK)  # горловина
    c.line(0.5, 0.34, 0.5, 0.72, 0.035, SHADOW)
    c.poly([(0.30, 0.22), (0.38, 0.18), (0.40, 0.50), (0.32, 0.46)], LIGHT)
    c.ellipse(0.27, 0.24, 0.09, 0.075, BODY)  # наплечники
    c.ellipse(0.73, 0.24, 0.09, 0.075, BODY)
    c.line(0.24, 0.36, 0.76, 0.36, 0.025, DARK)


def _potion(c: _Canvas, *, glow: bool = False) -> None:
    c.rect(0.42, 0.20, 0.58, 0.32, DARK)  # крышка
    c.rect(0.42, 0.30, 0.58, 0.42, SHADOW)  # горлышко
    c.ellipse(0.5, 0.64, 0.29, 0.26, BODY)
    c.ellipse(0.5, 0.70, 0.23, 0.18, LIGHT)  # жидкость
    c.ellipse(0.42, 0.58, 0.055, 0.06, GLOW)  # блик
    if glow:
        c.ellipse(0.57, 0.71, 0.045, 0.045, GLOW)
        c.ellipse(0.46, 0.76, 0.03, 0.03, GLOW)


def _scroll(c: _Canvas) -> None:
    c.rect(0.24, 0.22, 0.76, 0.82, BODY)
    c.ellipse(0.5, 0.22, 0.27, 0.075, LIGHT)
    c.ellipse(0.5, 0.82, 0.27, 0.075, LIGHT)
    for y in (0.38, 0.48, 0.58, 0.68):
        c.line(0.32, y, 0.68, y, 0.022, DARK)
    c.line(0.24, 0.30, 0.24, 0.76, 0.02, SHADOW)


def _gold(c: _Canvas) -> None:
    c.ellipse(0.50, 0.78, 0.29, 0.12, BODY)
    c.ellipse(0.50, 0.76, 0.25, 0.085, LIGHT)
    c.ellipse(0.36, 0.58, 0.17, 0.11, BODY)
    c.ellipse(0.36, 0.56, 0.135, 0.075, LIGHT)
    c.ellipse(0.62, 0.42, 0.16, 0.10, BODY)
    c.ellipse(0.62, 0.40, 0.125, 0.07, GLOW)


# --- враги ------------------------------------------------------------


def _rat(c: _Canvas) -> None:
    c.arc(0.72, 0.68, 0.20, 0.16, -0.6, 1.3, 0.035, SHADOW)  # хвост
    c.ellipse(0.46, 0.72, 0.28, 0.17, BODY)
    c.ellipse(0.22, 0.68, 0.13, 0.11, BODY)
    c.ellipse(0.27, 0.52, 0.075, 0.07, BODY)  # ухо
    c.ellipse(0.27, 0.52, 0.035, 0.033, SHADOW)
    c.ellipse(0.15, 0.68, 0.032, 0.032, GLOW)  # глаз
    c.ellipse(0.06, 0.74, 0.028, 0.022, DARK)  # нос
    c.rect(0.32, 0.84, 0.38, 0.94, SHADOW)
    c.rect(0.54, 0.84, 0.60, 0.94, SHADOW)


def _bat(c: _Canvas) -> None:
    c.poly(
        [(0.48, 0.44), (0.10, 0.22), (0.04, 0.54), (0.26, 0.54), (0.34, 0.66)],
        BODY,
    )
    c.poly(
        [(0.52, 0.44), (0.90, 0.22), (0.96, 0.54), (0.74, 0.54), (0.66, 0.66)],
        BODY,
    )
    c.poly([(0.44, 0.40), (0.40, 0.30), (0.48, 0.36)], LIGHT)
    c.poly([(0.56, 0.40), (0.60, 0.30), (0.52, 0.36)], LIGHT)
    c.ellipse(0.5, 0.52, 0.09, 0.13, BODY)
    _eyes(c, 0.50, 0.035, 0.022)
    c.line(0.46, 0.64, 0.44, 0.74, 0.03, SHADOW)
    c.line(0.54, 0.64, 0.56, 0.74, 0.03, SHADOW)


def _goblin(c: _Canvas) -> None:
    _legs(c, top=0.80, bottom=0.94, spread=0.065, width=0.055)
    c.poly([(0.36, 0.30), (0.10, 0.20), (0.33, 0.42)], BODY)
    c.poly([(0.64, 0.30), (0.90, 0.20), (0.67, 0.42)], BODY)
    c.ellipse(0.5, 0.64, 0.15, 0.16, BODY)
    c.line(0.36, 0.56, 0.28, 0.72, 0.055, SHADOW)
    c.line(0.64, 0.56, 0.72, 0.72, 0.055, SHADOW)
    c.ellipse(0.5, 0.33, 0.16, 0.145, BODY)
    _eyes(c, 0.33, 0.06, 0.035)
    c.line(0.44, 0.42, 0.56, 0.42, 0.025, DARK)


def _skeleton(c: _Canvas) -> None:
    _legs(c, top=0.70, bottom=0.94, spread=0.055, width=0.045)
    c.ellipse(0.5, 0.53, 0.15, 0.13, DARK)  # грудная клетка
    c.line(0.5, 0.40, 0.5, 0.70, 0.03, LIGHT)  # позвоночник
    for y, half in ((0.46, 0.14), (0.52, 0.16), (0.58, 0.13)):
        c.line(0.5 - half, y, 0.5 + half, y, 0.03, BODY)  # рёбра
    c.ellipse(0.5, 0.64, 0.13, 0.06, BODY)  # таз
    c.line(0.28, 0.46, 0.22, 0.64, 0.035, LIGHT)  # руки
    c.line(0.72, 0.46, 0.78, 0.64, 0.035, LIGHT)
    c.ellipse(0.5, 0.26, 0.16, 0.14, LIGHT)  # череп
    c.ellipse(0.44, 0.25, 0.052, 0.055, DARK)  # глазницы
    c.ellipse(0.56, 0.25, 0.052, 0.055, DARK)
    c.ellipse(0.44, 0.25, 0.016, 0.016, GLOW)  # зрачки
    c.ellipse(0.56, 0.25, 0.016, 0.016, GLOW)
    c.poly([(0.5, 0.29), (0.465, 0.35), (0.535, 0.35)], DARK)
    c.rect(0.42, 0.36, 0.58, 0.40, MUTED)  # челюсть
    for x in (0.45, 0.50, 0.55):
        c.line(x, 0.36, x, 0.40, 0.012, DARK)


def _orc(c: _Canvas) -> None:
    _legs(c, top=0.76, bottom=0.95, spread=0.08, width=0.085)
    c.ellipse(0.30, 0.48, 0.11, 0.10, BODY)  # плечи
    c.ellipse(0.70, 0.48, 0.11, 0.10, BODY)
    c.ellipse(0.5, 0.60, 0.24, 0.20, BODY)
    c.line(0.28, 0.52, 0.20, 0.74, 0.085, SHADOW)
    c.line(0.72, 0.52, 0.80, 0.74, 0.085, SHADOW)
    c.ellipse(0.5, 0.27, 0.16, 0.13, BODY)
    c.poly([(0.40, 0.35), (0.60, 0.35), (0.56, 0.40), (0.44, 0.40)], SHADOW)
    c.poly([(0.42, 0.39), (0.40, 0.29), (0.46, 0.37)], LIGHT)  # клыки
    c.poly([(0.58, 0.39), (0.60, 0.29), (0.54, 0.37)], LIGHT)
    _eyes(c, 0.27, 0.06, 0.03)
    c.line(0.40, 0.23, 0.60, 0.23, 0.03, DARK)  # брови


def _spider(c: _Canvas) -> None:
    for side in (-1, 1):
        for i, (y0, y1) in enumerate(
            ((0.52, 0.32), (0.58, 0.46), (0.62, 0.70), (0.58, 0.86))
        ):
            x0 = 0.5 + side * 0.10
            x1 = 0.5 + side * (0.36 + 0.04 * (i % 2))
            c.line(x0, y0, x1, y1, 0.028, SHADOW)
    c.ellipse(0.5, 0.70, 0.24, 0.20, BODY)  # брюшко
    c.ellipse(0.5, 0.50, 0.13, 0.12, BODY)  # головогрудь
    c.ellipse(0.5, 0.60, 0.09, 0.05, LIGHT)
    c.ellipse(0.45, 0.49, 0.028, 0.028, GLOW)
    c.ellipse(0.55, 0.49, 0.028, 0.028, GLOW)
    c.ellipse(0.47, 0.54, 0.02, 0.02, GLOW)
    c.ellipse(0.53, 0.54, 0.02, 0.02, GLOW)


def _robe(c: _Canvas, *, hood: bool = True, shade: float = BODY) -> None:
    c.poly(
        [(0.5, 0.20), (0.30, 0.36), (0.20, 0.94), (0.80, 0.94), (0.70, 0.36)],
        shade,
    )
    if hood:
        c.ellipse(0.5, 0.28, 0.17, 0.16, LIGHT)
        c.ellipse(0.5, 0.32, 0.11, 0.11, DARK)
    c.line(0.5, 0.44, 0.5, 0.86, 0.03, SHADOW)


def _cultist(c: _Canvas) -> None:
    c.poly([(0.3, 0.4), (0.16, 0.55), (0.26, 0.66)], SHADOW)
    c.poly([(0.7, 0.4), (0.84, 0.55), (0.74, 0.66)], SHADOW)
    _robe(c)
    _eyes(c, 0.32, 0.045, 0.025)


def _troll(c: _Canvas) -> None:
    _legs(c, top=0.76, bottom=0.96, spread=0.10, width=0.095)
    c.ellipse(0.28, 0.46, 0.12, 0.11, BODY)  # плечи
    c.ellipse(0.72, 0.46, 0.12, 0.11, BODY)
    c.ellipse(0.5, 0.62, 0.27, 0.22, BODY)
    c.line(0.26, 0.50, 0.17, 0.76, 0.10, SHADOW)  # руки
    c.line(0.74, 0.50, 0.83, 0.76, 0.10, SHADOW)
    c.ellipse(0.16, 0.80, 0.07, 0.07, BODY)  # кулаки
    c.ellipse(0.84, 0.80, 0.07, 0.07, BODY)
    c.line(0.40, 0.20, 0.28, 0.05, 0.06, LIGHT)  # рога
    c.line(0.60, 0.20, 0.72, 0.05, 0.06, LIGHT)
    c.ellipse(0.5, 0.26, 0.145, 0.115, BODY)
    c.poly([(0.42, 0.36), (0.58, 0.36), (0.54, 0.41), (0.46, 0.41)], SHADOW)
    c.poly([(0.44, 0.38), (0.42, 0.30), (0.48, 0.37)], LIGHT)
    c.poly([(0.56, 0.38), (0.58, 0.30), (0.52, 0.37)], LIGHT)
    _eyes(c, 0.26, 0.055, 0.032)


def _cultist(c: _Canvas) -> None:
    c.poly([(0.30, 0.40), (0.14, 0.56), (0.25, 0.68)], SHADOW)
    c.poly([(0.70, 0.40), (0.86, 0.56), (0.75, 0.68)], SHADOW)
    _robe(c)
    c.ellipse(0.5, 0.27, 0.175, 0.155, LIGHT)  # капюшон
    c.ellipse(0.5, 0.31, 0.115, 0.11, DARK)  # лицо в тени
    _eyes(c, 0.31, 0.045, 0.028)
    c.line(0.5, 0.44, 0.5, 0.88, 0.025, DARK)


def _golem(c: _Canvas) -> None:
    _legs(c, top=0.76, bottom=0.95, spread=0.10, width=0.10, shade=DARK)
    c.rect(0.16, 0.42, 0.29, 0.74, SHADOW)  # руки
    c.rect(0.71, 0.42, 0.84, 0.74, SHADOW)
    c.rect(0.29, 0.36, 0.71, 0.78, BODY)  # корпус
    c.ellipse(0.5, 0.36, 0.21, 0.06, BODY)  # плечи
    c.rect(0.35, 0.14, 0.65, 0.36, BODY)  # голова
    c.rect(0.39, 0.17, 0.61, 0.21, LIGHT)
    c.ellipse(0.5, 0.58, 0.09, 0.09, GLOW)  # руна
    c.ellipse(0.5, 0.58, 0.045, 0.045, BODY)
    c.line(0.36, 0.44, 0.40, 0.72, 0.022, DARK)
    c.line(0.64, 0.44, 0.60, 0.72, 0.022, DARK)
    _eyes(c, 0.27, 0.055, 0.03)


def _dragon(c: _Canvas, *, big_wings: bool = False) -> None:
    inset = 0.03 if big_wings else 0.0
    c.poly(
        [
            (0.46, 0.44),
            (0.10 - inset, 0.10 - inset),
            (0.03 - inset, 0.42),
            (0.22, 0.45),
            (0.33, 0.60),
        ],
        SHADOW,
    )
    c.poly(
        [
            (0.54, 0.44),
            (0.90 + inset, 0.10 - inset),
            (0.97 + inset, 0.42),
            (0.78, 0.45),
            (0.67, 0.60),
        ],
        SHADOW,
    )
    c.line(0.10 - inset, 0.10 - inset, 0.33, 0.60, 0.02, MUTED)
    c.line(0.90 + inset, 0.10 - inset, 0.67, 0.60, 0.02, MUTED)
    c.arc(0.26, 0.84, 0.22, 0.12, 2.3, 4.5, 0.05, BODY)  # хвост
    c.ellipse(0.5, 0.66, 0.23, 0.19, BODY)  # тело
    c.ellipse(0.5, 0.72, 0.15, 0.11, LIGHT)  # брюхо
    c.line(0.60, 0.56, 0.69, 0.38, 0.11, BODY)  # шея
    c.ellipse(0.71, 0.32, 0.13, 0.10, BODY)  # голова
    c.poly([(0.80, 0.29), (0.95, 0.32), (0.80, 0.37)], LIGHT)  # морда
    c.ellipse(0.70, 0.29, 0.025, 0.025, GLOW)  # глаз
    c.line(0.62, 0.78, 0.60, 0.92, 0.075, SHADOW)
    c.line(0.70, 0.80, 0.72, 0.92, 0.075, SHADOW)


# --- боссы ------------------------------------------------------------


def _skeleton_king(c: _Canvas) -> None:
    _skeleton(c)
    c.poly(
        [(0.36, 0.14), (0.40, 0.06), (0.44, 0.14), (0.48, 0.04), (0.52, 0.14),
         (0.56, 0.06), (0.60, 0.14), (0.64, 0.04), (0.66, 0.16)],
        GLOW,
    )


def _troll_chieftain(c: _Canvas) -> None:
    c.line(0.10, 0.42, 0.06, 0.88, 0.06, SHADOW)  # дубина
    c.ellipse(0.07, 0.38, 0.09, 0.13, BODY)
    c.ellipse(0.07, 0.38, 0.045, 0.08, LIGHT)
    _troll(c)
    c.poly([(0.38, 0.20), (0.30, 0.06), (0.42, 0.16)], LIGHT)
    c.poly([(0.62, 0.20), (0.70, 0.06), (0.58, 0.16)], LIGHT)


def _wyvern(c: _Canvas) -> None:
    _dragon(c, big_wings=True)
    c.poly([(0.70, 0.24), (0.76, 0.12), (0.78, 0.26)], GLOW)


def _lich(c: _Canvas) -> None:
    _robe(c)
    _eyes(c, 0.32, 0.045, 0.025)
    c.line(0.84, 0.28, 0.84, 0.92, 0.035, SHADOW)  # посох
    c.ellipse(0.84, 0.24, 0.075, 0.07, GLOW)
    c.ellipse(0.84, 0.24, 0.035, 0.032, BODY)
    c.poly(
        [(0.38, 0.12), (0.42, 0.04), (0.46, 0.12), (0.50, 0.02),
         (0.54, 0.12), (0.58, 0.04), (0.62, 0.12)],
        GLOW,
    )


def _shadow_lord(c: _Canvas) -> None:
    c.ellipse(0.5, 0.58, 0.36, 0.38, SHADOW)  # тёмный ореол
    _robe(c, shade=SHADOW)
    c.line(0.26, 0.30, 0.16, 0.10, 0.055, DARK)  # рога
    c.line(0.74, 0.30, 0.84, 0.10, 0.055, DARK)
    _eyes(c, 0.33, 0.05, 0.032, GLOW)
    c.line(0.40, 0.55, 0.60, 0.55, 0.03, DARK)


_SPRITE_DRAWERS: dict[str, tuple[Callable[[_Canvas], None], dict]] = {
    "item_sword": (_sword, {}),
    "item_axe": (_axe, {}),
    "item_spear": (_spear, {}),
    "item_hammer": (_hammer, {}),
    "item_bow": (_bow, {}),
    "item_armor": (_armor, {}),
    "item_potion_health": (_potion, {}),
    "item_potion_antidote": (_potion, {"glow": False}),
    "item_potion_boost": (_potion, {"glow": True}),
    "item_scroll": (_scroll, {}),
    "item_gold": (_gold, {}),
    "enemy_rat": (_rat, {}),
    "enemy_bat": (_bat, {}),
    "enemy_goblin": (_goblin, {}),
    "enemy_skeleton": (_skeleton, {}),
    "enemy_orc": (_orc, {}),
    "enemy_spider": (_spider, {}),
    "enemy_cultist": (_cultist, {}),
    "enemy_troll": (_troll, {}),
    "enemy_golem": (_golem, {}),
    "enemy_dragon": (_dragon, {}),
    "boss_skeleton_king": (_skeleton_king, {}),
    "boss_troll_chieftain": (_troll_chieftain, {}),
    "boss_wyvern": (_wyvern, {}),
    "boss_lich": (_lich, {}),
    "boss_shadow_lord": (_shadow_lord, {}),
}

SPRITES = tuple(_SPRITE_DRAWERS)

# Оружие, у которого есть собственный силуэт; остальные клинки рисуются
# мечом, а луки определяются по effect="ranged".
_WEAPON_SPRITES = {
    "Battleaxe": "item_axe",
    "Spear": "item_spear",
    "Warhammer": "item_hammer",
    "Shortbow": "item_bow",
    "Longbow": "item_bow",
}

ENEMY_SPRITES = {
    "Rat": "enemy_rat",
    "Bat": "enemy_bat",
    "Goblin": "enemy_goblin",
    "Skeleton": "enemy_skeleton",
    "Orc": "enemy_orc",
    "Giant Spider": "enemy_spider",
    "Cultist": "enemy_cultist",
    "Troll": "enemy_troll",
    "Stone Golem": "enemy_golem",
    "Dragon": "enemy_dragon",
    "Skeleton King": "boss_skeleton_king",
    "Troll Chieftain": "boss_troll_chieftain",
    "Wyvern": "boss_wyvern",
    "Lich": "boss_lich",
    "Shadow Lord": "boss_shadow_lord",
}


def item_sprite_key(item: object) -> str | None:
    """Выбрать спрайт для предмета по его виду и названию."""
    kind = getattr(item, "kind", "")
    name = getattr(item, "name", "")
    effect = getattr(item, "effect", "")
    if kind == "gold":
        return "item_gold"
    if kind == "armor":
        return "item_armor"
    if kind == "scroll":
        return "item_scroll"
    if kind == "potion":
        if effect == "health":
            return "item_potion_health"
        if effect == "antidote":
            return "item_potion_antidote"
        return "item_potion_boost"
    if kind == "weapon":
        if effect == "ranged":
            return "item_bow"
        return _WEAPON_SPRITES.get(name, "item_sword")
    return None


def enemy_sprite_key(name: str) -> str | None:
    return ENEMY_SPRITES.get(name)


def bake_sprite(name: str, tile_w: int, tile_h: int) -> np.ndarray:
    """Нарисовать спрайт под размер клетки и вернуть RGBA-растр."""
    drawer, options = _SPRITE_DRAWERS[name]
    canvas = _Canvas(tile_w, tile_h)
    drawer(canvas, **options)
    return canvas.finish()
