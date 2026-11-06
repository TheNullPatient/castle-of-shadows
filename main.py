#!/usr/bin/env python3
"""Castle of Shadows — tcod entry point."""
from __future__ import annotations

import numpy as np
import tcod
import tcod.context
import tcod.console
import tcod.event
from tcod.event import KeySym

from constants import (
    LOG_H,
    SCREEN_H,
    SCREEN_W,
    TILE_H,
    TILE_W,
    TTF_PATH,
    TILESET_PATH,
)
from game import Game
from ui import render

MOVE_KEYS = {
    KeySym.UP: (0, -1),
    KeySym.DOWN: (0, 1),
    KeySym.LEFT: (-1, 0),
    KeySym.RIGHT: (1, 0),
    KeySym.K: (0, -1),
    KeySym.J: (0, 1),
    KeySym.H: (-1, 0),
    KeySym.L: (1, 0),
    KeySym.W: (0, -1),
    KeySym.S: (0, 1),
    KeySym.A: (-1, 0),
    KeySym.D: (1, 0),
}


# Глифы, которые реально встречаются в интерфейсе. Полный набор DejaVu
# (3300+ символов) хранить в готовом тайлсете незачем — это лишняя память.
_USED_CODEPOINTS = (
    set(range(32, 127))  # ASCII
    | set(range(0x2500, 0x2580))  # рамки, которые рисует draw_frame
    | {ord(ch) for ch in "·—█░▒▲▼×"}
)

# Границы, чтобы окно нельзя было «уменьшить в ноль» и чтобы тайлсет
# не разросся до сотен мегабайт на очень больших дисплеях.
_MIN_TILE_W, _MIN_TILE_H = 8, 13
_MAX_SCALE = 3.2

# После изменения размера окна ждём столько секунд тишины и только потом
# пересобираем шрифт: иначе перетаскивание окна превращается в слайд-шоу.
RESIZE_SETTLE_SECONDS = 0.12


def _tight_ttf_tileset(tile_w: int, tile_h: int) -> tcod.tileset.Tileset:
    """Собрать компактный тайлсет из TTF.

    libtcod рендерит TTF в ``tile_width`` так, что глиф занимает примерно
    половину клетки — отсюда огромные промежутки между буквами. Поэтому мы
    рендерим шрифт в 2x и вырезаем центральную часть каждого глифа.
    """
    big = tcod.tileset.load_truetype_font(TTF_PATH, tile_w * 2, tile_h * 2)
    tileset = tcod.tileset.Tileset(tile_w, tile_h)
    crop_x = (tile_w * 2 - tile_w) // 2
    crop_y = (tile_h * 2 - tile_h) // 2
    yy, xx = np.indices((tile_h, tile_w))

    for codepoint, tile in big.items():
        if codepoint not in _USED_CODEPOINTS:
            continue
        if codepoint == 0x2588:  # █ — сплошной блок для HP-бара
            glyph = np.zeros((tile_h, tile_w, 4), dtype=np.uint8)
            glyph[:, :, :3] = 255
            glyph[:, :, 3] = 255
        elif codepoint == 0x2591:  # ░ — лёгкая штриховка
            glyph = np.zeros((tile_h, tile_w, 4), dtype=np.uint8)
            glyph[:, :, :3] = 255
            glyph[:, :, 3] = np.where(
                (xx % 2 == 0) & (yy % 2 == 0), 255, 0
            ).astype(np.uint8)
        elif codepoint == 0x2592:  # ▒ — средняя штриховка
            glyph = np.zeros((tile_h, tile_w, 4), dtype=np.uint8)
            glyph[:, :, :3] = 255
            glyph[:, :, 3] = np.where((xx + yy) % 2 == 0, 255, 0).astype(
                np.uint8
            )
        else:
            glyph = tile[
                crop_y : crop_y + tile_h, crop_x : crop_x + tile_w
            ].copy()
        tileset[codepoint] = glyph
    return tileset


def load_tileset(tile_w: int = TILE_W, tile_h: int = TILE_H) -> tcod.tileset.Tileset:
    """Сначала пробуем TTF (он заметно чётче), иначе откатываемся на PNG."""
    tile_w = max(_MIN_TILE_W, int(tile_w))
    tile_h = max(_MIN_TILE_H, int(tile_h))
    if TTF_PATH.exists():
        try:
            return _tight_ttf_tileset(tile_w, tile_h)
        except Exception as exc:  # pragma: no cover - зависит от сборки SDL
            print(f"Could not load TTF font ({exc}); falling back to tilesheet.")
    if not TILESET_PATH.exists():
        raise FileNotFoundError(f"Font not found: {TTF_PATH} or {TILESET_PATH}")
    return tcod.tileset.load_tilesheet(TILESET_PATH, 32, 8, tcod.tileset.CHARMAP_TCOD)


def _output_size(context: tcod.context.Context) -> tuple[int, int]:
    """Размер окна в физических пикселях (на Retina он вдвое больше)."""
    try:
        width = tcod.ffi.new("int*")
        height = tcod.ffi.new("int*")
        tcod.lib.SDL_GetRenderOutputSize(context.sdl_renderer.p, width, height)
        return max(1, width[0]), max(1, height[0])
    except Exception:  # pragma: no cover - зависит от платформы
        return SCREEN_W * TILE_W, SCREEN_H * TILE_H


def _fitted_tile_size(context: tcod.context.Context) -> tuple[int, int]:
    """Подобрать клетку так, чтобы консоль занимала окно почти 1:1.

    Дробное масштабирование заполняет окно по высоте, а смена тайлсета под
    размер окна не даёт SDL растягивать шрифт и делать его мыльным.
    """
    out_w, out_h = _output_size(context)
    scale = min(
        out_w / (SCREEN_W * TILE_W),
        out_h / (SCREEN_H * TILE_H),
    )
    scale = max(1.0, min(scale, _MAX_SCALE))
    tile_w = min(
        round(TILE_W * _MAX_SCALE),
        max(_MIN_TILE_W, round(TILE_W * scale)),
    )
    tile_h = min(
        round(TILE_H * _MAX_SCALE),
        max(_MIN_TILE_H, round(TILE_H * scale)),
    )
    return tile_w, tile_h


def _shifted(event: tcod.event.KeyDown) -> bool:
    mod = event.mod
    modifier = getattr(tcod.event, "Modifier", None)
    if modifier is not None:
        return bool(mod & modifier.SHIFT)
    return bool(mod & getattr(tcod.event, "KMOD_SHIFT", 0x0001))


def _letter(event: tcod.event.KeyDown) -> str | None:
    try:
        value = int(event.sym)
    except (TypeError, ValueError):
        return None
    if ord("a") <= value <= ord("z"):
        return chr(value)
    if ord("A") <= value <= ord("Z"):
        return chr(value + 32)
    return None


def handle_key(game: Game, event: tcod.event.KeyDown) -> bool:
    """Обработать клавишу. True — закрыть окно."""
    if game.mode == "dead":
        if event.sym == KeySym.R:
            game.restart()
            return False
        return True
    if game.mode == "help":
        game.mode = "playing"
        return False
    if game.mode == "inventory":
        return _handle_inventory(game, event)
    if game.mode == "trash":
        return _handle_trash(game, event)

    sym = event.sym
    if sym in (KeySym.Q,):
        game.finish(quit_requested=True)
        return False
    if sym in (KeySym.SLASH,) and _shifted(event):
        game.toggle_help()
        return False
    if sym in (KeySym.QUESTION, KeySym.F1):
        game.toggle_help()
        return False
    if sym == KeySym.I:
        game.toggle_inventory()
        return False
    if sym == KeySym.X:
        game.open_trash()
        return False
    if sym in MOVE_KEYS:
        dx, dy = MOVE_KEYS[sym]
        game.move(dx, dy)
        return False
    if sym in (KeySym.PERIOD, KeySym.KP_PERIOD) and not _shifted(event):
        game.wait()
        return False
    if sym == KeySym.SPACE:
        game.wait()
        return False
    if sym in (KeySym.GREATER, KeySym.RETURN, KeySym.KP_ENTER) or (
        sym in (KeySym.PERIOD, KeySym.COMMA) and _shifted(event)
    ):
        game.descend()
        return False
    if sym == KeySym.PAGEUP:
        game.log.scroll(LOG_H - 1)
        return False
    if sym in (KeySym.MINUS, KeySym.KP_MINUS):
        game.log.scroll(1)
        return False
    if sym == KeySym.PAGEDOWN:
        game.log.scroll(-(LOG_H - 1))
        return False
    if sym in (KeySym.EQUALS, KeySym.KP_PLUS, KeySym.PLUS):
        game.log.scroll(-1)
        return False
    return False


def _handle_inventory(game: Game, event: tcod.event.KeyDown) -> bool:
    sym = event.sym
    if sym == KeySym.ESCAPE:
        if game.discard_mode:
            game.discard_mode = False
        else:
            game.mode = "playing"
        return False
    if game.discard_mode:
        letter = _letter(event)
        if letter:
            idx = game.inventory.letter_index(letter)
            if idx is None:
                game.msg("No item in that slot.")
                return False
            game.discard_item(idx)
        return False
    if sym in (KeySym.DELETE, KeySym.BACKSPACE):
        game.discard_mode = True
        return False
    letter = _letter(event)
    if letter:
        idx = game.inventory.letter_index(letter)
        if idx is None:
            game.msg("No item in that slot.")
            return False
        if game.use_inventory(idx) and game.mode == "inventory":
            game.discard_mode = False
            game.mode = "playing"
    return False


def _handle_trash(game: Game, event: tcod.event.KeyDown) -> bool:
    sym = event.sym
    if sym in (KeySym.ESCAPE, KeySym.X):
        game.mode = "playing"
        return False
    letter = _letter(event)
    if letter:
        idx = ord(letter) - ord("a")
        if idx < len(game.trash_items):
            game.take_from_trash(idx)
        else:
            game.msg("No item in that slot.")
    return False


def main() -> None:
    tileset = load_tileset()
    with tcod.context.new(
        columns=SCREEN_W,
        rows=SCREEN_H,
        width=SCREEN_W * TILE_W,
        height=SCREEN_H * TILE_H,
        tileset=tileset,
        title="Castle of Shadows",
        vsync=True,
        sdl_window_flags=(
            tcod.context.SDL_WINDOW_RESIZABLE
            | tcod.context.SDL_WINDOW_ALLOW_HIGHDPI
        ),
    ) as context:
        console = tcod.console.Console(SCREEN_W, SCREEN_H, order="F")
        game = Game()
        needs_fit = True
        settling = False

        while True:
            # Подгоняем шрифт под окно, но не во время перетаскивания:
            # сначала ждём, пока пользователь отпустит край окна.
            if needs_fit and not settling:
                tile_w, tile_h = _fitted_tile_size(context)
                if (tile_w, tile_h) != (
                    tileset.tile_width,
                    tileset.tile_height,
                ):
                    try:
                        tileset = load_tileset(tile_w, tile_h)
                        context.change_tileset(tileset)
                    except Exception as exc:  # pragma: no cover
                        print(f"Could not resize font: {exc}")
                needs_fit = False

            render(console, game)
            # keep_aspect убирает искажения, а integer_scaling=False позволяет
            # заполнить окно дробно — поля остаются только по бокам.
            context.present(
                console, keep_aspect=True, integer_scaling=False
            )

            events = list(
                tcod.event.wait(
                    RESIZE_SETTLE_SECONDS if settling else None
                )
            )
            resized = False
            for event in events:
                if isinstance(event, tcod.event.WindowResized):
                    resized = True
                    settling = True
                    continue
                if isinstance(event, tcod.event.Quit):
                    raise SystemExit()
                if isinstance(event, tcod.event.KeyDown):
                    if handle_key(game, event):
                        raise SystemExit()
            if settling and not resized:
                settling = False
                needs_fit = True


if __name__ == "__main__":
    main()
