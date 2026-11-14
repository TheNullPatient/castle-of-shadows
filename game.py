"""Состояние игры: ходы, бой, FOV, спуск, статистика."""
from __future__ import annotations

import random

import numpy as np
import tcod.map
import tcod.path
from tcod.constants import FOV_SYMMETRIC_SHADOWCAST

from constants import (
    AGGRO_RANGE,
    ALTAR_HEAL_RATIO,
    ARMOR_WEAR_PER_HIT,
    AUTO_DISPLAY_MODE,
    BIOME_NAMES,
    biome_index,
    BOSS_HEAL_MIN,
    BOSS_HEAL_RATIO,
    CHEST_CAPACITY,
    CHEST_TRAP_BONUS_GUARDED,
    CHEST_TRAP_CHANCE,
    CHEST_TRAP_MAX,
    CHEST_TRAP_PER_DEPTH,
    COLOR_ENEMY,
    COLOR_GOOD,
    COLOR_GOLD,
    COLOR_HP,
    COLOR_ITEM,
    COLOR_MSG,
    COLOR_WARN,
    DEFAULT_DISPLAY_MODE,
    DESCEND_HEAL_MIN,
    DESCEND_HEAL_RATIO,
    DISPLAY_MODE_ORDER,
    DISPLAY_MODES,
    ENEMY_RANGED_RANGE,
    FOV_RADIUS,
    LEVEL_UP_HEAL_MIN,
    LEVEL_UP_HEAL_RATIO,
    LOG_H,
    LOG_HISTORY,
    MAP_H,
    MAP_W,
    MAX_DEPTH,
    MAX_ENEMIES,
    MERCHANT_DEPTH_OFFSET,
    MERCHANT_DEPTH_STEP,
    MODE_AIM,
    MODE_CHEST,
    MODE_DEAD,
    MODE_HELP,
    MODE_INVENTORY,
    MODE_MAP,
    MODE_MENU,
    MODE_PAUSE,
    MODE_PLAYING,
    MODE_RUN_MODES,
    MODE_SETTINGS,
    MODE_SHOP,
    MODE_SLOTS,
    MODE_TRASH,
    POISON_DAMAGE,
    POISON_PER_DEPTH,
    POISON_TURNS,
    PLAYER_RANGED_RANGE,
    REPAIR_COST_DIVISOR,
    RUN_MODE_AVAILABLE,
    RUN_MODE_CLASSIC,
    RUN_MODE_GENERAL,
    RUN_MODE_NAMES,
    RUN_MODE_ORDER,
    RUN_MODE_SHORT,
    SEARCH_RADIUS,
    SECRET_DOOR_CHAR,
    SECRET_ROOM_CHANCE,
    SECRET_ROOM_EXTRA_CHANCE,
    SECRET_ROOM_EXTRA_DEPTH,
    SCREEN_H,
    SCREEN_W,
    SUMMON_COOLDOWN,
    TRAP_BASE_COUNT,
    TRAP_DART_DAMAGE_BASE,
    TRAP_DART_DAMAGE_PER_DEPTH,
    TRAP_MAX,
    TRAP_PER_DEPTH,
    TRAP_POISON_TURNS_BASE,
    TRAP_POISON_TURNS_PER_DEPTH,
    TRAP_SPIKE_DAMAGE_BASE,
    TRAP_SPIKE_DAMAGE_PER_DEPTH,
    TRASH_CAPACITY,
    TRASH_CHAR,
    TRASH_LOOT_CHANCE,
    TRASH_LOOT_MAX,
    VIEW_H,
    VIEW_W,
)
from display import auto_columns
from dungeon import Dungeon
from entities import (
    BOSS_TYPES,
    ENEMY_BY_NAME,
    ENEMY_GEAR_WEAR,
    Chest,
    Entity,
    Item,
    Trap,
    age_trash_gear,
    enemy_pool,
    make_boss,
    make_chest_loot,
    make_enemy,
    make_merchant_stock,
    make_player,
    random_loot,
    shop_price,
)
from inventory import Inventory
from savegame import (
    SLOT_COUNT,
    apply_state,
    build_state,
    delete_save,
    first_free_slot,
    has_any_save,
    latest_slot,
    list_slots,
    read_save,
    write_save,
)

MSG_COLORS = {
    "msg": COLOR_MSG,
    "item": COLOR_ITEM,
    "gold": COLOR_GOLD,
    "enemy": COLOR_ENEMY,
    "warn": COLOR_WARN,
    "heal": COLOR_GOOD,
    "good": COLOR_HP,
}

SPECIAL_ROOM_TEXT = {
    "vault": "You enter a treasure vault. A chest waits in the corner.",
    "guarded": "You enter a guarded vault. Something stirs in the dark.",
    "camp": "You enter an abandoned camp. Leftovers lie scattered around.",
    "shop": "You enter a trading post. A merchant waits by a lantern.",
    "secret": "You discover a hidden chamber.",
    "shrine": "You enter a silent shrine. An altar glows faintly.",
}

DIRECTION_NAMES = {
    (0, -1): "North",
    (1, -1): "North-East",
    (1, 0): "East",
    (1, 1): "South-East",
    (0, 1): "South",
    (-1, 1): "South-West",
    (-1, 0): "West",
    (-1, -1): "North-West",
}


class MessageLog:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []
        self.offset = 0

    def add(self, text: str, color: str = "msg") -> None:
        self.messages.append((text, color))
        if len(self.messages) > LOG_HISTORY:
            self.messages = self.messages[-LOG_HISTORY // 2 :]
        self.offset = 0

    def view(self, height: int = LOG_H) -> list[tuple[str, str]]:
        if not self.messages:
            return []
        max_offset = max(0, len(self.messages) - height)
        self.offset = max(0, min(self.offset, max_offset))
        end = len(self.messages) - self.offset
        start = max(0, end - height)
        return self.messages[start:end]

    def scroll(self, delta: int) -> None:
        if not self.messages:
            return
        max_offset = max(0, len(self.messages) - LOG_H)
        self.offset = max(0, min(max_offset, self.offset + delta))


class Game:
    MENU_OPTIONS = ("New Game", "How to Play", "Settings", "Quit")
    PAUSE_OPTIONS = (
        "Resume",
        "Settings",
        "Save & Quit to main menu",
        "Quit to main menu without saving",
        "Save & Quit to Desktop",
        "Quit to Desktop without saving",
    )

    def __init__(
        self,
        build_level: bool = True,
        run_mode: str = RUN_MODE_GENERAL,
        display_mode: str | None = None,
        auto_width: int | None = None,
    ) -> None:
        self.mode = MODE_MENU
        self.menu_index = 0
        if run_mode not in RUN_MODE_NAMES:
            run_mode = RUN_MODE_GENERAL
        self.run_mode = run_mode
        self.new_run_mode = run_mode
        self.run_mode_index = 0
        self.run_mode_note = ""
        if display_mode not in DISPLAY_MODES:
            display_mode = DEFAULT_DISPLAY_MODE
        self.display_mode = display_mode
        if auto_width and auto_width > 0:
            self.auto_width = auto_width
        elif display_mode == AUTO_DISPLAY_MODE:
            self.auto_width = auto_columns()
        else:
            self.auto_width = int(DISPLAY_MODES[AUTO_DISPLAY_MODE]["width"])
        self.display_changed = False
        self.settings_index = DISPLAY_MODE_ORDER.index(display_mode)
        self.settings_return_mode = MODE_MENU
        self.help_return_mode = MODE_MENU
        self.slot: int | None = None
        self.pause_index = 0
        self.slot_action = "continue"
        self.slot_index = 0
        self.slot_confirm_delete: int | None = None
        self.slot_confirm_overwrite: int | None = None
        self.depth = 1
        self.log = MessageLog()
        self.player: Entity | None = None
        self.inventory = Inventory()
        self.stairs = (0, 0)
        self.game_over = False
        self.win = False
        self.quit_requested = False
        self.player_level = 1
        self.player_xp = 0
        self.xp_next = 15
        self.gold = 0
        self.kills = 0
        self.turns = 0
        # Счётчик атак игрока: main.py по нему останавливает автоповтор.
        self.player_attack_events = 0
        self.killed_by = ""
        self.poison_turns = 0
        self.poison_damage = POISON_DAMAGE
        self.enemies: list[Entity] = []
        self.items: list[Item] = []
        self.trash_pos: tuple[int, int] | None = None
        self.trash_items: list[Item] = []
        self.trash_noticed = False
        self.trash_deposit_mode = False
        self.chests: list[Chest] = []
        self.active_chest: Chest | None = None
        self.chest_deposit_mode = False
        self.chest_hinted = False
        self.inventory_index = 0
        self.inventory_reorder = False
        self.container_index = 0
        self.merchant_pos: tuple[int, int] | None = None
        self.merchant_stock: list[Item] = []
        self.merchant_noticed = False
        self.shop_index = 0
        self.shop_sell_mode = False
        self.shop_sell_index = 0
        self.aim_dx = 1
        self.aim_dy = 0
        self.traps: list[Trap] = []
        self.secret_doors: set[tuple[int, int]] = set()
        self.secret_hinted = False
        self.altar_pos: tuple[int, int] | None = None
        self.altar_used = False
        self.special_rooms: list[tuple[int, int, int, int, str]] = []
        self.special_room_seen: set[tuple[int, int, int, int]] = set()
        self.spawn = (0, 0)
        self.map_left = 0
        self.map_top = 0
        self.skip_turn = False
        self.visible = np.zeros((MAP_W, MAP_H), dtype=bool, order="F")
        self.explored = np.zeros((MAP_W, MAP_H), dtype=bool, order="F")
        self.dungeon: Dungeon
        if build_level:
            self.new_level(first=True)
            self.msg(
                f"Welcome, Hero! Find '>' and descend {MAX_DEPTH} levels."
            )
            self.msg('Press "?" for help. Tab: inventory. i: interact. .: wait.')

    def menu_options(self) -> tuple[str, ...]:
        """Пункты главного меню: Continue появляется только при сейвах."""
        if has_any_save():
            return (
                "Continue",
                "New Game",
                "How to Play",
                "Settings",
                "Quit",
            )
        return self.MENU_OPTIONS

    def open_run_modes(self) -> None:
        """Экран выбора режима перед выбором слота для новой игры."""
        try:
            self.run_mode_index = RUN_MODE_ORDER.index(self.new_run_mode)
        except ValueError:
            self.run_mode_index = 0
        self.run_mode_note = ""
        self.mode = MODE_RUN_MODES

    def close_run_modes(self) -> None:
        if self.mode == MODE_RUN_MODES:
            self.mode = MODE_MENU
            self.menu_index = 0

    def run_mode_move(self, delta: int) -> None:
        self.run_mode_index = (
            self.run_mode_index + delta
        ) % len(RUN_MODE_ORDER)
        self.run_mode_note = ""

    def selected_run_mode(self) -> str:
        return RUN_MODE_ORDER[self.run_mode_index]

    def run_mode_activate(self) -> bool:
        """Выбрать режим и перейти к слотам; закрытые режимы не начинают игру."""
        run_mode = self.selected_run_mode()
        if not RUN_MODE_AVAILABLE.get(run_mode, False):
            name = RUN_MODE_NAMES.get(run_mode, run_mode)
            self.run_mode_note = f"{name} is not available yet."
            return False
        self.new_run_mode = run_mode
        self.run_mode_note = ""
        self.open_slots("new")
        return True

    def run_mode_summary(self) -> str:
        """Название режима текущего забега для слотов и паузы."""
        return RUN_MODE_SHORT.get(self.run_mode, "General")

    # --- Отображение и настройки -----------------------------------------
    def screen_width(self) -> int:
        """Ширина всей консоли в клетках для выбранного режима."""
        if self.display_mode == AUTO_DISPLAY_MODE:
            return max(VIEW_W, int(self.auto_width))
        info = DISPLAY_MODES.get(self.display_mode)
        if info is None:
            return SCREEN_W
        return int(info["width"])

    def screen_height(self) -> int:
        return SCREEN_H

    def view_width(self) -> int:
        """Ширина видимой области карты (совпадает с шириной консоли)."""
        return self.screen_width()

    def view_height(self) -> int:
        return VIEW_H

    def map_view_width(self) -> int:
        return max(1, self.screen_width() - 2)

    def map_view_height(self) -> int:
        return max(1, self.screen_height() - 4)

    def refresh_auto_width(self) -> int:
        """Пересчитать ширину auto под текущий монитор."""
        self.auto_width = auto_columns()
        return self.auto_width

    def display_label(self) -> str:
        if self.display_mode == AUTO_DISPLAY_MODE:
            return f"Auto · {self.screen_width()} cols"
        info = DISPLAY_MODES.get(self.display_mode)
        return info["label"] if info else self.display_mode

    def display_mode_at(self, index: int) -> str:
        return DISPLAY_MODE_ORDER[index % len(DISPLAY_MODE_ORDER)]

    def open_settings(self, return_mode: str | None = None) -> None:
        """Открыть настройки из главного меню или паузы."""
        if return_mode not in (MODE_MENU, MODE_PAUSE):
            return_mode = MODE_MENU
        self.settings_return_mode = return_mode
        self.settings_index = DISPLAY_MODE_ORDER.index(self.display_mode)
        self.mode = MODE_SETTINGS

    def close_settings(self) -> None:
        if self.mode == MODE_SETTINGS:
            self.mode = self.settings_return_mode

    def settings_move(self, delta: int) -> None:
        self.settings_index = (
            self.settings_index + delta
        ) % len(DISPLAY_MODE_ORDER)

    def selected_display_mode(self) -> str:
        return self.display_mode_at(self.settings_index)

    def apply_display_selection(self) -> bool:
        mode = self.selected_display_mode()
        if mode == self.display_mode == AUTO_DISPLAY_MODE:
            previous = self.auto_width
            self.refresh_auto_width()
            if self.auto_width != previous:
                self.display_changed = True
                return True
            return False
        return self.set_display_mode(mode)

    def set_display_mode(self, mode: str) -> bool:
        """Сменить режим отображения; main.py пересоздаст окно и консоль."""
        if mode not in DISPLAY_MODES or mode == self.display_mode:
            return False
        self.display_mode = mode
        if mode == AUTO_DISPLAY_MODE:
            self.refresh_auto_width()
        self.settings_index = DISPLAY_MODE_ORDER.index(mode)
        self.display_changed = True
        return True

    def slot_infos(self) -> list[dict | None]:
        return list_slots()

    def open_slots(self, action: str) -> bool:
        """Открыть список слотов для продолжения или новой игры."""
        infos = list_slots()
        if action == "continue" and not any(infos):
            return False
        self.slot_action = action
        self.slot_confirm_delete = None
        self.slot_confirm_overwrite = None
        self.mode = MODE_SLOTS
        if action == "continue":
            self.slot_index = next(
                (i for i, info in enumerate(infos) if info is not None),
                0,
            )
        else:
            self.slot_index = next(
                (i for i, info in enumerate(infos) if info is None),
                0,
            )
        return True

    def close_slots(self) -> None:
        self.slot_confirm_delete = None
        self.slot_confirm_overwrite = None
        self.mode = MODE_MENU
        self.menu_index = 0

    def slot_move(self, delta: int) -> None:
        self.slot_index = (self.slot_index + delta) % SLOT_COUNT
        self.slot_confirm_delete = None
        self.slot_confirm_overwrite = None

    def slot_activate(self) -> bool:
        """Загрузить слот или начать в нём новую игру."""
        slot = self.slot_index + 1
        info = self.slot_infos()[self.slot_index]
        if self.slot_action == "continue":
            if info is None:
                return False
            return self.continue_game(slot)
        if info is not None and self.slot_confirm_overwrite != slot:
            self.slot_confirm_overwrite = slot
            self.slot_confirm_delete = None
            return False
        self.start_new_game(slot)
        return True

    def slot_delete(self) -> bool:
        """Удалить слот; первый Del только запрашивает подтверждение."""
        slot = self.slot_index + 1
        info = self.slot_infos()[self.slot_index]
        if info is None:
            return False
        if self.slot_confirm_delete != slot:
            self.slot_confirm_delete = slot
            self.slot_confirm_overwrite = None
            return False
        delete_save(slot)
        self.slot_confirm_delete = None
        return True

    def save(self) -> bool:
        """Записать текущий забег в свой слот (или первый свободный)."""
        if self.player is None or self.game_over:
            return False
        slot = self.slot if self.slot is not None else first_free_slot()
        if slot is None:
            self.msg("All save slots are full.", "warn")
            return False
        self.slot = slot
        try:
            write_save(slot, build_state(self))
        except OSError:
            self.msg("Could not save the game.", "warn")
            return False
        return True

    def start_new_game(self, slot: int) -> None:
        """Начать новый забег в выбранном слоте."""
        delete_save(slot)
        run_mode = self.new_run_mode
        display_mode = self.display_mode
        self.__init__(run_mode=run_mode, display_mode=display_mode)
        self.slot = slot
        self.mode = MODE_PLAYING
        self.save()

    def continue_game(self, slot: int | None = None) -> bool:
        """Загрузить сохранённый забег в этот объект Game."""
        if slot is None:
            slot = latest_slot()
        if slot is None:
            return False
        data = read_save(slot)
        if data is None:
            return False
        try:
            apply_state(self, data)
        except (KeyError, TypeError, ValueError, IndexError):
            return False
        self.slot = slot
        self.mode = MODE_PLAYING
        return True

    def open_pause(self) -> None:
        if self.mode == MODE_PLAYING:
            self.pause_index = 0
            self.mode = MODE_PAUSE

    def close_pause(self) -> None:
        if self.mode == MODE_PAUSE:
            self.mode = MODE_PLAYING

    def pause_options(self) -> tuple[str, ...]:
        return self.PAUSE_OPTIONS

    def return_to_menu(self) -> None:
        """Сохранить текущий этаж и вернуться в главное меню."""
        if self.player is not None and not self.game_over:
            self.save()
        self.quit_to_menu()

    def quit_to_menu(self) -> None:
        """Вернуться в главное меню, не записывая текущий этаж."""
        self.mode = MODE_MENU
        self.menu_index = 0
        self.pause_index = 0

    def msg(self, text: str, color: str = "msg") -> None:
        self.log.add(text, color)

    @property
    def total_atk(self) -> int:
        bonus = self.inventory.weapon.value if self.inventory.weapon else 0
        return self.player.atk + bonus

    @property
    def total_df(self) -> int:
        bonus = self.inventory.armor.value if self.inventory.armor else 0
        return self.player.df + bonus

    @property
    def melee_atk(self) -> int:
        """Сила удара вплотную: лук в ближнем бою бонуса не даёт."""
        weapon = self.inventory.weapon
        if weapon is not None and weapon.effect == "ranged":
            return self.player.atk
        return self.total_atk

    @property
    def poison_strength(self) -> int:
        """Яд глубже бьёт больнее, иначе 6 ходов по 1 почти незаметны."""
        return POISON_DAMAGE + self.depth // POISON_PER_DEPTH

    def level_dimensions(self) -> tuple[int, int]:
        """Classic — один экран, general — большой этаж с камерой."""
        if self.run_mode == RUN_MODE_CLASSIC:
            return VIEW_W, VIEW_H
        return MAP_W, MAP_H

    @property
    def allow_ranged_loot(self) -> bool:
        """В classic нет луков: только ближний бой."""
        return self.run_mode != RUN_MODE_CLASSIC

    def new_level(self, first: bool = False) -> None:
        if not first:
            self._expire_maps()
        width, height = self.level_dimensions()
        self.dungeon = Dungeon(width, height)
        r0 = self.dungeon.rooms[0]
        px = r0[0] + r0[2] // 2
        py = r0[1] + r0[3] // 2
        if self.player is None:
            self.player = make_player(px, py)
        else:
            self.player.x, self.player.y = px, py
            if not first:
                self.player.max_hp += 5
                heal = max(
                    DESCEND_HEAL_MIN,
                    int(self.player.max_hp * DESCEND_HEAL_RATIO),
                )
                healed = self._heal_player(heal)
                if healed:
                    self.msg(
                        f"You bind your wounds (+{healed} HP).",
                        "heal",
                    )
        self.spawn = (px, py)

        rl = self.dungeon.rooms[-1]
        self.stairs = (rl[0] + rl[2] // 2, rl[1] + rl[3] // 2)
        self.dungeon.grid[self.stairs[1]][self.stairs[0]] = ">"

        self.enemies = []
        self.items = []
        self.chests = []
        self.active_chest = None
        self.chest_deposit_mode = False
        self.chest_hinted = False
        self.inventory_index = 0
        self.inventory_reorder = False
        self.container_index = 0
        self.merchant_pos = None
        self.merchant_stock = []
        self.merchant_noticed = False
        self.shop_index = 0
        self.shop_sell_mode = False
        self.shop_sell_index = 0
        self.aim_dx = 1
        self.aim_dy = 0
        self.traps = []
        self.secret_doors = set()
        self.secret_hinted = False
        self.altar_pos = None
        self.altar_used = False
        self.special_rooms = []
        self.special_room_seen = set()
        self.trash_items = []
        self.trash_noticed = False
        self.trash_deposit_mode = False
        self.trash_pos = self._place_trash()
        self._prepare_special_rooms()
        self._place_merchant()
        self._spawn_enemies()
        self._spawn_items()
        self._spawn_trash_loot()
        self._spawn_boss()
        self._place_secrets()
        self._place_traps()
        if not first and biome_index(self.depth) != biome_index(self.depth - 1):
            self.msg(
                f"You enter the {BIOME_NAMES[biome_index(self.depth)]}.",
                "good",
            )
        self.explored = np.zeros(
            (self.dungeon.w, self.dungeon.h), dtype=bool, order="F"
        )
        self.update_fov()

    def _place_trash(self) -> tuple[int, int] | None:
        """Поставить мусорку в закрытый угол случайной комнаты.

        Закрытым считается угол, у которого обе внешние ортогональные
        клетки и внешняя диагональ — стены. Угол, к которому примыкает
        коридор или дверной проём, мусоркой не занимаем, иначе она
        оказывается прямо на проходе.
        """
        closed: list[tuple[int, int]] = []
        fallback: list[tuple[int, int]] = []
        for x, y, w, h in self.dungeon.rooms:
            corners = (
                ((x, y), ((-1, 0), (0, -1), (-1, -1))),
                ((x + w - 1, y), ((1, 0), (0, -1), (1, -1))),
                ((x, y + h - 1), ((-1, 0), (0, 1), (-1, 1))),
                (
                    (x + w - 1, y + h - 1),
                    ((1, 0), (0, 1), (1, 1)),
                ),
            )
            for corner, outside in corners:
                if corner == self.stairs:
                    continue
                if self.player and corner == (self.player.x, self.player.y):
                    continue
                fallback.append(corner)
                if all(
                    self.dungeon.is_wall(corner[0] + dx, corner[1] + dy)
                    for dx, dy in outside
                ):
                    closed.append(corner)
        candidates = closed or fallback
        if not candidates:
            return None
        pos = random.choice(candidates)
        self.dungeon.grid[pos[1]][pos[0]] = TRASH_CHAR
        return pos

    def _prepare_special_rooms(self) -> None:
        """Сделать 1-2 комнаты особыми: сокровищница, засада, лагерь, алтарь."""
        rooms = self.dungeon.rooms
        if len(rooms) < 3:
            return
        candidates = list(range(1, len(rooms) - 1))
        if not candidates:
            return
        count = 1
        if len(rooms) >= 12:
            count = 2
        if len(rooms) >= 24 and self.depth >= 3:
            count = 3
        if (
            count < 3
            and self.depth >= 4
            and len(candidates) > count
            and random.random() < 0.35
        ):
            count += 1
        for idx in random.sample(candidates, min(count, len(candidates))):
            room = rooms[idx]
            if self.run_mode == RUN_MODE_CLASSIC:
                kind = random.choices(
                    ("vault", "guarded", "camp"),
                    weights=(0.46, 0.34, 0.20),
                )[0]
            else:
                kind = random.choices(
                    ("vault", "guarded", "camp", "shrine"),
                    weights=(0.36, 0.27, 0.17, 0.20),
                )[0]
            if kind == "shrine" and self.altar_pos is not None:
                kind = "camp"
            self.special_rooms.append((*room, kind))
            if kind in ("vault", "guarded"):
                self._place_chest(room, guarded=kind == "guarded")
            if kind == "guarded":
                for _ in range(1 + (self.depth >= 6)):
                    self._spawn_guard(room)
            elif kind == "vault":
                pos = self._free_spot_in_room(room)
                if pos is not None:
                    self.items.append(
                        random_loot(
                            pos[0],
                            pos[1],
                            self.depth,
                            allow_ranged=self.allow_ranged_loot,
                        )
                    )
            elif kind == "shrine":
                pos = self._free_spot_in_room(room)
                if pos is not None:
                    self.altar_pos = pos
            else:
                for _ in range(random.randint(2, 3)):
                    pos = self._free_spot_in_room(room)
                    if pos is not None:
                        self.items.append(
                            random_loot(
                                pos[0],
                                pos[1],
                                self.depth,
                                allow_ranged=self.allow_ranged_loot,
                            )
                        )

    def _place_merchant(self) -> None:
        """Поставить торговца в отдельную комнату на заданных этажах."""
        if self.run_mode == RUN_MODE_CLASSIC:
            return
        if self.depth % MERCHANT_DEPTH_STEP != MERCHANT_DEPTH_OFFSET:
            return
        rooms = [
            room
            for room in self.dungeon.rooms[1:-1]
            if not self._is_special_room(room)
        ]
        if not rooms:
            rooms = list(self.dungeon.rooms[1:-1])
        random.shuffle(rooms)
        for room in rooms:
            pos = self._free_spot_in_room(room)
            if pos is None:
                continue
            self.merchant_pos = pos
            self.merchant_stock = make_merchant_stock(self.depth)
            if not self._is_special_room(room):
                self.special_rooms.append((*room, "shop"))
            return

    def _is_special_room(self, room: tuple[int, int, int, int]) -> bool:
        return any(entry[:4] == room for entry in self.special_rooms)

    def _free_spot_in_room(
        self,
        room: tuple[int, int, int, int],
    ) -> tuple[int, int] | None:
        x, y, w, h = room
        # Не занимаем клетки у стен: там могут начинаться коридоры.
        xs = range(x + 1, x + w - 1) if w > 2 else range(x, x + w)
        ys = range(y + 1, y + h - 1) if h > 2 else range(y, y + h)
        for _ in range(40):
            px = random.choice(xs)
            py = random.choice(ys)
            if (px, py) in (self.stairs, self.trash_pos):
                continue
            if self.chest_at(px, py) or self._occupied(px, py):
                continue
            return px, py
        return None

    # --- секретные комнаты -------------------------------------------------

    def _place_secrets(self) -> None:
        """Спрятать 0-2 комнаты за потайными дверями."""
        if self.run_mode == RUN_MODE_CLASSIC:
            return
        rooms = [
            room
            for room in self.dungeon.rooms[1:-1]
            if not self._is_special_room(room)
        ]
        if not rooms:
            return
        random.shuffle(rooms)
        count = 1 if random.random() < SECRET_ROOM_CHANCE else 0
        if (
            count
            and self.depth >= SECRET_ROOM_EXTRA_DEPTH
            and random.random() < SECRET_ROOM_EXTRA_CHANCE
        ):
            count += 1
        built = 0
        for room in rooms:
            if built >= count:
                break
            if self._carve_secret_room(room):
                built += 1

    def _carve_secret_room(
        self,
        room: tuple[int, int, int, int],
    ) -> bool:
        """Пристроить к комнате камеру 2x2/3x3 за фальшивой стеной."""
        x, y, w, h = room
        if w < 4 or h < 4:
            return False
        directions = [(0, -1), (0, 1), (-1, 0), (1, 0)]
        random.shuffle(directions)
        for dx, dy in directions:
            if dx == 0:
                door = (
                    random.randint(x + 1, x + w - 2),
                    y - 1 if dy < 0 else y + h,
                )
                cw = min(random.choice((2, 3)), w - 2)
                ch = 2
                offset = random.randint(0, cw - 1)
                rect = (
                    door[0] - offset,
                    door[1] - ch if dy < 0 else door[1] + 1,
                    cw,
                    ch,
                )
            else:
                door = (
                    x - 1 if dx < 0 else x + w,
                    random.randint(y + 1, y + h - 2),
                )
                cw = 2
                ch = min(random.choice((2, 3)), h - 2)
                offset = random.randint(0, ch - 1)
                rect = (
                    door[0] - cw if dx < 0 else door[0] + 1,
                    door[1] - offset,
                    cw,
                    ch,
                )
            if self._secret_room_fits(rect, door):
                self._build_secret_room(rect, door)
                return True
        return False

    def _secret_room_fits(
        self,
        rect: tuple[int, int, int, int],
        door: tuple[int, int],
    ) -> bool:
        """Камера должна целиком лежать в камне, а вокруг неё — только стены."""
        x, y, w, h = rect
        cells = [
            (cx, cy)
            for cy in range(y, y + h)
            for cx in range(x, x + w)
        ]
        allowed = set(cells) | {door}
        grid = self.dungeon.grid
        for cx, cy in cells:
            if not self.dungeon.in_bounds(cx, cy):
                return False
            if grid[cy][cx] != "#":
                return False
        dx, dy = door
        if not self.dungeon.in_bounds(dx, dy) or grid[dy][dx] != "#":
            return False
        for cx, cy in cells:
            for nx in (cx - 1, cx, cx + 1):
                for ny in (cy - 1, cy, cy + 1):
                    if (nx, ny) in allowed:
                        continue
                    if not self.dungeon.in_bounds(nx, ny):
                        return False
                    if grid[ny][nx] != "#":
                        return False
        return True

    def _build_secret_room(
        self,
        rect: tuple[int, int, int, int],
        door: tuple[int, int],
    ) -> None:
        x, y, w, h = rect
        cells = [
            (cx, cy)
            for cy in range(y, y + h)
            for cx in range(x, x + w)
        ]
        for cx, cy in cells:
            self.dungeon.grid[cy][cx] = "."
        self.secret_doors.add(door)
        self.special_rooms.append((*rect, "secret"))
        entry = next(
            (
                cell
                for cell in cells
                if max(
                    abs(cell[0] - door[0]),
                    abs(cell[1] - door[1]),
                )
                == 1
            ),
            cells[0],
        )
        if random.random() < 0.55:
            cx, cy = random.choice(
                [cell for cell in cells if cell != entry] or cells
            )
            self.chests.append(
                Chest(
                    cx,
                    cy,
                    items=make_chest_loot(
                        self.depth, allow_ranged=self.allow_ranged_loot
                    ),
                )
            )
            return
        spots = random.sample(cells, k=min(len(cells), random.randint(2, 3)))
        for spot in spots:
            self.items.append(
                random_loot(
                    spot[0],
                    spot[1],
                    self.depth,
                    allow_ranged=self.allow_ranged_loot,
                )
            )
        free = [cell for cell in cells if cell not in spots]
        if free:
            gx, gy = random.choice(free)
            self.items.append(
                Item(
                    "Gold",
                    "$",
                    "gold",
                    COLOR_GOLD,
                    gx,
                    gy,
                    random.randint(10 + self.depth * 2, 20 + self.depth * 4),
                )
            )

    # --- напольные ловушки -------------------------------------------------

    def _place_traps(self) -> None:
        """Скрытые ловушки в комнатах и коридорах, но не в особых комнатах."""
        if self.run_mode == RUN_MODE_CLASSIC:
            return
        count = min(
            TRAP_MAX,
            TRAP_BASE_COUNT + self.depth // TRAP_PER_DEPTH,
        )
        candidates: list[tuple[int, int]] = []
        for y in range(self.dungeon.h):
            for x in range(self.dungeon.w):
                if self.dungeon.grid[y][x] != ".":
                    continue
                if self.special_room_at(x, y) is not None:
                    continue
                if (x, y) == self.spawn or (x, y) == self.stairs:
                    continue
                if (x, y) in (self.trash_pos, self.merchant_pos):
                    continue
                if max(abs(x - self.spawn[0]), abs(y - self.spawn[1])) <= 1:
                    continue
                if self.chest_at(x, y) or self._occupied(x, y):
                    continue
                candidates.append((x, y))
        if not candidates:
            return
        kinds = ("spikes", "poison", "dart", "teleport")
        weights = (0.45, 0.28, 0.17, 0.10)
        for pos in random.sample(candidates, min(count, len(candidates))):
            kind = random.choices(kinds, weights=weights)[0]
            self.traps.append(Trap(pos[0], pos[1], kind))

    def trap_at(self, x: int, y: int) -> Trap | None:
        return next(
            (
                trap
                for trap in self.traps
                if (trap.x, trap.y) == (x, y) and trap.armed
            ),
            None,
        )

    def _spring_floor_trap(self) -> None:
        trap = self.trap_at(self.player.x, self.player.y)
        if trap is None:
            return
        trap.revealed = True
        trap.armed = False
        if trap.kind == "spikes":
            dmg = (
                TRAP_SPIKE_DAMAGE_BASE
                + self.depth // TRAP_SPIKE_DAMAGE_PER_DEPTH
            )
            self.msg(f"Hidden spikes stab you for {dmg}!", "warn")
            self._hurt_player(dmg, "hidden spikes", wear_armor=False)
        elif trap.kind == "dart":
            dmg = (
                TRAP_DART_DAMAGE_BASE
                + self.depth // TRAP_DART_DAMAGE_PER_DEPTH
            )
            self.msg(f"A dart trap fires at you for {dmg}!", "warn")
            self._hurt_player(dmg, "a dart trap", wear_armor=False)
        elif trap.kind == "poison":
            turns = (
                TRAP_POISON_TURNS_BASE
                + self.depth // TRAP_POISON_TURNS_PER_DEPTH
            )
            self._poison_from_trap("a poison needle", turns)
        else:
            self.msg("A teleport rune flares under your feet!", "warn")
            if not self.teleport_player():
                self.msg("But the magic fizzles.", "warn")

    def search(self) -> bool:
        """Поиск: открыть потайные двери и заметить ловушки рядом."""
        if self.game_over or self.player is None:
            return False
        px, py = self.player.x, self.player.y
        traps_found = 0
        for trap in self.traps:
            if trap.revealed:
                continue
            if max(abs(trap.x - px), abs(trap.y - py)) <= SEARCH_RADIUS:
                trap.revealed = True
                traps_found += 1
        doors_found = 0
        for door in sorted(self.secret_doors):
            if max(abs(door[0] - px), abs(door[1] - py)) <= SEARCH_RADIUS:
                self._reveal_secret_door(door)
                doors_found += 1
        if doors_found:
            self.msg(
                f"You reveal {doors_found} secret door(s) in the wall!",
                "good",
            )
        if traps_found:
            self.msg(f"You spot {traps_found} hidden trap(s).", "warn")
        if not doors_found and not traps_found:
            self.msg("You search the area but find nothing.", "warn")
        self.player_acted()
        return True

    def _reveal_secret_door(self, door: tuple[int, int]) -> None:
        x, y = door
        self.secret_doors.discard(door)
        if self.dungeon.in_bounds(x, y) and self.dungeon.grid[y][x] == "#":
            self.dungeon.grid[y][x] = SECRET_DOOR_CHAR

    def _notice_secret_door(self) -> None:
        """Один раз за этаж подсказать, что рядом есть фальшивая стена."""
        if self.secret_hinted or not self.secret_doors or self.player is None:
            return
        px, py = self.player.x, self.player.y
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if (px + dx, py + dy) in self.secret_doors:
                    self.secret_hinted = True
                    self.msg(
                        "A cold draft slips from the wall nearby. "
                        "Press 'x' to search.",
                        "warn",
                    )
                    return

    def _place_chest(
        self,
        room: tuple[int, int, int, int],
        guarded: bool = False,
    ) -> None:
        x, y, w, h = room
        inner = [
            (x + 1, y + 1),
            (x + w - 2, y + 1),
            (x + 1, y + h - 2),
            (x + w - 2, y + h - 2),
        ]
        candidates = [
            spot
            for spot in inner
            if self.walkable(*spot)
            and spot not in (self.stairs, self.trash_pos)
            and not self.chest_at(*spot)
            and not self._occupied(*spot)
        ]
        pos = (
            random.choice(candidates)
            if candidates
            else self._free_spot_in_room(room)
        )
        if pos is not None:
            self.chests.append(
                Chest(
                    pos[0],
                    pos[1],
                    guarded,
                    items=make_chest_loot(
                        self.depth,
                        guarded,
                        allow_ranged=self.allow_ranged_loot,
                    ),
                )
            )

    def _spawn_guard(self, room: tuple[int, int, int, int]) -> None:
        pos = self._free_spot_in_room(room)
        if pos is None:
            return
        kind = random.choice(enemy_pool(self.depth))
        self.enemies.append(make_enemy(kind, pos[0], pos[1], self.depth))

    def _special_room_entry_at(
        self,
        x: int,
        y: int,
    ) -> tuple[int, int, int, int, str] | None:
        for entry in self.special_rooms:
            sx, sy, w, h, _kind = entry
            if sx <= x < sx + w and sy <= y < sy + h:
                return entry
        return None

    def special_room_at(self, x: int, y: int) -> str | None:
        entry = self._special_room_entry_at(x, y)
        return entry[4] if entry else None

    def _notice_special_room(self) -> None:
        entry = self._special_room_entry_at(self.player.x, self.player.y)
        if entry is None:
            return
        key = entry[:4]
        if key in self.special_room_seen:
            return
        self.special_room_seen.add(key)
        self.msg(SPECIAL_ROOM_TEXT[entry[4]], "good")

    def chest_at(self, x: int, y: int) -> Chest | None:
        return next(
            (c for c in self.chests if (c.x, c.y) == (x, y)),
            None,
        )

    def open_chest(self, chest: Chest) -> bool:
        """Открыть сундук и показать содержимое в отдельном меню."""
        self.active_chest = chest
        self.chest_deposit_mode = False
        self.inventory_index = 0
        self.inventory_reorder = False
        self.container_index = 0
        if not chest.opened:
            chest.opened = True
            self.msg("You open the chest.", "item")
            chance = min(
                CHEST_TRAP_MAX,
                CHEST_TRAP_CHANCE
                + self.depth * CHEST_TRAP_PER_DEPTH
                + (CHEST_TRAP_BONUS_GUARDED if chest.guarded else 0.0),
            )
            if random.random() < chance:
                self._spring_chest_trap()
                if self.game_over:
                    self.active_chest = None
                    return False
        else:
            self.msg("You reopen the chest.", "item")
        self.mode = MODE_CHEST
        return True

    def close_chest(self) -> None:
        if self.mode == MODE_CHEST:
            self.mode = MODE_PLAYING
        self.active_chest = None
        self.chest_deposit_mode = False
        self.container_index = 0

    def take_from_chest(self, index: int) -> bool:
        chest = self.active_chest
        if chest is None or not (0 <= index < len(chest.items)):
            return False
        item = chest.items[index]
        if item.kind == "gold":
            self.gold += item.value
            chest.items.pop(index)
            self.msg(
                f"You take {item.value} gold from the chest.",
                "gold",
            )
        else:
            if not self.inventory.add(item):
                self.msg("Your pack is full.", "warn")
                return False
            chest.items.pop(index)
            self.msg(f"You take {item.name} from the chest.", "item")
        if not chest.items:
            self.msg("The chest is now empty.", "item")
        self.clamp_selection()
        return True

    def put_in_chest(self, index: int) -> bool:
        """Положить предмет из рюкзака обратно в открытый сундук."""
        chest = self.active_chest
        if chest is None or not (0 <= index < len(self.inventory.items)):
            return False
        if len(chest.items) >= CHEST_CAPACITY:
            self.msg(
                f"The chest is full ({CHEST_CAPACITY}/{CHEST_CAPACITY}).",
                "warn",
            )
            return False
        item = self.inventory.items[index]
        if item.quantity > 1:
            piece = item.split(1)
        else:
            piece = self.inventory.remove(index)
        chest.items.append(piece)
        self.msg(
            f"You put {piece.name} in the chest. "
            f"({len(chest.items)}/{CHEST_CAPACITY})",
            "item",
        )
        self.clamp_selection()
        return True

    def chest_nearby(self) -> Chest | None:
        """Ближайший сундук в соседней клетке (включая диагонали)."""
        if self.player is None:
            return None
        nearby = [
            chest
            for chest in self.chests
            if max(
                abs(chest.x - self.player.x),
                abs(chest.y - self.player.y),
            ) == 1
        ]
        if not nearby:
            return None
        return min(
            nearby,
            key=lambda chest: (
                abs(chest.x - self.player.x) + abs(chest.y - self.player.y),
                chest.y,
                chest.x,
            ),
        )

    def merchant_nearby(self) -> bool:
        if self.player is None or self.merchant_pos is None:
            return False
        return max(
            abs(self.merchant_pos[0] - self.player.x),
            abs(self.merchant_pos[1] - self.player.y),
        ) == 1

    def altar_nearby(self) -> bool:
        if self.player is None or self.altar_pos is None:
            return False
        return max(
            abs(self.altar_pos[0] - self.player.x),
            abs(self.altar_pos[1] - self.player.y),
        ) == 1

    def use_altar(self) -> bool:
        """Одно благословение за алтарь: лечение, antidote или +1 max HP."""
        if self.altar_pos is None or not self.altar_nearby():
            self.msg("There is no altar nearby.", "warn")
            return False
        if self.altar_used:
            self.msg("The altar is silent now.", "warn")
            return False
        self.altar_used = True
        healed = self._heal_player(
            max(1, int(self.player.max_hp * ALTAR_HEAL_RATIO))
        )
        cured = self.cure_poison()
        if healed:
            if cured:
                self.msg(
                    f"The altar restores {healed} HP and purifies your blood.",
                    "heal",
                )
            else:
                self.msg(f"The altar restores {healed} HP.", "heal")
        elif cured:
            self.msg("The altar purifies your blood.", "heal")
        else:
            self.player.max_hp += 1
            self.player.hp += 1
            self.msg(
                "The altar grants you a sliver of life (+1 max HP).",
                "good",
            )
        self.player_acted()
        return True

    def open_shop(self) -> None:
        self.mode = MODE_SHOP
        self.shop_index = 0
        self.shop_sell_mode = False
        self.shop_sell_index = 0
        self.msg("The merchant spreads out his wares.", "good")

    def close_shop(self) -> None:
        if self.mode == MODE_SHOP:
            self.mode = MODE_PLAYING
        self.shop_sell_mode = False

    def shop_move(self, delta: int) -> None:
        count = len(self.merchant_stock)
        if count:
            self.shop_index = (self.shop_index + delta) % count

    def open_shop_sell(self) -> None:
        """Включить продажу: курсор ходит по рюкзаку."""
        self.shop_sell_mode = True
        self.shop_sell_index = 0
        self.shop_sell_selected()

    def shop_sell_move(self, delta: int) -> None:
        count = len(self.inventory.items)
        if count:
            self.shop_sell_index = (self.shop_sell_index + delta) % count

    def shop_sell_selected(self) -> int | None:
        """Индекс выбранного для продажи предмета или None."""
        count = len(self.inventory.items)
        if count <= 0:
            self.shop_sell_index = 0
            return None
        self.shop_sell_index = min(max(0, self.shop_sell_index), count - 1)
        return self.shop_sell_index

    def item_price(self, item: Item) -> int:
        return shop_price(item, self.depth)

    def shop_sell_price(self, item: Item) -> int:
        return max(1, self.item_price(item) // 3)

    def _damaged_gear(self) -> list[Item]:
        seen: set[int] = set()
        damaged: list[Item] = []
        candidates = [
            self.inventory.weapon,
            self.inventory.armor,
            *self.inventory.items,
        ]
        for item in candidates:
            if item is None or id(item) in seen:
                continue
            seen.add(id(item))
            if item.max_durability > 0 and item.durability < item.max_durability:
                damaged.append(item)
        return damaged

    def repair_cost(self, item: Item) -> int:
        missing = max(0, item.max_durability - item.durability)
        if missing == 0:
            return 0
        return max(
            1,
            (missing + REPAIR_COST_DIVISOR - 1) // REPAIR_COST_DIVISOR,
        )

    def shop_repair_cost(self) -> int:
        return sum(self.repair_cost(item) for item in self._damaged_gear())

    def shop_repair_all(self) -> bool:
        damaged = self._damaged_gear()
        if not damaged:
            self.msg("Your gear is already in good shape.", "good")
            return False
        cost = sum(self.repair_cost(item) for item in damaged)
        if self.gold < cost:
            self.msg(
                f"A full repair costs {cost} gold; you have {self.gold}.",
                "warn",
            )
            return False
        self.gold -= cost
        for item in damaged:
            item.durability = item.max_durability
        self.msg(
            f"The merchant repairs {len(damaged)} item(s) "
            f"for {cost} gold.",
            "gold",
        )
        return True

    def shop_buy(self, index: int) -> bool:
        if not (0 <= index < len(self.merchant_stock)):
            return False
        stock_item = self.merchant_stock[index]
        price = self.item_price(stock_item)
        if self.gold < price:
            self.msg(
                f"You need {price} gold for the {stock_item.name}.",
                "warn",
            )
            return False
        piece = stock_item.copy()
        piece.quantity = 1
        if not self.inventory.add(piece):
            self.msg("Your pack is full.", "warn")
            return False
        self.gold -= price
        if stock_item.quantity > 1:
            stock_item.quantity -= 1
        else:
            self.merchant_stock.pop(index)
            self.shop_index = min(
                self.shop_index,
                max(0, len(self.merchant_stock) - 1),
            )
        self.msg(f"You buy {piece.name} for {price} gold.", "gold")
        return True

    def shop_sell_item(self, index: int) -> bool:
        if not (0 <= index < len(self.inventory.items)):
            return False
        item = self.inventory.items[index]
        price = self.shop_sell_price(item)
        name = item.name
        if item.quantity > 1:
            item.quantity -= 1
        else:
            self.inventory.remove(index)
        self.gold += price
        self.msg(f"You sell {name} for {price} gold.", "gold")
        self.shop_sell_selected()
        return True

    def interact(self) -> bool:
        """Взаимодействовать с мусоркой, сундуком или торговцем рядом."""
        if self.game_over:
            return False
        if self.merchant_nearby():
            self.open_shop()
            return True
        if self.altar_nearby():
            self.use_altar()
            return True
        if self.near_trash():
            self.open_trash()
            return True
        chest = self.chest_nearby()
        if chest is not None:
            if self.open_chest(chest):
                self.player_acted()
            return True
        self.msg("There is nothing to interact with here.", "warn")
        return False

    def _spring_chest_trap(self) -> None:
        if random.random() < 0.5:
            dmg = random.randint(1, 3 + self.depth // 3)
            self.msg(f"A dart trap hits you for {dmg}.", "warn")
            self._hurt_player(dmg, "a chest trap", wear_armor=False)
            return
        turns = 4 + self.depth // 4
        self.poison_turns = max(self.poison_turns, turns)
        self.poison_damage = max(self.poison_damage, self.poison_strength)
        self.msg(
            f"Poison gas escapes the chest! ({self.poison_turns} turns)",
            "warn",
        )

    def _spawn_enemies(self) -> None:
        rooms = len(self.dungeon.rooms)
        # Меньше врагов, но каждый заметнее: длинный забег не должен
        # превращаться в зачистку десятков крыс на каждом этаже.
        num = 3 + self.depth // 3 + max(0, rooms - 6) // 8
        pool = enemy_pool(self.depth)
        for _ in range(num):
            pos = self._free_spot()
            if pos is None:
                continue
            kind = random.choice(pool)
            self.enemies.append(make_enemy(kind, pos[0], pos[1], self.depth))

    def _spawn_items(self) -> None:
        rooms = len(self.dungeon.rooms)
        count = random.randint(3, 6) + max(0, rooms - 8) // 4
        for _ in range(count):
            pos = self._free_spot()
            if pos is None:
                continue
            self.items.append(
                random_loot(
                    pos[0],
                    pos[1],
                    self.depth,
                    allow_ranged=self.allow_ranged_loot,
                )
            )

    def _spawn_trash_loot(self) -> None:
        """Иногда в мусорке уже лежит что-то полезное."""
        if self.trash_pos is None or random.random() >= TRASH_LOOT_CHANCE:
            return
        count = random.randint(1, TRASH_LOOT_MAX)
        for _ in range(count):
            if len(self.trash_items) >= TRASH_CAPACITY:
                break
            item = random_loot(
                self.trash_pos[0],
                self.trash_pos[1],
                self.depth,
                allow_ranged=self.allow_ranged_loot,
            )
            self.trash_items.append(age_trash_gear(item))

    def _spawn_boss(self) -> None:
        """На каждом пятом этаже поставить босса биома к лестнице."""
        if self.depth % 5 != 0:
            return
        index = min(len(BOSS_TYPES) - 1, self.depth // 5 - 1)
        room = self.dungeon.rooms[-1]
        pos = self._free_spot_in_room(room)
        if pos is None:
            pos = self._spot_near(self.stairs[0], self.stairs[1], 3)
        if pos is None:
            return
        boss = make_boss(BOSS_TYPES[index], pos[0], pos[1], self.depth)
        self.enemies.append(boss)
        self.msg(f"{boss.name} guards the stairs!", "enemy")

    def _free_spot(self) -> tuple[int, int] | None:
        rooms = [
            room
            for room in self.dungeon.rooms[1:]
            if not self._is_special_room(room)
        ] or self.dungeon.rooms
        for _ in range(40):
            room = random.choice(rooms)
            x = room[0] + random.randint(0, room[2] - 1)
            y = room[1] + random.randint(0, room[3] - 1)
            if self._occupied(x, y) or (x, y) == self.stairs:
                continue
            if (x, y) == self.trash_pos:
                continue
            return x, y
        return None

    def _occupied(self, x: int, y: int, ignore_items: bool = False) -> bool:
        if self.player and (self.player.x, self.player.y) == (x, y):
            return True
        if any((e.x, e.y) == (x, y) for e in self.enemies):
            return True
        if any((c.x, c.y) == (x, y) for c in self.chests):
            return True
        if self.merchant_pos == (x, y):
            return True
        if self.altar_pos == (x, y):
            return True
        if not ignore_items and any((i.x, i.y) == (x, y) for i in self.items):
            return True
        return False

    def walkable(self, x: int, y: int) -> bool:
        return self.dungeon.walkable(x, y)

    def enemy_at(self, x: int, y: int) -> Entity | None:
        return next((e for e in self.enemies if (e.x, e.y) == (x, y)), None)

    def item_at(self, x: int, y: int) -> Item | None:
        return next((i for i in self.items if (i.x, i.y) == (x, y)), None)

    def is_visible(self, x: int, y: int) -> bool:
        return bool(self.visible[x, y])

    def is_explored(self, x: int, y: int) -> bool:
        return bool(self.explored[x, y])

    def update_fov(self) -> None:
        width, height = self.dungeon.w, self.dungeon.h
        trans = np.zeros((width, height), dtype=bool, order="F")
        for y in range(height):
            row = self.dungeon.grid[y]
            for x in range(width):
                trans[x, y] = row[x] != "#"
        self.visible = tcod.map.compute_fov(
            trans,
            (self.player.x, self.player.y),
            radius=FOV_RADIUS,
            light_walls=True,
            algorithm=FOV_SYMMETRIC_SHADOWCAST,
        )
        self._light_wall_edges()
        self.explored |= self.visible

    def camera(self) -> tuple[int, int]:
        """Левый верхний угол видимой области карты в мировых координатах."""
        if self.player is None:
            return 0, 0
        width, height = self.dungeon.w, self.dungeon.h
        view_w, view_h = self.view_width(), self.view_height()
        if width <= view_w:
            left = (width - view_w) // 2
        else:
            left = min(
                max(0, self.player.x - view_w // 2),
                width - view_w,
            )
        if height <= view_h:
            top = (height - view_h) // 2
        else:
            top = min(
                max(0, self.player.y - view_h // 2),
                height - view_h,
            )
        return left, top

    def _clamp_map(self, left: int, top: int) -> tuple[int, int]:
        width, height = self.dungeon.w, self.dungeon.h
        view_w, view_h = self.map_view_width(), self.map_view_height()
        if width <= view_w:
            left = (width - view_w) // 2
        else:
            left = min(max(0, left), width - view_w)
        if height <= view_h:
            top = (height - view_h) // 2
        else:
            top = min(max(0, top), height - view_h)
        return left, top

    def map_camera(self) -> tuple[int, int]:
        """Левый верхний угол полноэкранной карты."""
        return self._clamp_map(self.map_left, self.map_top)

    def open_map(self) -> None:
        if self.player is None:
            return
        self.center_map()
        self.mode = MODE_MAP

    def close_map(self) -> None:
        if self.mode == MODE_MAP:
            self.mode = MODE_PLAYING

    def center_map(self) -> None:
        if self.player is None:
            return
        self.map_left, self.map_top = self._clamp_map(
            self.player.x - self.map_view_width() // 2,
            self.player.y - self.map_view_height() // 2,
        )

    def scroll_map(self, dx: int, dy: int) -> None:
        self.map_left, self.map_top = self._clamp_map(
            self.map_left + dx,
            self.map_top + dy,
        )

    def _light_wall_edges(self) -> None:
        """Подсветить стены, примыкающие к видимому полу.

        На краю радиуса стена может оказаться на клетку дальше последнего
        видимого пола. Без этого граница комнаты или коридора выглядит так,
        будто игрок её не видит.
        """
        neighbors = (
            (-1, -1), (0, -1), (1, -1),
            (-1, 0), (1, 0),
            (-1, 1), (0, 1), (1, 1),
        )
        visible_floors = [
            (x, y)
            for y in range(self.dungeon.h)
            for x in range(self.dungeon.w)
            if self.visible[x, y] and self.dungeon.grid[y][x] != "#"
        ]
        for x, y in visible_floors:
            for dx, dy in neighbors:
                nx, ny = x + dx, y + dy
                if not self.dungeon.in_bounds(nx, ny):
                    continue
                if self.dungeon.grid[ny][nx] == "#":
                    self.visible[nx, ny] = True

    def attack(self, attacker: Entity, defender: Entity) -> None:
        if attacker is self.player:
            self.player_attack_events += 1
            dmg = max(
                1,
                self.melee_atk - defender.df + random.randint(-1, 2),
            )
            defender.hp -= dmg
            self.msg(f"You hit {defender.name} for {dmg}.")
            wear = ENEMY_GEAR_WEAR.get(
                defender.name,
                (1, ARMOR_WEAR_PER_HIT),
            )[0]
            self._wear_equipment(self.inventory.weapon, wear)
            if not defender.alive():
                self._kill_enemy(defender)
            return

        dmg = max(
            1,
            attacker.atk
            - (self.total_df if defender is self.player else defender.df)
            + random.randint(-1, 2),
        )
        if defender is self.player:
            self.msg(f"{attacker.name} hits you for {dmg}.", "enemy")
            self._hurt_player(dmg, attacker.name, attacker=attacker)
        else:
            defender.hp -= dmg
            if not defender.alive():
                self._kill_enemy(defender)

    def fire_ranged(self) -> bool:
        """Выстрелить из лука по ближайшему видимому врагу (автоцель)."""
        if self.game_over:
            return False
        weapon = self.inventory.weapon
        if weapon is None or weapon.effect != "ranged":
            self.msg("Equip a bow to shoot at range.", "warn")
            return False
        target = self._ranged_target()
        if target is None:
            self.msg("No target within bow range.", "warn")
            return False
        self._shoot_target(target, weapon)
        self.player_acted()
        return True

    # --- ручное прицеливание ----------------------------------------------

    def start_aim(self) -> bool:
        """Войти в режим прицела; без лука — только сообщение."""
        if self.game_over or self.player is None:
            return False
        weapon = self.inventory.weapon
        if weapon is None or weapon.effect != "ranged":
            self.msg("Equip a bow to aim.", "warn")
            return False
        target = self._ranged_target()
        if target is not None:
            self.aim_dx = (target.x > self.player.x) - (
                target.x < self.player.x
            )
            self.aim_dy = (target.y > self.player.y) - (
                target.y < self.player.y
            )
        elif self.aim_dx == 0 and self.aim_dy == 0:
            self.aim_dx, self.aim_dy = 1, 0
        self.mode = MODE_AIM
        return True

    def set_aim(self, dx: int, dy: int) -> None:
        """Повернуть прицел; направление всегда нормализуется к 8 сторонам."""
        if dx == 0 and dy == 0:
            return
        self.aim_dx = max(-1, min(1, dx))
        self.aim_dy = max(-1, min(1, dy))

    def cancel_aim(self) -> bool:
        if self.mode != MODE_AIM:
            return False
        self.mode = MODE_PLAYING
        return True

    def aim_label(self) -> str:
        return DIRECTION_NAMES.get((self.aim_dx, self.aim_dy), "East")

    def _shot_blocked(self, x: int, y: int) -> bool:
        """Стрела не проходит сквозь сундук, торговца, алтарь и мусорку."""
        return (
            self.chest_at(x, y) is not None
            or (x, y) == self.merchant_pos
            or (x, y) == self.altar_pos
            or (x, y) == self.trash_pos
        )

    def aim_path(self) -> tuple[list[tuple[int, int]], Entity | None]:
        """Клетки луча до первой преграды и враг, если он на линии."""
        if self.player is None:
            return [], None
        px, py = self.player.x, self.player.y
        cells: list[tuple[int, int]] = []
        for step in range(1, PLAYER_RANGED_RANGE + 1):
            nx = px + self.aim_dx * step
            ny = py + self.aim_dy * step
            if not self.dungeon.in_bounds(nx, ny):
                break
            if not self.walkable(nx, ny):
                break
            enemy = self.enemy_at(nx, ny)
            if enemy is not None and enemy.alive():
                cells.append((nx, ny))
                return cells, enemy
            if self._shot_blocked(nx, ny):
                break
            cells.append((nx, ny))
        return cells, None

    def aim_info(self) -> dict:
        """Данные для HUD: направление, клетки луча и выбранная цель."""
        path, target = self.aim_path()
        return {
            "dx": self.aim_dx,
            "dy": self.aim_dy,
            "label": self.aim_label(),
            "path": path,
            "target": target,
        }

    def fire_aimed(self) -> bool:
        """Выстрелить в выбранном направлении и выйти из прицела."""
        if self.game_over or self.player is None:
            return False
        weapon = self.inventory.weapon
        if weapon is None or weapon.effect != "ranged":
            self.mode = MODE_PLAYING
            self.msg("Equip a bow to shoot at range.", "warn")
            return False
        _path, target = self.aim_path()
        label = self.aim_label()
        self.mode = MODE_PLAYING
        if target is None:
            self.msg(f"Your arrow flies {label.lower()} into the dark.", "warn")
            self._wear_equipment(weapon, 1)
            self.player_acted()
            return True
        self._shoot_target(target, weapon)
        self.player_acted()
        return True

    def _shoot_target(self, target: Entity, weapon: Item) -> int:
        """Нанести урон стрелой, износить лук и убрать павшего врага."""
        dist = max(
            abs(target.x - self.player.x),
            abs(target.y - self.player.y),
        )
        dmg = max(
            1,
            self.total_atk
            - target.df
            - dist // 2
            + random.randint(-1, 2),
        )
        target.hp -= dmg
        self.msg(f"Your arrow hits {target.name} for {dmg}.")
        wear = ENEMY_GEAR_WEAR.get(
            target.name,
            (1, ARMOR_WEAR_PER_HIT),
        )[0]
        self._wear_equipment(weapon, wear)
        if not target.alive():
            self._kill_enemy(target)
        return dmg

    def _ranged_target(self) -> Entity | None:
        targets = [
            enemy
            for enemy in self.enemies
            if enemy.alive()
            and self.is_visible(enemy.x, enemy.y)
            and max(
                abs(enemy.x - self.player.x),
                abs(enemy.y - self.player.y),
            ) <= PLAYER_RANGED_RANGE
        ]
        if not targets:
            return None
        return min(
            targets,
            key=lambda enemy: (
                max(
                    abs(enemy.x - self.player.x),
                    abs(enemy.y - self.player.y),
                ),
                enemy.hp,
            ),
        )

    def _kill_enemy(self, enemy: Entity) -> None:
        if enemy not in self.enemies:
            return
        self.enemies.remove(enemy)
        self.kills += 1
        self.player_xp += enemy.xp
        self.msg(f"{enemy.name} dies! (+{enemy.xp} XP)")
        if enemy.boss:
            gold = random.randint(
                20 + self.depth * 5,
                40 + self.depth * 8,
            )
            self.gold += gold
            self.msg(
                f"You loot {gold} gold from the {enemy.name}.",
                "gold",
            )
            self.items.append(
                random_loot(
                    enemy.x,
                    enemy.y,
                    self.depth,
                    allow_ranged=self.allow_ranged_loot,
                )
            )
            heal = max(
                BOSS_HEAL_MIN,
                int(self.player.max_hp * BOSS_HEAL_RATIO),
            )
            healed = self._heal_player(heal)
            if healed:
                self.msg(f"You catch your breath (+{healed} HP).", "heal")
        self._check_level_up()

    def _hurt_player(
        self,
        dmg: int,
        source: str,
        wear_armor: bool = True,
        attacker: Entity | None = None,
    ) -> None:
        if self.game_over:
            return
        self.player.hp -= dmg
        if wear_armor:
            amount = ARMOR_WEAR_PER_HIT
            if attacker is not None:
                amount = ENEMY_GEAR_WEAR.get(
                    attacker.name,
                    (1, ARMOR_WEAR_PER_HIT),
                )[1]
            self._wear_equipment(self.inventory.armor, amount)
        if self.player.hp <= 0:
            self.player.hp = 0
            self.killed_by = source
            self.msg("You died!", "enemy")
            self.finish(win=False)

    def _apply_poison(self, enemy: Entity) -> None:
        if self.game_over:
            return
        was_poisoned = self.poison_turns > 0
        self.poison_turns = max(self.poison_turns, POISON_TURNS)
        self.poison_damage = max(self.poison_damage, self.poison_strength)
        if was_poisoned:
            self.msg(
                f"{enemy.name}'s venom burns again "
                f"({self.poison_turns} turns).",
                "warn",
            )
        else:
            self.msg(
                f"You are poisoned by {enemy.name}! "
                f"({self.poison_turns} turns)",
                "warn",
            )

    def _poison_from_trap(self, source: str, turns: int) -> None:
        if self.game_over:
            return
        was_poisoned = self.poison_turns > 0
        self.poison_turns = max(self.poison_turns, turns)
        self.poison_damage = max(self.poison_damage, self.poison_strength)
        if was_poisoned:
            self.msg(
                f"The poison burns again ({self.poison_turns} turns).",
                "warn",
            )
        else:
            self.msg(
                f"You are poisoned by {source}! "
                f"({self.poison_turns} turns)",
                "warn",
            )

    def cure_poison(self) -> bool:
        if self.poison_turns <= 0:
            return False
        self.poison_turns = 0
        self.poison_damage = POISON_DAMAGE
        return True

    def _poison_tick(self) -> None:
        if self.poison_turns <= 0 or self.game_over:
            return
        self.poison_turns -= 1
        dmg = max(1, self.poison_damage)
        self.player.hp -= dmg
        if self.player.hp <= 0:
            self.player.hp = 0
            self.killed_by = "Poison"
            self.msg("The poison overwhelms you!", "enemy")
            self.finish(win=False)
            return
        if self.poison_turns <= 0:
            self.msg(f"Poison deals {dmg}. You feel better.", "warn")
        else:
            self.msg(
                f"Poison deals {dmg} ({self.poison_turns} turns left).",
                "warn",
            )

    def _wear_equipment(self, item: Item | None, amount: int = 1) -> None:
        """Износить оружие/броню и сломать при нуле прочности."""
        if item is None or item.max_durability <= 0 or amount <= 0:
            return
        item.durability = max(0, item.durability - amount)
        if item.durability <= 0:
            inventory = self.inventory
            if inventory.weapon is item:
                inventory.weapon = None
            if inventory.armor is item:
                inventory.armor = None
            if item in inventory.items:
                inventory.items.remove(item)
            self.msg(f"Your {item.name} breaks!", "warn")
            return
        low_marks = {
            max(1, item.max_durability // 4),
            max(1, item.max_durability // 10),
        }
        if item.durability in low_marks:
            self.msg(
                f"Your {item.name} is wearing out "
                f"({item.durability}/{item.max_durability}).",
                "warn",
            )

    def _heal_player(self, amount: int) -> int:
        """Восстановить не больше ``amount`` HP и вернуть фактическое лечение."""
        if amount <= 0 or self.game_over:
            return 0
        before = self.player.hp
        self.player.hp = min(self.player.max_hp, self.player.hp + amount)
        return self.player.hp - before

    def _check_level_up(self) -> None:
        while self.player_xp >= self.xp_next:
            self.player_xp -= self.xp_next
            self.xp_next = int(self.xp_next * 1.5)
            self.player_level += 1
            self.player.max_hp += 5
            heal = max(
                LEVEL_UP_HEAL_MIN,
                int(self.player.max_hp * LEVEL_UP_HEAL_RATIO),
            )
            healed = self._heal_player(heal)
            self.player.atk += 1
            if self.player_level % 2 == 0:
                self.player.df += 1
            self.msg(
                f"*** Level up! LV {self.player_level} "
                f"(+{healed} HP) ***",
                "good",
            )

    def player_acted(self) -> None:
        if self.game_over:
            return
        self.turns += 1
        self._notice_special_room()
        self._notice_secret_door()
        self.enemy_turn()
        if not self.game_over:
            self._poison_tick()
        if not self.game_over:
            self.update_fov()

    def move(self, dx: int, dy: int) -> None:
        if self.game_over:
            return
        nx, ny = self.player.x + dx, self.player.y + dy
        enemy = self.enemy_at(nx, ny)
        if enemy:
            self.attack(self.player, enemy)
            self.player_acted()
            return
        if self.merchant_pos == (nx, ny):
            if not self.merchant_noticed:
                self.merchant_noticed = True
                self.msg(
                    "A merchant waits here. Press 'i' to trade.",
                    "warn",
                )
            return
        if self.altar_pos == (nx, ny):
            self.msg("An altar stands here. Press 'i' to pray.", "warn")
            return
        chest = self.chest_at(nx, ny)
        if chest:
            if not self.chest_hinted:
                self.chest_hinted = True
                self.msg(
                    "A chest blocks the way. Press 'i' to interact.",
                    "warn",
                )
            return
        if (nx, ny) == self.trash_pos:
            if not self.trash_noticed:
                self.trash_noticed = True
                self.msg(
                    f"A trash bin blocks the way "
                    f"({len(self.trash_items)}/{TRASH_CAPACITY}). "
                    f"Press 'i' to interact.",
                    "warn",
                )
            return
        if not self.walkable(nx, ny):
            return
        self.player.x, self.player.y = nx, ny
        self._spring_floor_trap()
        if self.game_over:
            return
        item = self.item_at(self.player.x, self.player.y)
        if item:
            self.pickup(item)
        self.player_acted()

    def wait(self) -> None:
        if self.game_over:
            return
        self.msg("You wait.")
        self.player_acted()

    def pickup(self, item: Item) -> None:
        if item.kind == "gold":
            self.gold += item.value
            self.msg(f"You found {item.value} gold.", "gold")
            self.items.remove(item)
            return
        if not self.inventory.add(item):
            self.msg("Your pack is full.", "warn")
            return
        self.items.remove(item)
        self.msg(f"You pick up {item.name}.", "item")

    def use_inventory(self, index: int) -> bool:
        self.skip_turn = False
        if self.inventory.use(index, self):
            self.clamp_selection()
            if not self.skip_turn:
                self.player_acted()
            return True
        return False

    def on_trash(self) -> bool:
        return self.trash_pos is not None and (
            self.player.x,
            self.player.y,
        ) == self.trash_pos

    def trash_nearby(self) -> bool:
        """Мусорка стоит в соседней клетке (включая диагонали)."""
        if self.trash_pos is None or self.player is None:
            return False
        return max(
            abs(self.trash_pos[0] - self.player.x),
            abs(self.trash_pos[1] - self.player.y),
        ) == 1

    def near_trash(self) -> bool:
        return self.on_trash() or self.trash_nearby()

    def put_in_trash(self, index: int) -> bool:
        """Выбросить предмет из рюкзака в мусорку рядом."""
        if not (0 <= index < len(self.inventory.items)):
            return False
        if not self.near_trash():
            self.msg(
                "You can only throw items away next to the trash bin.",
                "warn",
            )
            return False
        if len(self.trash_items) >= TRASH_CAPACITY:
            self.msg(
                f"The trash is full ({TRASH_CAPACITY}/{TRASH_CAPACITY}).",
                "warn",
            )
            return False
        item = self.inventory.items[index]
        if item.quantity > 1:
            piece = item.split(1)
        else:
            piece = self.inventory.remove(index)
        self.trash_items.append(piece)
        self.msg(
            f"You throw {piece.name} into the trash. "
            f"({len(self.trash_items)}/{TRASH_CAPACITY})",
            "item",
        )
        self.clamp_selection()
        return True

    def open_trash(self) -> None:
        if not self.near_trash():
            self.msg("There is no trash bin nearby.", "warn")
            return
        self.trash_deposit_mode = False
        self.inventory_index = 0
        self.inventory_reorder = False
        self.container_index = 0
        self.mode = MODE_TRASH

    def close_trash(self) -> None:
        if self.mode == MODE_TRASH:
            self.mode = MODE_PLAYING
        self.trash_deposit_mode = False
        self.container_index = 0

    def take_from_trash(self, index: int) -> bool:
        if not (0 <= index < len(self.trash_items)):
            return False
        item = self.trash_items[index]
        if item.kind == "gold":
            self.gold += item.value
            self.trash_items.pop(index)
            self.msg(f"You find {item.value} gold in the trash.", "gold")
            self.clamp_selection()
            return True
        if not self.inventory.add(item):
            self.msg("Your pack is full.", "warn")
            return False
        self.trash_items.pop(index)
        self.msg(f"You take {item.name} from the trash.", "item")
        self.clamp_selection()
        return True

    def teleport_player(self) -> bool:
        spots: list[tuple[int, int]] = []
        for y in range(self.dungeon.h):
            for x in range(self.dungeon.w):
                if (
                    self.walkable(x, y)
                    and not self.enemy_at(x, y)
                    and not self.chest_at(x, y)
                    and (x, y) not in (self.trash_pos, self.merchant_pos)
                    and (x, y) != self.altar_pos
                    and not any(
                        (trap.x, trap.y) == (x, y) for trap in self.traps
                    )
                    and (x, y) != (self.player.x, self.player.y)
                ):
                    spots.append((x, y))
        if not spots:
            return False
        self.player.x, self.player.y = random.choice(spots)
        return True

    def _expire_maps(self) -> None:
        """Израсходовать свитки карты, открытые на прошлом этаже."""
        spent = 0
        for index in range(len(self.inventory.items) - 1, -1, -1):
            item = self.inventory.items[index]
            if (
                item.kind == "scroll"
                and item.effect == "mapping"
                and item.map_open
            ):
                item.map_open = False
                item.quantity -= 1
                spent += 1
                if item.quantity <= 0:
                    self.inventory.items.pop(index)
        if spent:
            self.msg("The spent map crumbles to dust.", "item")

    def reveal_map(self) -> None:
        for y in range(self.dungeon.h):
            for x in range(self.dungeon.w):
                if self.dungeon.grid[y][x] != "#":
                    self.explored[x, y] = True
                    for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                        if self.dungeon.in_bounds(nx, ny):
                            self.explored[nx, ny] = True

    def cast_fire(self, radius: int, damage: int) -> int:
        hits = 0
        px, py = self.player.x, self.player.y
        for e in self.enemies[:]:
            if max(abs(e.x - px), abs(e.y - py)) > radius:
                continue
            if not self.is_visible(e.x, e.y):
                continue
            e.hp -= damage
            hits += 1
            self.msg(f"Fire burns {e.name} for {damage}.", "warn")
            if not e.alive():
                self._kill_enemy(e)
        return hits

    def cast_lightning(self, damage: int) -> str | None:
        targets = [e for e in self.enemies if self.is_visible(e.x, e.y)]
        if not targets:
            return None
        target = min(
            targets,
            key=lambda e: (
                abs(e.x - self.player.x) + abs(e.y - self.player.y),
                e.hp,
            ),
        )
        target.hp -= damage
        self.msg(f"Lightning strikes {target.name} for {damage}!", "warn")
        if not target.alive():
            self._kill_enemy(target)
        return target.name

    def _path_cost(self) -> np.ndarray:
        cost = np.zeros(
            (self.dungeon.w, self.dungeon.h), dtype=np.int8, order="F"
        )
        for y in range(self.dungeon.h):
            for x in range(self.dungeon.w):
                if self.dungeon.grid[y][x] != "#":
                    cost[x, y] = 1
        for e in self.enemies:
            cost[e.x, e.y] = 0
        for chest in self.chests:
            cost[chest.x, chest.y] = 0
        if self.merchant_pos is not None:
            cost[self.merchant_pos[0], self.merchant_pos[1]] = 0
        if self.altar_pos is not None:
            cost[self.altar_pos[0], self.altar_pos[1]] = 0
        if self.trash_pos is not None:
            cost[self.trash_pos[0], self.trash_pos[1]] = 0
        cost[self.player.x, self.player.y] = 1
        return cost

    def _melee_enemy(self, enemy: Entity) -> None:
        self.attack(enemy, self.player)
        if self.game_over:
            return
        if enemy.behavior == "poison":
            self._apply_poison(enemy)
        if enemy.behavior == "fast" and not self.game_over:
            self.attack(enemy, self.player)

    def _ranged_attack(self, enemy: Entity) -> None:
        dmg = max(
            1,
            enemy.atk - self.total_df + random.randint(-1, 2),
        )
        self.msg(f"{enemy.name} shoots you for {dmg}.", "enemy")
        self._hurt_player(dmg, enemy.name, attacker=enemy)

    def _summon(self, enemy: Entity) -> None:
        limit = MAX_ENEMIES + len(self.dungeon.rooms) // 3
        if len(self.enemies) >= limit:
            self.msg(
                f"{enemy.name} chants, but the shadows are full.",
                "warn",
            )
            return
        pos = self._spot_near(enemy.x, enemy.y, 2)
        if pos is None:
            self.msg(f"{enemy.name} chants, but nothing answers.", "warn")
            return
        kind = ENEMY_BY_NAME[random.choice(("Rat", "Bat"))]
        minion = make_enemy(kind, pos[0], pos[1], self.depth)
        self.enemies.append(minion)
        self.msg(f"{enemy.name} summons a {minion.name}!", "enemy")

    def _spot_near(
        self,
        x: int,
        y: int,
        radius: int,
    ) -> tuple[int, int] | None:
        spots: list[tuple[int, int]] = []
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if dx == 0 and dy == 0:
                    continue
                nx, ny = x + dx, y + dy
                if not self.walkable(nx, ny):
                    continue
                if self._occupied(nx, ny):
                    continue
                if (nx, ny) in (self.stairs, self.trash_pos):
                    continue
                spots.append((nx, ny))
        return random.choice(spots) if spots else None

    def enemy_turn(self) -> None:
        cost = self._path_cost()
        for e in self.enemies[:]:
            if self.game_over:
                return
            if not e.alive():
                continue

            if e.behavior == "slow":
                # Голем действует через ход.
                if e.cooldown > 0:
                    e.cooldown -= 1
                    continue
                e.cooldown = 1
            elif e.cooldown > 0:
                e.cooldown -= 1

            dist = abs(self.player.x - e.x) + abs(self.player.y - e.y)

            if (
                e.behavior == "ranged"
                and dist > 1
                and dist <= ENEMY_RANGED_RANGE
                and self.is_visible(e.x, e.y)
            ):
                if e.cooldown <= 0:
                    self._ranged_attack(e)
                    e.cooldown = 2
                continue

            if (
                e.behavior == "summoner"
                and dist <= AGGRO_RANGE
                and self.is_visible(e.x, e.y)
                and e.cooldown <= 0
            ):
                self._summon(e)
                e.cooldown = SUMMON_COOLDOWN
                continue

            if dist == 1:
                self._melee_enemy(e)
                continue
            if dist > AGGRO_RANGE:
                continue

            cost[e.x, e.y] = 1
            graph = tcod.path.SimpleGraph(cost=cost, cardinal=1, diagonal=0)
            pf = tcod.path.Pathfinder(graph)
            pf.add_root((e.x, e.y))
            path = pf.path_to((self.player.x, self.player.y))
            cost[e.x, e.y] = 0
            if len(path) < 2:
                continue
            nx, ny = int(path[1][0]), int(path[1][1])
            if (nx, ny) == (self.player.x, self.player.y):
                self._melee_enemy(e)
                continue
            if (
                self.walkable(nx, ny)
                and not self.enemy_at(nx, ny)
                and not self.chest_at(nx, ny)
                and (nx, ny) != self.trash_pos
                and (nx, ny) != self.merchant_pos
                and (nx, ny) != self.altar_pos
            ):
                e.x, e.y = nx, ny

    def descend(self) -> None:
        if (self.player.x, self.player.y) != self.stairs:
            self.msg('You must stand on ">" to descend.')
            return
        boss = next((enemy for enemy in self.enemies if enemy.boss), None)
        if boss is not None:
            self.msg(
                f"The stairs are sealed until {boss.name} falls!",
                "warn",
            )
            return
        if self.depth >= MAX_DEPTH:
            self.msg("*** You escape the Castle of Shadows! VICTORY! ***", "good")
            self.finish(win=True)
            return
        self.depth += 1
        self.msg(f"You descend to depth {self.depth}.")
        self.new_level()
        self.save()

    def finish(self, win: bool = False, quit_requested: bool = False) -> None:
        self.win = win
        self.quit_requested = quit_requested
        self.game_over = True
        self.trash_deposit_mode = False
        self.chest_deposit_mode = False
        if self.slot is not None:
            delete_save(self.slot)
        self.mode = MODE_DEAD

    def toggle_help(self) -> None:
        if self.mode == MODE_HELP:
            self.close_help()
            return
        self.help_return_mode = self.mode
        self.mode = MODE_HELP

    def close_help(self) -> None:
        if self.mode == MODE_HELP:
            self.mode = self.help_return_mode

    def toggle_inventory(self) -> None:
        if self.mode == MODE_INVENTORY:
            self.mode = MODE_PLAYING
            self.inventory_reorder = False
        elif self.mode == MODE_PLAYING:
            self.inventory_index = 0
            self.inventory_reorder = False
            self.mode = MODE_INVENTORY

    def toggle_inventory_reorder(self) -> None:
        """Включить/выключить режим перестановки предметов."""
        self.inventory_reorder = not self.inventory_reorder

    def inventory_reorder_move(self, delta: int) -> None:
        """Переместить выбранный предмет вверх или вниз по рюкзаку."""
        if not self.inventory_reorder:
            return
        index = self.inventory_selected()
        if index is None:
            return
        moved = self.inventory.move(index, delta)
        if moved is not None:
            self.inventory_index = moved

    def quick_use_inventory(self, slot: int) -> bool:
        """Быстрый доступ к первым девяти предметам по цифрам 1-9."""
        if not (1 <= slot <= 9):
            return False
        index = slot - 1
        if index >= len(self.inventory.items):
            self.msg(f"No item in quick slot {slot}.")
            return False
        self.inventory_index = index
        return self.use_inventory(index)

    def inventory_move(self, delta: int) -> None:
        """Передвинуть курсор по рюкзаку с закольцовыванием."""
        count = len(self.inventory.items)
        if count <= 0:
            self.inventory_index = 0
            return
        self.inventory_index = (self.inventory_index + delta) % count

    def inventory_selected(self) -> int | None:
        """Индекс выбранного предмета рюкзака или None для пустого рюкзака."""
        count = len(self.inventory.items)
        if count <= 0:
            self.inventory_index = 0
            return None
        self.inventory_index = min(max(0, self.inventory_index), count - 1)
        return self.inventory_index

    def container_count(self) -> int:
        """Сколько предметов в открытом контейнере (не в режиме переноса)."""
        if self.mode == MODE_CHEST and not self.chest_deposit_mode:
            return len(self.active_chest.items) if self.active_chest else 0
        if self.mode == MODE_TRASH and not self.trash_deposit_mode:
            return len(self.trash_items)
        return 0

    def container_move(self, delta: int) -> None:
        """Передвинуть курсор по содержимому сундука или мусорки."""
        count = self.container_count()
        if count <= 0:
            self.container_index = 0
            return
        self.container_index = (self.container_index + delta) % count

    def container_selected(self) -> int | None:
        """Индекс выбранного предмета контейнера или None."""
        count = self.container_count()
        if count <= 0:
            self.container_index = 0
            return None
        self.container_index = min(max(0, self.container_index), count - 1)
        return self.container_index

    def clamp_selection(self) -> None:
        """Держать курсоры в пределах списков после переноса предметов."""
        count = len(self.inventory.items)
        self.inventory_index = (
            min(max(0, self.inventory_index), count - 1) if count else 0
        )
        count = self.container_count()
        self.container_index = (
            min(max(0, self.container_index), count - 1) if count else 0
        )

    def restart(self) -> None:
        """Начать новый забег в том же слоте после смерти."""
        slot = self.slot if self.slot is not None else first_free_slot()
        run_mode = self.run_mode
        display_mode = self.display_mode
        self.__init__(run_mode=run_mode, display_mode=display_mode)
        self.slot = slot
        self.mode = MODE_PLAYING
        self.save()
