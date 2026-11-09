"""Отрисовка карты, панелей, инвентаря, help и экрана смерти."""
from __future__ import annotations

import math
from datetime import datetime

import tcod.console

from constants import (
    CHEST_CAPACITY,
    CHEST_CHAR,
    BIOME_COLORS,
    BIOME_NAMES,
    biome_index,
    COLOR_BG,
    COLOR_CAMP_FLOOR,
    COLOR_CHEST,
    COLOR_CHEST_GUARDED,
    COLOR_DIM,
    COLOR_GOLD,
    COLOR_GUARDED_FLOOR,
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
    COLOR_VAULT_FLOOR,
    COLOR_WARN,
    COLOR_XP,
    FOV_RADIUS,
    HINT_Y,
    LOG_H,
    LOG_Y,
    MAX_DEPTH,
    MODE_CHEST,
    MODE_MENU,
    MODE_PAUSE,
    MODE_SLOTS,
    SCREEN_H,
    SCREEN_W,
    STATUS_Y,
    TRASH_CAPACITY,
    TRASH_CHAR,
    VIEW_H,
    VIEW_W,
)
from game import MSG_COLORS, Game

HELP_ROWS = [
    ("Move", "WASD / arrows / hjkl"),
    ("Attack", "bump into an enemy"),
    ("Wait", ". or Space"),
    ("Pick up", "walk over an item (gold auto)"),
    ("Inventory", "Tab, then a-z to use / equip"),
    ("Interact", "i: chest / trash nearby"),
    ("Throw away", "in trash menu: Del, then a-z"),
    ("Trash", "stand next to '%' and press i"),
    ("Chests", "i near '=': a-z take, Del put"),
    ("Vaults", "gold/red rooms hide chests and guards"),
    ("Descend", "stand on '>' and press > or Enter"),
    ("Map", "floors are larger than the screen"),
    ("Camera", "follows you; stairs lie far away"),
    ("Log", "PgUp / PgDn, or - / ="),
    ("Help", "?"),
    ("Pause", "Esc: menu and desktop options"),
    ("Quick quit", "Q in pause: save & menu"),
    ("Saves", "5 slots; Continue in the menu"),
    ("Restart", "R (on the death screen)"),
    ("", ""),
    ("Health", "slow regen; floors/levels heal partly"),
    ("Potions", "heal, antidote, strength, iron skin"),
    ("Scrolls", "teleport, mapping, fire, healing, lightning"),
    ("Gear", "weapons/armor lose durability when used"),
    ("Poison", "P<n> in status; antidote cures it"),
    ("Foes", "bats strike twice, skeletons shoot arrows"),
    ("", "spiders poison, cultists summon minions"),
    ("Goal", f"descend {MAX_DEPTH} floors and escape"),
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
    if game.mode == MODE_MENU:
        _render_menu(console, game)
        return
    if game.mode == MODE_SLOTS:
        _render_slots(console, game)
        return
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
    elif game.mode == MODE_CHEST:
        _render_chest(console, game)
    elif game.mode == MODE_PAUSE:
        _render_pause(console, game)


def _special_floor_color(kind: str | None) -> tuple[int, int, int] | None:
    if kind == "vault":
        return COLOR_VAULT_FLOOR
    if kind == "guarded":
        return COLOR_GUARDED_FLOOR
    if kind == "camp":
        return COLOR_CAMP_FLOOR
    return None


def _render_map(console: tcod.console.Console, game: Game) -> None:
    grid = game.dungeon.grid
    left, top = game.camera()
    wall_color, floor_color = BIOME_COLORS[biome_index(game.depth)]
    for sy in range(VIEW_H):
        wy = top + sy
        if not 0 <= wy < game.dungeon.h:
            continue
        row = grid[wy]
        for sx in range(VIEW_W):
            wx = left + sx
            if not 0 <= wx < game.dungeon.w:
                continue
            ch = row[wx]
            visible = game.is_visible(wx, wy)
            explored = game.is_explored(wx, wy)
            if not visible and not explored:
                continue
            special = _special_floor_color(game.special_room_at(wx, wy))
            if visible:
                light = _light(game, wx, wy)
                if ch == "#":
                    fg = _tint(wall_color, light)
                elif ch == ">":
                    fg = _tint(COLOR_STAIRS, 0.75 + light * 0.25)
                elif ch == TRASH_CHAR:
                    fg = _tint(COLOR_TRASH, 0.75 + light * 0.25)
                else:
                    fg = _tint(special or floor_color, light)
                bg = _warm_glow(game, wx, wy)
            else:
                if ch == "#":
                    fg = _tint(wall_color, 0.28)
                elif ch == ">":
                    fg = (40, 90, 55)
                elif ch == TRASH_CHAR:
                    fg = COLOR_TRASH_DARK
                elif special:
                    fg = _tint(special, 0.22)
                else:
                    fg = _tint(floor_color, 0.20)
                bg = COLOR_BG
            _put(console, sx, sy, ch, fg, bg)


def _render_entities(console: tcod.console.Console, game: Game) -> None:
    left, top = game.camera()
    for chest in game.chests:
        if game.is_visible(chest.x, chest.y):
            color = COLOR_CHEST_GUARDED if chest.guarded else COLOR_CHEST
            _put(console, chest.x - left, chest.y - top, CHEST_CHAR, color)
    for item in game.items:
        if game.is_visible(item.x, item.y):
            _put(console, item.x - left, item.y - top, item.char, item.color)
    for enemy in game.enemies:
        if not game.is_visible(enemy.x, enemy.y):
            continue
        ratio = max(0.2, enemy.hp / enemy.max_hp)
        color = _tint(enemy.color, 0.62 + ratio * 0.38)
        _put(console, enemy.x - left, enemy.y - top, enemy.char, color)
    player = game.player
    _put(console, player.x - left, player.y - top, "@", COLOR_PLAYER)


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

    console.draw_rect(
        0, STATUS_Y, SCREEN_W, 1, ord(" "), fg=COLOR_UI, bg=COLOR_PANEL_LIGHT
    )

    def build_segments(bar_width: int) -> list[tuple[str, tuple[int, int, int]]]:
        filled = max(0, min(bar_width, round(ratio * bar_width)))
        result: list[tuple[str, tuple[int, int, int]]] = [
            (" HP ", COLOR_DIM),
            (f"{player.hp:>3}/{player.max_hp:<3}", hp_color),
            ("█" * filled, hp_color),
            ("░" * (bar_width - filled), COLOR_DIM),
            (" LV ", COLOR_DIM),
            (str(game.player_level), COLOR_XP),
            (" XP ", COLOR_DIM),
            (f"{game.player_xp}/{game.xp_next}", COLOR_XP),
            (" ATK ", COLOR_DIM),
            (str(game.total_atk), COLOR_UI),
            (" DEF ", COLOR_DIM),
            (str(game.total_df), COLOR_UI),
            (" $ ", COLOR_DIM),
            (str(game.gold), COLOR_GOLD),
            (" DEP ", COLOR_DIM),
            (f"{game.depth}/{MAX_DEPTH}", COLOR_STAIRS),
        ]
        if game.poison_turns > 0:
            result.extend(
                [
                    (" P", COLOR_WARN),
                    (str(game.poison_turns), COLOR_HP_LOW),
                ]
            )
        return result

    # Если строка не влезает (высокие HP/XP/золото), сначала ужимаем HP-бар,
    # чтобы важные цифры вроде DEP никогда не обрезались.
    bar_width = 10
    segments = build_segments(bar_width)
    while (
        bar_width > 3
        and sum(len(text) for text, _ in segments) > SCREEN_W
    ):
        bar_width -= 1
        segments = build_segments(bar_width)
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
        ("Tab", COLOR_UI),
        (" inv · ", COLOR_DIM),
        ("i", COLOR_UI),
        (" interact · ", COLOR_DIM),
        (">", COLOR_UI),
        (" descend · ", COLOR_DIM),
        ("?", COLOR_UI),
        (" help · ", COLOR_DIM),
        ("Esc", COLOR_UI),
        (" pause", COLOR_DIM),
    ]
    _print_segments(console, 0, HINT_Y, segments, COLOR_PANEL, SCREEN_W)


def _render_inventory(
    console: tcod.console.Console,
    game: Game,
    title: str | None = None,
    hint: str | None = None,
) -> None:
    inventory = game.inventory
    width = VIEW_W
    height = VIEW_H
    x0 = 0
    y0 = 0
    frame_title = (
        title
        if title is not None
        else f" Inventory {len(inventory.items)}/{inventory.capacity} "
    )
    console.draw_frame(
        x0,
        y0,
        width,
        height,
        title=frame_title,
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

    hint_text = (
        hint if hint is not None else "a-z use/equip   Tab/Esc close"
    )
    console.print(
        x0 + 2,
        y0 + height - 2,
        hint_text[: width - 4],
        fg=COLOR_DIM,
        bg=COLOR_PANEL,
    )


def _render_trash(console: tcod.console.Console, game: Game) -> None:
    if game.trash_deposit_mode:
        _render_inventory(
            console,
            game,
            title=" Put into trash "
            f"(pack {len(game.inventory.items)}/{game.inventory.capacity}) ",
            hint="a-z put   ESC cancel",
        )
        return
    width = min(VIEW_W - 4, 50)
    height = min(VIEW_H, TRASH_CAPACITY + 5)
    x0 = max(1, (VIEW_W - width) // 2)
    y0 = max(1, (VIEW_H - height) // 2)
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
        "a-h take   Del put   ESC close"[: width - 4],
        fg=COLOR_DIM,
        bg=COLOR_PANEL,
    )


def _render_chest(console: tcod.console.Console, game: Game) -> None:
    chest = game.active_chest
    if chest is None:
        return
    if game.chest_deposit_mode:
        _render_inventory(
            console,
            game,
            title=" Put into chest "
            f"(pack {len(game.inventory.items)}/{game.inventory.capacity}) ",
            hint="a-z put   ESC cancel",
        )
        return
    width = min(VIEW_W - 4, 50)
    height = min(VIEW_H, max(7, len(chest.items) + 5))
    x0 = max(1, (VIEW_W - width) // 2)
    y0 = max(1, (VIEW_H - height) // 2)
    frame_color = COLOR_CHEST_GUARDED if chest.guarded else COLOR_CHEST
    console.draw_frame(
        x0,
        y0,
        width,
        height,
        title=f" {'Guarded ' if chest.guarded else ''}Chest "
        f"{len(chest.items)}/{CHEST_CAPACITY} ",
        fg=frame_color,
        bg=COLOR_PANEL,
        clear=True,
    )
    if not chest.items:
        console.print(
            x0 + 2, y0 + 2, "(empty)", fg=COLOR_DIM, bg=COLOR_PANEL
        )
    else:
        rows_per_column = height - 6
        columns = 2 if len(chest.items) > rows_per_column else 1
        column_width = (
            (width - 4) // columns - 1 if columns > 1 else width - 4
        )
        for i, item in enumerate(chest.items):
            column = i // rows_per_column
            row = i % rows_per_column
            if column >= columns:
                break
            letter = chr(ord("a") + i)
            fg = COLOR_GOLD if item.kind == "gold" else item.color
            console.print(
                x0 + 2 + column * (column_width + 2),
                y0 + 2 + row,
                f" {letter}) {game.inventory.label(item)}"[:column_width],
                fg=fg,
                bg=COLOR_PANEL,
            )
    console.print(
        x0 + 2,
        y0 + height - 2,
        "a-z take   Del put   ESC close"[: width - 4],
        fg=COLOR_DIM,
        bg=COLOR_PANEL,
    )


def _slot_label(info: dict | None) -> str:
    if info is None:
        return "(empty)"
    try:
        when = datetime.fromtimestamp(info["saved_at"]).strftime("%d.%m %H:%M")
    except (OverflowError, OSError, ValueError):
        when = "--"
    return (
        f"depth {info['depth']:>2}  LV {info['player_level']}  "
        f"{info['turns']} turns  {info['gold']} gold  {when}"
    )


def _render_slots(console: tcod.console.Console, game: Game) -> None:
    console.clear(fg=COLOR_UI, bg=COLOR_BG)
    infos = game.slot_infos()
    width = min(SCREEN_W - 4, 64)
    height = min(SCREEN_H - 2, len(infos) + 8)
    x0 = max(1, (SCREEN_W - width) // 2)
    y0 = max(1, (SCREEN_H - height) // 2)
    title = " Continue " if game.slot_action == "continue" else " New Game "
    console.draw_frame(
        x0,
        y0,
        width,
        height,
        title=title,
        fg=COLOR_GOLD,
        bg=COLOR_BG,
        clear=True,
    )
    subtitle = (
        "Choose a run to continue"
        if game.slot_action == "continue"
        else "Choose a slot for the new run"
    )
    console.print(
        x0 + 2, y0 + 1, subtitle[: width - 4], fg=COLOR_DIM, bg=COLOR_BG
    )
    start_y = y0 + 3
    for i, info in enumerate(infos):
        selected = i == game.slot_index
        marker = ">" if selected else " "
        text = f"{marker} {i + 1}) {_slot_label(info)}"
        fg = COLOR_GOLD if selected else (COLOR_UI if info else COLOR_DIM)
        console.print(x0 + 2, start_y + i, text[: width - 4], fg=fg, bg=COLOR_BG)
    if game.slot_confirm_delete is not None:
        hint = f"Press Del again to delete slot {game.slot_confirm_delete}"
        hint_color = COLOR_WARN
    elif game.slot_confirm_overwrite is not None:
        hint = (
            "Press Enter again to overwrite slot "
            f"{game.slot_confirm_overwrite}"
        )
        hint_color = COLOR_WARN
    elif game.slot_action == "continue":
        hint = "Enter load   Del delete   ESC back"
        hint_color = COLOR_DIM
    else:
        hint = "Enter start   Del delete   ESC back"
        hint_color = COLOR_DIM
    console.print(
        x0 + 2,
        y0 + height - 2,
        hint[: width - 4],
        fg=hint_color,
        bg=COLOR_BG,
    )


def _render_pause(console: tcod.console.Console, game: Game) -> None:
    width = min(VIEW_W - 4, 46)
    height = len(game.pause_options()) * 2 + 6
    x0 = max(1, (VIEW_W - width) // 2)
    y0 = max(1, (VIEW_H - height) // 2)
    console.draw_frame(
        x0,
        y0,
        width,
        height,
        title=" PAUSED ",
        fg=COLOR_GOLD,
        bg=COLOR_PANEL,
        clear=True,
    )
    slot = f"slot {game.slot}" if game.slot is not None else "unsaved"
    console.print(
        x0 + 2,
        y0 + 1,
        f"Depth {game.depth} · {BIOME_NAMES[biome_index(game.depth)]}"
        f"   {slot}"[: width - 4],
        fg=COLOR_DIM,
        bg=COLOR_PANEL,
    )
    start_y = y0 + 3
    for i, label in enumerate(game.pause_options()):
        selected = i == game.pause_index
        text = f"{'>' if selected else ' '} {label}"
        console.print(
            x0 + 2,
            start_y + i * 2,
            text[: width - 4],
            fg=COLOR_GOLD if selected else COLOR_UI,
            bg=COLOR_PANEL,
        )
    console.print(
        x0 + 2,
        y0 + height - 2,
        "W/S select  Enter  Esc  Q save & menu"[: width - 4],
        fg=COLOR_DIM,
        bg=COLOR_PANEL,
    )


def _render_menu(console: tcod.console.Console, game: Game) -> None:
    console.clear(fg=COLOR_UI, bg=COLOR_BG)
    width = min(SCREEN_W - 8, 54)
    height = 15
    x0 = (SCREEN_W - width) // 2
    y0 = max(2, (SCREEN_H - height) // 2)
    console.draw_frame(
        x0,
        y0,
        width,
        height,
        title=" CASTLE OF SHADOWS ",
        fg=COLOR_GOLD,
        bg=COLOR_BG,
        clear=True,
    )
    subtitle = "A roguelike descent into darkness"
    console.print(
        x0 + max(0, (width - len(subtitle)) // 2),
        y0 + 2,
        subtitle,
        fg=COLOR_DIM,
        bg=COLOR_BG,
    )
    start_y = y0 + 5
    for i, label in enumerate(game.menu_options()):
        selected = i == game.menu_index
        text = f"{'>' if selected else ' '} {label}"
        console.print(
            x0 + max(0, (width - len(text)) // 2),
            start_y + i * 2,
            text,
            fg=COLOR_GOLD if selected else COLOR_UI,
            bg=COLOR_BG,
        )
    hint = "W/S or arrows · Enter select · Q quit"
    console.print(
        x0 + max(0, (width - len(hint)) // 2),
        y0 + height - 2,
        hint,
        fg=COLOR_DIM,
        bg=COLOR_BG,
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
