#!/usr/bin/env python3
"""Castle of Shadows — tcod entry point."""
from __future__ import annotations

import time
import types

import numpy as np
import tcod
import tcod.context
import tcod.console
import tcod.event
from tcod.event import KeySym

from constants import (
    KEY_REPEAT_DELAY,
    KEY_REPEAT_INTERVAL,
    LOG_H,
    MAP_VIEW_H,
    MODE_AIM,
    MODE_CHEST,
    MODE_MAP,
    MODE_MENU,
    MODE_PAUSE,
    MODE_PLAYING,
    MODE_RUN_MODES,
    MODE_SHOP,
    MODE_SLOTS,
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

# Прицел: те же кардинальные клавиши плюс диагонали y/u/b/n.
AIM_KEYS = dict(MOVE_KEYS)
AIM_KEYS.update(
    {
        KeySym.Y: (-1, -1),
        KeySym.U: (1, -1),
        KeySym.B: (-1, 1),
        KeySym.N: (1, 1),
    }
)


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


LOG_SCROLL_KEYS = {
    KeySym.PAGEUP,
    KeySym.PAGEDOWN,
    KeySym.MINUS,
    KeySym.KP_MINUS,
    KeySym.EQUALS,
    KeySym.KP_PLUS,
    KeySym.PLUS,
}

REPEATABLE_KEYS = (
    set(AIM_KEYS)
    | LOG_SCROLL_KEYS
    | {KeySym.PERIOD, KeySym.KP_PERIOD, KeySym.SPACE}
)


class KeyRepeat:
    """Собственный автоповтор клавиш.

    ОС присылает повторные KeyDown с разной задержкой и частотой. Здесь
    первый повтор задаётся ``delay``, дальнейшие — ``interval``. Это же
    состояние пригодится для будущего ticking-режима.
    """

    def __init__(
        self,
        delay: float = KEY_REPEAT_DELAY,
        interval: float = KEY_REPEAT_INTERVAL,
    ) -> None:
        self.delay = delay
        self.interval = interval
        self._held: dict[KeySym, int] = {}
        self._modes: dict[KeySym, str] = {}
        self._blocked: set[KeySym] = set()
        self._seq = 0
        self.active: KeySym | None = None
        self.next_at: float | None = None

    def press(self, sym: KeySym, now: float, mode: str) -> bool:
        """Запомнить нажатие. False — это повтор самой ОС, его игнорируем."""
        if sym in self._held:
            return False
        self._seq += 1
        self._held[sym] = self._seq
        self._modes[sym] = mode
        self._blocked.discard(sym)
        self.active = sym
        self.next_at = now + self.delay
        return True

    def release(self, sym: KeySym, now: float) -> None:
        self._held.pop(sym, None)
        self._modes.pop(sym, None)
        self._blocked.discard(sym)
        if self.active != sym:
            return
        ready = [
            held
            for held in self._held
            if held not in self._blocked
        ]
        if ready:
            self.active = max(
                ready,
                key=lambda held: self._held[held],
            )
            self.next_at = now + self.interval
        else:
            self.active = None
            self.next_at = None

    def mode_of(self, sym: KeySym) -> str | None:
        return self._modes.get(sym)

    def interrupt(self, sym: KeySym | None = None) -> None:
        """Остановить повтор до отпускания клавиши (например, после атаки)."""
        if sym is None:
            sym = self.active
        if sym is None:
            return
        self._blocked.add(sym)
        if self.active == sym:
            self.next_at = None

    def is_blocked(self, sym: KeySym | None) -> bool:
        return sym is not None and sym in self._blocked

    def due(self, now: float) -> bool:
        return self.next_at is not None and now >= self.next_at

    def fire(self, now: float) -> None:
        if self.next_at is None:
            return
        self.next_at += self.interval
        if self.next_at < now:
            # После лага не выдаём пачку повторов разом.
            self.next_at = now + self.interval

    def timeout(self, now: float) -> float | None:
        if self.next_at is None:
            return None
        return max(0.0, self.next_at - now)

    def suspend(self) -> None:
        """Не повторять действие, пока режим его не разрешает."""
        self.next_at = None

    def resume(self, now: float) -> None:
        """Снова включить автоповтор после смены режима."""
        if (
            self.active is not None
            and self.next_at is None
            and self.active not in self._blocked
        ):
            self.next_at = now + self.interval


def _dispatch_key(
    game: Game,
    event: tcod.event.KeyDown,
    repeat: KeyRepeat,
) -> bool:
    """Обработать клавишу и прервать автоповтор после атаки игрока."""
    attacks_before = game.player_attack_events
    result = handle_key(game, event)
    if (
        game.player_attack_events != attacks_before
        and repeat.active is not None
        and not repeat.is_blocked(repeat.active)
    ):
        repeat.interrupt(repeat.active)
    return result


def _repeatable_action(game: Game, sym: KeySym) -> bool:
    """Разрешён ли автоповтор этой клавиши в текущем режиме."""
    if sym not in REPEATABLE_KEYS:
        return False
    if game.mode == MODE_AIM:
        return sym in AIM_KEYS
    if game.mode == MODE_PLAYING:
        return True
    if game.mode == MODE_MAP:
        return sym in MOVE_KEYS or sym in (
            KeySym.PAGEUP,
            KeySym.PAGEDOWN,
        )
    if game.mode in (MODE_MENU, MODE_SLOTS, MODE_PAUSE, MODE_RUN_MODES):
        return sym in (
            KeySym.UP,
            KeySym.DOWN,
            KeySym.W,
            KeySym.S,
            KeySym.K,
            KeySym.J,
        )
    if game.mode == MODE_SHOP:
        return (
            not game.shop_sell_mode
            and sym in (
                KeySym.UP,
                KeySym.DOWN,
                KeySym.W,
                KeySym.S,
                KeySym.K,
                KeySym.J,
            )
        )
    return False


def _repeat_event(sym: KeySym) -> types.SimpleNamespace:
    return types.SimpleNamespace(sym=sym, mod=0)


def handle_key(game: Game, event: tcod.event.KeyDown) -> bool:
    """Обработать клавишу. True — закрыть окно."""
    if game.mode == MODE_MENU:
        return _handle_menu(game, event)
    if game.mode == MODE_SLOTS:
        return _handle_slots(game, event)
    if game.mode == MODE_RUN_MODES:
        return _handle_run_modes(game, event)
    if game.mode == MODE_MAP:
        return _handle_map(game, event)
    if game.mode == MODE_PAUSE:
        return _handle_pause(game, event)
    if game.mode == "dead":
        if event.sym == KeySym.R:
            game.restart()
            return False
        if event.sym == KeySym.ESCAPE:
            game.mode = MODE_MENU
            game.menu_index = 0
            return False
        return True
    if game.mode == "help":
        game.close_help()
        return False
    if game.mode == "inventory":
        return _handle_inventory(game, event)
    if game.mode == "trash":
        return _handle_trash(game, event)
    if game.mode == MODE_CHEST:
        return _handle_chest(game, event)
    if game.mode == MODE_SHOP:
        return _handle_shop(game, event)
    if game.mode == MODE_AIM:
        return _handle_aim(game, event)

    sym = event.sym
    if sym == KeySym.ESCAPE:
        game.open_pause()
        return False
    if sym in (KeySym.SLASH,) and _shifted(event):
        game.toggle_help()
        return False
    if sym in (KeySym.QUESTION, KeySym.F1):
        game.toggle_help()
        return False
    if sym == KeySym.TAB:
        game.toggle_inventory()
        return False
    if sym == KeySym.I:
        game.interact()
        return False
    if sym == KeySym.F:
        game.start_aim()
        return False
    if sym == KeySym.X:
        game.search()
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


def _handle_map(game: Game, event: tcod.event.KeyDown) -> bool:
    sym = event.sym
    if sym in (KeySym.ESCAPE, KeySym.TAB, KeySym.I):
        game.close_map()
        return False
    if sym in MOVE_KEYS:
        dx, dy = MOVE_KEYS[sym]
        game.scroll_map(dx, dy)
        return False
    if sym == KeySym.PAGEUP:
        game.scroll_map(0, -(MAP_VIEW_H // 2))
        return False
    if sym == KeySym.PAGEDOWN:
        game.scroll_map(0, MAP_VIEW_H // 2)
        return False
    if sym in (KeySym.HOME, KeySym.C):
        game.center_map()
    return False


def _handle_aim(game: Game, event: tcod.event.KeyDown) -> bool:
    """Режим прицела: направление, выстрел и отмена."""
    sym = event.sym
    if sym in (KeySym.ESCAPE, KeySym.TAB, KeySym.I):
        game.cancel_aim()
        return False
    if sym in (KeySym.RETURN, KeySym.KP_ENTER, KeySym.SPACE, KeySym.F):
        game.fire_aimed()
        return False
    if sym in AIM_KEYS:
        dx, dy = AIM_KEYS[sym]
        game.set_aim(dx, dy)
        return False
    return False


def _handle_menu(game: Game, event: tcod.event.KeyDown) -> bool:
    sym = event.sym
    options = game.menu_options()
    count = len(options)
    game.menu_index %= count
    if sym in (KeySym.UP, KeySym.W, KeySym.K):
        game.menu_index = (game.menu_index - 1) % count
        return False
    if sym in (KeySym.DOWN, KeySym.S, KeySym.J):
        game.menu_index = (game.menu_index + 1) % count
        return False
    if sym in (KeySym.QUESTION, KeySym.F1):
        game.toggle_help()
        return False
    if sym in (KeySym.RETURN, KeySym.KP_ENTER, KeySym.SPACE):
        choice = options[game.menu_index]
        if choice == "Continue":
            if not game.open_slots("continue"):
                game.menu_index = 0
        elif choice == "New Game":
            game.open_run_modes()
        elif choice == "How to Play":
            game.toggle_help()
        else:
            return True
        return False
    if sym in (KeySym.Q, KeySym.ESCAPE):
        return True
    return False


def _handle_run_modes(game: Game, event: tcod.event.KeyDown) -> bool:
    sym = event.sym
    if sym in (KeySym.ESCAPE, KeySym.Q):
        game.close_run_modes()
        return False
    if sym in (KeySym.UP, KeySym.W, KeySym.K):
        game.run_mode_move(-1)
        return False
    if sym in (KeySym.DOWN, KeySym.S, KeySym.J):
        game.run_mode_move(1)
        return False
    if sym in (KeySym.RETURN, KeySym.KP_ENTER, KeySym.SPACE):
        game.run_mode_activate()
        return False
    return False


def _handle_slots(game: Game, event: tcod.event.KeyDown) -> bool:
    sym = event.sym
    if sym in (KeySym.ESCAPE, KeySym.Q):
        game.close_slots()
        return False
    if sym in (KeySym.UP, KeySym.W, KeySym.K):
        game.slot_move(-1)
        return False
    if sym in (KeySym.DOWN, KeySym.S, KeySym.J):
        game.slot_move(1)
        return False
    if sym in (KeySym.RETURN, KeySym.KP_ENTER, KeySym.SPACE):
        game.slot_activate()
        return False
    if sym in (KeySym.DELETE, KeySym.BACKSPACE):
        game.slot_delete()
        return False
    return False


def _handle_pause(game: Game, event: tcod.event.KeyDown) -> bool:
    sym = event.sym
    options = game.pause_options()
    count = len(options)
    game.pause_index %= count
    if sym in (KeySym.UP, KeySym.W, KeySym.K):
        game.pause_index = (game.pause_index - 1) % count
        return False
    if sym in (KeySym.DOWN, KeySym.S, KeySym.J):
        game.pause_index = (game.pause_index + 1) % count
        return False
    if sym in (KeySym.ESCAPE,):
        game.close_pause()
        return False
    if sym in (KeySym.RETURN, KeySym.KP_ENTER, KeySym.SPACE):
        choice = options[game.pause_index]
        if choice == "Resume":
            game.close_pause()
        elif choice.startswith("Save & Quit to main"):
            game.return_to_menu()
        elif choice.startswith("Quit to main"):
            game.quit_to_menu()
        elif choice.startswith("Save & Quit to Desktop"):
            game.save()
            return True
        else:
            return True
        return False
    if sym == KeySym.Q:
        game.return_to_menu()
        return False
    return False


def _handle_inventory(game: Game, event: tcod.event.KeyDown) -> bool:
    sym = event.sym
    if sym in (KeySym.ESCAPE, KeySym.TAB):
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


def _handle_trash(game: Game, event: tcod.event.KeyDown) -> bool:
    sym = event.sym
    if sym in (KeySym.ESCAPE, KeySym.TAB, KeySym.I):
        if game.trash_deposit_mode:
            game.trash_deposit_mode = False
        else:
            game.close_trash()
        return False
    if game.trash_deposit_mode:
        letter = _letter(event)
        if letter:
            idx = game.inventory.letter_index(letter)
            if idx is None:
                game.msg("No item in that slot.")
                return False
            game.put_in_trash(idx)
        return False
    if sym in (KeySym.DELETE, KeySym.BACKSPACE):
        game.trash_deposit_mode = True
        return False
    letter = _letter(event)
    if letter:
        idx = ord(letter) - ord("a")
        if idx < len(game.trash_items):
            game.take_from_trash(idx)
        else:
            game.msg("No item in that slot.")
    return False


def _handle_chest(game: Game, event: tcod.event.KeyDown) -> bool:
    sym = event.sym
    if sym in (KeySym.ESCAPE, KeySym.TAB, KeySym.I):
        if game.chest_deposit_mode:
            game.chest_deposit_mode = False
        else:
            game.close_chest()
        return False
    if game.chest_deposit_mode:
        letter = _letter(event)
        if letter:
            idx = game.inventory.letter_index(letter)
            if idx is None:
                game.msg("No item in that slot.")
                return False
            game.put_in_chest(idx)
        return False
    if sym in (KeySym.DELETE, KeySym.BACKSPACE):
        game.chest_deposit_mode = True
        return False
    letter = _letter(event)
    if letter:
        chest = game.active_chest
        idx = ord(letter) - ord("a")
        if chest is not None and idx < len(chest.items):
            game.take_from_chest(idx)
        else:
            game.msg("No item in that slot.")
    return False


def _handle_shop(game: Game, event: tcod.event.KeyDown) -> bool:
    sym = event.sym
    if game.shop_sell_mode:
        if sym in (KeySym.ESCAPE, KeySym.TAB, KeySym.I):
            game.shop_sell_mode = False
            return False
        letter = _letter(event)
        if letter:
            idx = game.inventory.letter_index(letter)
            if idx is None:
                game.msg("No item in that slot.")
                return False
            game.shop_sell_item(idx)
        return False
    if sym in (KeySym.ESCAPE, KeySym.TAB, KeySym.I):
        game.close_shop()
        return False
    if sym in (KeySym.UP, KeySym.W, KeySym.K):
        game.shop_move(-1)
        return False
    if sym in (KeySym.DOWN, KeySym.S, KeySym.J):
        game.shop_move(1)
        return False
    if sym in (KeySym.RETURN, KeySym.KP_ENTER, KeySym.SPACE):
        game.shop_buy(game.shop_index)
        return False
    if sym == KeySym.R:
        game.shop_repair_all()
        return False
    letter = _letter(event)
    if letter:
        idx = ord(letter) - ord("a")
        if idx < len(game.merchant_stock):
            game.shop_index = idx
            game.shop_buy(idx)
        else:
            game.msg("No item in that slot.")
        return False
    if sym in (KeySym.DELETE, KeySym.BACKSPACE):
        game.shop_sell_mode = True
        return False
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
        game = Game(build_level=False)
        needs_fit = True
        settling = False
        repeat = KeyRepeat()

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

            now = time.monotonic()
            active = repeat.active
            if active is not None and (
                repeat.mode_of(active) != game.mode
                or not _repeatable_action(game, active)
            ):
                repeat.suspend()
            timeout = repeat.timeout(now)
            if settling:
                timeout = (
                    RESIZE_SETTLE_SECONDS
                    if timeout is None
                    else min(timeout, RESIZE_SETTLE_SECONDS)
                )
            events = list(tcod.event.wait(timeout))
            now = time.monotonic()
            resized = False
            for event in events:
                if isinstance(event, tcod.event.WindowResized):
                    resized = True
                    settling = True
                    continue
                if isinstance(event, tcod.event.Quit):
                    raise SystemExit()
                if isinstance(event, tcod.event.KeyDown):
                    # Повторы ОС игнорируем: у нас своя задержка. Это
                    # касается и неавтоповторяемых клавиш вроде f или i.
                    if not repeat.press(event.sym, now, game.mode):
                        continue
                    if _dispatch_key(game, event, repeat):
                        raise SystemExit()
                elif isinstance(event, tcod.event.KeyUp):
                    repeat.release(event.sym, now)
            if settling and not resized:
                settling = False
                needs_fit = True

            active = repeat.active
            if (
                active is not None
                and repeat.mode_of(active) == game.mode
                and not repeat.is_blocked(active)
                and _repeatable_action(game, active)
            ):
                if repeat.next_at is None:
                    repeat.resume(now)
                if repeat.due(now):
                    if _dispatch_key(game, _repeat_event(active), repeat):
                        raise SystemExit()
                    repeat.fire(now)


if __name__ == "__main__":
    main()
