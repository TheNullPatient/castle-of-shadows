#!/usr/bin/env python3
"""Castle of Shadows — tcod entry point."""
from __future__ import annotations

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


def load_tileset(scale: int = 1) -> tcod.tileset.Tileset:
    """Сначала пробуем TTF (он заметно чётче), иначе откатываемся на PNG."""
    if TTF_PATH.exists():
        try:
            return tcod.tileset.load_truetype_font(
                TTF_PATH, TILE_W * scale, TILE_H * scale
            )
        except Exception as exc:  # pragma: no cover - зависит от сборки SDL
            print(f"Could not load TTF font ({exc}); falling back to tilesheet.")
    if not TILESET_PATH.exists():
        raise FileNotFoundError(f"Font not found: {TTF_PATH} or {TILESET_PATH}")
    return tcod.tileset.load_tilesheet(TILESET_PATH, 32, 8, tcod.tileset.CHARMAP_TCOD)


def _retina_scale(context: tcod.context.Context) -> int:
    """2 на Retina-дисплеях, иначе 1. Нужен, чтобы SDL не растягивал кадр."""
    try:
        scale = float(tcod.lib.SDL_GetWindowDisplayScale(context.sdl_window.p))
    except Exception:  # pragma: no cover - зависит от платформы
        return 1
    return 2 if scale >= 1.9 else 1


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
    if sym in (KeySym.ESCAPE, KeySym.I):
        game.mode = "playing"
        return False
    letter = _letter(event)
    if letter:
        idx = game.inventory.letter_index(letter)
        if idx is None:
            game.msg("No item in that slot.")
            return False
        if game.use_inventory(idx) and game.mode == "inventory":
            game.mode = "playing"
    return False


def main() -> None:
    tileset = load_tileset()
    with tcod.context.new(
        columns=SCREEN_W,
        rows=SCREEN_H,
        tileset=tileset,
        title="Castle of Shadows",
        vsync=True,
        sdl_window_flags=(
            tcod.context.SDL_WINDOW_RESIZABLE
            | tcod.context.SDL_WINDOW_ALLOW_HIGHDPI
        ),
    ) as context:
        # На Retina SDL отдаёт кадр в 2x. Поднимаем разрешение тайлсета,
        # иначе SDL растянет 1x-шрифт и он снова станет мыльным.
        scale = _retina_scale(context)
        if scale == 2 and tileset.tile_width == TILE_W:
            try:
                context.change_tileset(load_tileset(scale))
            except Exception as exc:  # pragma: no cover
                print(f"Could not enable high-DPI font: {exc}")
        console = tcod.console.Console(SCREEN_W, SCREEN_H, order="F")
        game = Game()
        while True:
            render(console, game)
            context.present(console, integer_scaling=True)
            for event in tcod.event.wait():
                if isinstance(event, tcod.event.Quit):
                    raise SystemExit()
                if isinstance(event, tcod.event.KeyDown):
                    if handle_key(game, event):
                        raise SystemExit()


if __name__ == "__main__":
    main()
