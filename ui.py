"""Отрисовка карты, панелей, инвентаря, help и экрана смерти."""
from __future__ import annotations

import math

import tcod.console

from constants import (
    COLOR_BG,
    COLOR_DIM,
    COLOR_FLOOR,
    COLOR_FLOOR_DARK,
    COLOR_GOLD,
    COLOR_HP,
    COLOR_HP_LOW,
    COLOR_HP_MID,
    COLOR_HP_OK,
    COLOR_MSG,
    COLOR_PANEL,
    COLOR_PANEL_LIGHT,
    COLOR_PLAYER,
    COLOR_STAIRS,
    COLOR_TRASH,
    COLOR_TRASH_DARK,
    COLOR_UI,
    COLOR_WALL,
    COLOR_WALL_DARK,
    COLOR_WARN,
    COLOR_XP,
    FOV_RADIUS,
    HINT_Y,
    LOG_H,
    LOG_Y,
    MAP_H,
    MAP_W,
    MAX_DEPTH,
    SCREEN_H,
    SCREEN_W,
    STATUS_Y,
    TRASH_CAPACITY,
    TRASH_CHAR,
)
from game import MSG_COLORS, Game

HELP_ROWS = [
    ("Move", "WASD / arrows / hjkl"),
    ("Attack", "bump into an enemy"),
    ("Wait", ". or Space"),
    ("Pick up", "walk over an item (gold auto)"),
    ("Inventory", "i, then a-z to use / equip"),
    ("Throw away", "in inventory: Del, then a-z (at the bin)"),
    ("Trash", "stand on '%' and press Tab"),
    ("Descend", "stand on '>' and press > or Enter"),
    ("Log", "PgUp / PgDn, or - / ="),
    ("Help", "?"),
    ("Quit", "Q"),
    ("Restart", "R (on the death screen)"),
    ("", ""),
    ("Potions", "heal, stack up to 8"),
    ("Scrolls", "teleport, mapping, fire; stack up to 4"),
    ("Gear", "weapons/armor lose durability when used"),
    ("Goal", "descend 10 floors and escape"),
    ("", ""),
    ("", "Press any key to return..."),
]


def _put(console: tcod.console.Console, x: int, y: int, ch: str, fg, bg=COLOR_BG) -> None:
    if ch and 0 <= x < console.width and 0 <= y < console.height:
        console.print(x, y, ch[0], fg=fg, bg=bg)


def _tint(color: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    return tuple(max(0, min(255, int(channel * factor))) for channel in color)  # type: ignore[return-value]


def _light(game: Game, x: int, y: int) -> float:
    """Мягкое затухание света от игрока внутри FOV."""
    distance = math.hypot(x - game.player.x, y - game.player.y)
    return max(0.58, 1.0 - distance / (FOV_RADIUS + 2.0) * 0.42)


def _warm_glow(game: Game, x: int, y: int) -> tuple[int, int, int]:
    """Тёплый ореол вокруг игрока, чтобы карта не была плоской."""
    distance = math.hypot(x - game.player.x, y - game.player.y)
    strength = max(0.0, 1.0 - distance / (FOV_RADIUS * 0.9))
    return int(12 * strength), int(8 * strength), int(3 * strength)


def render(console: tcod.console.Console, game: Game) -> None:
    console.clear()
    if game.mode == "help":
        _render_help(console)
        return
    if game.mode == "dead":
        _render_death(console, game)
        return
    _render_map(console, game)
    _render_entities(console, game)
    _render_status(console, game)
    _render_log(console, game)
    _render_hint(console)
    if game.mode == "inventory":
        _render_inventory(console, game)
    elif game.mode == "trash":
        _render_trash(console, game)


def _render_map(console: tcod.console.Console, game: Game) -> None:
    grid = game.dungeon.grid
    for y in range(MAP_H):
        for x in range(MAP_W):
            ch = grid[y][x]
            visible = game.is_visible(x, y)
            explored = game.is_explored(x, y)
            if not visible and not explored:
                continue
            if visible:
                light = _light(game, x, y)
                if ch == "#":
                    fg = _tint(COLOR_WALL, light)
                elif ch == ">":
                    fg = _tint(COLOR_STAIRS, 0.75 + light * 0.25)
                elif ch == TRASH_CHAR:
                    fg = _tint(COLOR_TRASH, 0.75 + light * 0.25)
                else:
                    fg = _tint(COLOR_FLOOR, light)
                bg = _warm_glow(game, x, y)
            else:
                if ch == "#":
                    fg = COLOR_WALL_DARK
                elif ch == ">":
                    fg = (40, 90, 55)
                elif ch == TRASH_CHAR:
                    fg = COLOR_TRASH_DARK
                else:
                    fg = COLOR_FLOOR_DARK
                bg = COLOR_BG
            _put(console, x, y, ch, fg, bg)


def _render_entities(console: tcod.console.Console, game: Game) -> None:
    for item in game.items:
        if game.is_visible(item.x, item.y):
            _put(console, item.x, item.y, item.char, item.color)
    for enemy in game.enemies:
        if not game.is_visible(enemy.x, enemy.y):
            continue
        ratio = max(0.2, enemy.hp / enemy.max_hp)
        color = _tint(enemy.color, 0.62 + ratio * 0.38)
        _put(console, enemy.x, enemy.y, enemy.char, color)
    player = game.player
    _put(console, player.x, player.y, "@", COLOR_PLAYER)


def _print_segments(
    console: tcod.console.Console,
    x: int,
    y: int,
    segments: list[tuple[str, tuple[int, int, int]]],
    bg: tuple[int, int, int],
    max_width: int = SCREEN_W,
) -> None:
    for text, fg in segments:
        if not text:
            continue
        room = max_width - x
        if room <= 0:
            break
        console.print(x, y, text[:room], fg=fg, bg=bg)
        x += min(len(text), room)


def _render_status(console: tcod.console.Console, game: Game) -> None:
    player = game.player
    ratio = player.hp / player.max_hp
    if ratio <= 0.25:
        hp_color = COLOR_HP_LOW
    elif ratio <= 0.55:
        hp_color = COLOR_HP_MID
    else:
        hp_color = COLOR_HP_OK
    if ratio <= 0.25 and game.turns % 2:
        hp_color = _tint(hp_color, 0.55)

    bar_width = 10
    filled = max(0, min(bar_width, round(ratio * bar_width)))
    console.draw_rect(
        0, STATUS_Y, SCREEN_W, 1, ord(" "), fg=COLOR_UI, bg=COLOR_PANEL_LIGHT
    )
    segments = [
        (" HP ", COLOR_DIM),
        (f"{player.hp:>3}/{player.max_hp:<3}", hp_color),
        ("█" * filled, hp_color),
        ("░" * (bar_width - filled), COLOR_DIM),
        ("  LV ", COLOR_DIM),
        (str(game.player_level), COLOR_XP),
        ("  XP ", COLOR_DIM),
        (f"{game.player_xp}/{game.xp_next}", COLOR_XP),
        ("  ATK ", COLOR_DIM),
        (str(game.total_atk), COLOR_UI),
        ("  DEF ", COLOR_DIM),
        (str(game.total_df), COLOR_UI),
        ("  $ ", COLOR_DIM),
        (str(game.gold), COLOR_GOLD),
        ("  DEP ", COLOR_DIM),
        (f"{game.depth}/{MAX_DEPTH}", COLOR_STAIRS),
    ]
    _print_segments(console, 0, STATUS_Y, segments, COLOR_PANEL_LIGHT, SCREEN_W)


def _render_log(console: tcod.console.Console, game: Game) -> None:
    console.draw_rect(
        0, LOG_Y, SCREEN_W, LOG_H, ord(" "), fg=COLOR_MSG, bg=COLOR_PANEL
    )
    for i, (text, color) in enumerate(game.log.view(LOG_H)):
        fg = MSG_COLORS.get(color, COLOR_MSG)
        console.print(
            0,
            LOG_Y + i,
            text[: SCREEN_W - 1],
            fg=fg,
            bg=COLOR_PANEL,
        )
    if game.log.offset:
        console.print(SCREEN_W - 1, LOG_Y, "▲", fg=COLOR_DIM, bg=COLOR_PANEL)
        console.print(
            SCREEN_W - 1, LOG_Y + LOG_H - 1, "▼", fg=COLOR_DIM, bg=COLOR_PANEL
        )


def _render_hint(console: tcod.console.Console) -> None:
    console.draw_rect(0, HINT_Y, SCREEN_W, 1, ord(" "), fg=COLOR_UI, bg=COLOR_PANEL)
    segments = [
        (" WASD", COLOR_UI),
        (" · ", COLOR_DIM),
        (".", COLOR_UI),
        (" wait · ", COLOR_DIM),
        ("i", COLOR_UI),
        (" inv · ", COLOR_DIM),
        (">", COLOR_UI),
        (" descend · ", COLOR_DIM),
        ("?", COLOR_UI),
        (" help · ", COLOR_DIM),
        ("PgUp/Dn", COLOR_UI),
        (" log · ", COLOR_DIM),
        ("Q", COLOR_UI),
        (" quit", COLOR_DIM),
    ]
    _print_segments(console, 0, HINT_Y, segments, COLOR_PANEL, SCREEN_W)


def _render_inventory(console: tcod.console.Console, game: Game) -> None:
    inventory = game.inventory
    width = MAP_W
    height = MAP_H
    x0 = 0
    y0 = 0
    console.draw_frame(
        x0,
        y0,
        width,
        height,
        title=f" Inventory {len(inventory.items)}/{inventory.capacity} ",
        fg=COLOR_UI,
        bg=COLOR_PANEL,
        clear=True,
    )

    weapon = inventory.equipped_label(inventory.weapon)
    armor = inventory.equipped_label(inventory.armor)
    player = game.player
    console.print(
        x0 + 2,
        y0 + 1,
        f"Weapon: {weapon}"[: width - 4],
        fg=COLOR_UI,
        bg=COLOR_PANEL,
    )
    console.print(
        x0 + 2,
        y0 + 2,
        f"Armor:  {armor}"[: width - 4],
        fg=COLOR_UI,
        bg=COLOR_PANEL,
    )
    console.print(
        x0 + 2,
        y0 + 3,
        f"HP {player.hp}/{player.max_hp}   ATK {game.total_atk}   DEF {game.total_df}"[
            : width - 4
        ],
        fg=COLOR_HP,
        bg=COLOR_PANEL,
    )

    if not inventory.items:
        console.print(
            x0 + 2, y0 + 5, "(empty)", fg=COLOR_DIM, bg=COLOR_PANEL
        )
    else:
        rows_per_column = height - 7
        columns = 2 if len(inventory.items) > rows_per_column else 1
        column_width = (width - 4) // columns - 1 if columns > 1 else width - 4
        for i, item in enumerate(inventory.items):
            column = i // rows_per_column
            row = i % rows_per_column
            if column >= columns:
                break
            letter = chr(ord("a") + i)
            equipped = item is inventory.weapon or item is inventory.armor
            marker = "*" if equipped else " "
            line = f" {letter}) {marker}{inventory.label(item)}"
            fg = COLOR_GOLD if equipped else item.color
            console.print(
                x0 + 2 + column * (column_width + 2),
                y0 + 5 + row,
                line[:column_width],
                fg=fg,
                bg=COLOR_PANEL,
            )

    if game.discard_mode:
        hint = "Throw away: choose a slot a-z   ESC cancel"
    elif game.on_trash():
        hint = "a-z use/equip   Del throw away   Tab look in trash   ESC close"
    else:
        hint = "a-z use/equip   Del throw away (stand on %)   ESC close"
    console.print(
        x0 + 2,
        y0 + height - 2,
        hint[: width - 4],
        fg=COLOR_WARN if game.discard_mode else COLOR_DIM,
        bg=COLOR_PANEL,
    )


def _render_trash(console: tcod.console.Console, game: Game) -> None:
    width = min(MAP_W - 4, 50)
    height = min(MAP_H, TRASH_CAPACITY + 5)
    x0 = max(1, (MAP_W - width) // 2)
    y0 = max(1, (MAP_H - height) // 2)
    console.draw_frame(
        x0,
        y0,
        width,
        height,
        title=f" Trash {len(game.trash_items)}/{TRASH_CAPACITY} ",
        fg=COLOR_TRASH,
        bg=COLOR_PANEL,
        clear=True,
    )
    if not game.trash_items:
        console.print(
            x0 + 2, y0 + 2, "(empty)", fg=COLOR_DIM, bg=COLOR_PANEL
        )
    else:
        for i, item in enumerate(game.trash_items[:TRASH_CAPACITY]):
            letter = chr(ord("a") + i)
            console.print(
                x0 + 2,
                y0 + 2 + i,
                f" {letter}) {game.inventory.label(item)}"[: width - 4],
                fg=item.color,
                bg=COLOR_PANEL,
            )
    console.print(
        x0 + 2,
        y0 + height - 2,
        "a-h take   ESC close"[: width - 4],
        fg=COLOR_DIM,
        bg=COLOR_PANEL,
    )


def _render_help(console: tcod.console.Console) -> None:
    width = min(SCREEN_W - 4, 62)
    height = min(SCREEN_H - 2, len(HELP_ROWS) + 4)
    x0 = max(1, (SCREEN_W - width) // 2)
    y0 = max(1, (SCREEN_H - height) // 2)
    console.clear(fg=COLOR_UI, bg=COLOR_BG)
    console.draw_frame(
        x0,
        y0,
        width,
        height,
        title=" CASTLE OF SHADOWS ",
        fg=COLOR_UI,
        bg=COLOR_BG,
        clear=True,
    )
    for i, (key, description) in enumerate(HELP_ROWS[: height - 2]):
        y = y0 + 1 + i
        if not key and not description:
            continue
        if key:
            console.print(x0 + 2, y, f"{key:<10}", fg=COLOR_GOLD, bg=COLOR_BG)
        console.print(
            x0 + 13,
            y,
            description[: width - 15],
            fg=COLOR_MSG if description else COLOR_DIM,
            bg=COLOR_BG,
        )


def _render_death(console: tcod.console.Console, game: Game) -> None:
    if game.win:
        title = " VICTORY "
        frame_color = COLOR_GOLD
        cause = "You escaped the Castle of Shadows."
    elif game.quit_requested:
        title = " RETREAT "
        frame_color = COLOR_WARN
        cause = "You fled the dungeon."
    else:
        title = " YOU DIED "
        frame_color = COLOR_HP_LOW
        cause = f"Killed by {game.killed_by or 'unknown fate'}."

    stats = [
        ("Depth reached", f"{game.depth}/{MAX_DEPTH}"),
        ("Hero level", str(game.player_level)),
        ("Gold", str(game.gold)),
        ("Kills", str(game.kills)),
        ("Turns", str(game.turns)),
        ("XP", f"{game.player_xp}/{game.xp_next}"),
    ]

    width = min(SCREEN_W - 6, 50)
    height = len(stats) + 8
    x0 = max(1, (SCREEN_W - width) // 2)
    y0 = max(1, (SCREEN_H - height) // 2)

    console.clear(fg=COLOR_UI, bg=COLOR_BG)
    console.draw_frame(
        x0,
        y0,
        width,
        height,
        title=title,
        fg=frame_color,
        bg=COLOR_BG,
        clear=True,
    )
    cause_color = COLOR_GOLD if game.win else (
        COLOR_WARN if game.quit_requested else COLOR_HP_LOW
    )
    console.print(
        x0 + 2,
        y0 + 2,
        cause[: width - 4],
        fg=cause_color,
        bg=COLOR_BG,
    )
    for i, (label, value) in enumerate(stats):
        y = y0 + 4 + i
        console.print(x0 + 3, y, f"{label:<16}", fg=COLOR_DIM, bg=COLOR_BG)
        console.print(
            x0 + width - 3 - len(value),
            y,
            value,
            fg=COLOR_UI,
            bg=COLOR_BG,
        )
    prompt = "R restart  ·  any other key exit"
    console.print(
        max(0, (SCREEN_W - len(prompt)) // 2),
        y0 + height - 2,
        prompt,
        fg=COLOR_DIM,
        bg=COLOR_BG,
    )
