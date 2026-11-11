"""Состояние игры: ходы, бой, FOV, спуск, статистика."""
from __future__ import annotations

import random

import numpy as np
import tcod.map
import tcod.path
from tcod.constants import FOV_SYMMETRIC_SHADOWCAST

from constants import (
    AGGRO_RANGE,
    ARMOR_WEAR_PER_HIT,
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
    DESCEND_HEAL_MIN,
    DESCEND_HEAL_RATIO,
    ENEMY_RANGED_RANGE,
    FOV_RADIUS,
    LEVEL_UP_HEAL_MIN,
    LEVEL_UP_HEAL_RATIO,
    LOG_H,
    LOG_HISTORY,
    MAP_H,
    MAP_VIEW_H,
    MAP_VIEW_W,
    MAP_W,
    MAX_DEPTH,
    MAX_ENEMIES,
    MERCHANT_DEPTH_OFFSET,
    MERCHANT_DEPTH_STEP,
    MODE_CHEST,
    MODE_DEAD,
    MODE_HELP,
    MODE_INVENTORY,
    MODE_MAP,
    MODE_MENU,
    MODE_PAUSE,
    MODE_PLAYING,
    MODE_SHOP,
    MODE_SLOTS,
    MODE_TRASH,
    POISON_DAMAGE,
    POISON_PER_DEPTH,
    POISON_TURNS,
    PLAYER_RANGED_RANGE,
    REPAIR_COST_DIVISOR,
    SUMMON_COOLDOWN,
    TRASH_CAPACITY,
    TRASH_CHAR,
    TRASH_LOOT_CHANCE,
    TRASH_LOOT_MAX,
    VIEW_H,
    VIEW_W,
)
from dungeon import Dungeon
from entities import (
    BOSS_TYPES,
    ENEMY_BY_NAME,
    ENEMY_GEAR_WEAR,
    Chest,
    Entity,
    Item,
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
    MENU_OPTIONS = ("New Game", "How to Play", "Quit")
    PAUSE_OPTIONS = (
        "Resume",
        "Save & Quit to main menu",
        "Quit to main menu without saving",
        "Save & Quit to Desktop",
        "Quit to Desktop without saving",
    )

    def __init__(self, build_level: bool = True) -> None:
        self.mode = MODE_MENU
        self.menu_index = 0
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
        self.merchant_pos: tuple[int, int] | None = None
        self.merchant_stock: list[Item] = []
        self.merchant_noticed = False
        self.shop_index = 0
        self.shop_sell_mode = False
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
            return ("Continue", "New Game", "How to Play", "Quit")
        return self.MENU_OPTIONS

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
        self.__init__()
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

    def new_level(self, first: bool = False) -> None:
        if not first:
            self._expire_maps()
        self.dungeon = Dungeon(MAP_W, MAP_H)
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
        self.merchant_pos = None
        self.merchant_stock = []
        self.merchant_noticed = False
        self.shop_index = 0
        self.shop_sell_mode = False
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
        """Сделать 1-2 комнаты особыми: сокровищница, засада или лагерь."""
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
            kind = random.choices(
                ("vault", "guarded", "camp"),
                weights=(0.45, 0.35, 0.20),
            )[0]
            self.special_rooms.append((*room, kind))
            if kind in ("vault", "guarded"):
                self._place_chest(room, guarded=kind == "guarded")
            if kind == "guarded":
                for _ in range(1 + (self.depth >= 6)):
                    self._spawn_guard(room)
            elif kind == "vault":
                pos = self._free_spot_in_room(room)
                if pos is not None:
                    self.items.append(random_loot(pos[0], pos[1], self.depth))
            else:
                for _ in range(random.randint(2, 3)):
                    pos = self._free_spot_in_room(room)
                    if pos is not None:
                        self.items.append(
                            random_loot(pos[0], pos[1], self.depth)
                        )

    def _place_merchant(self) -> None:
        """Поставить торговца в отдельную комнату на заданных этажах."""
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
        for _ in range(40):
            px = x + random.randint(0, w - 1)
            py = y + random.randint(0, h - 1)
            if (px, py) in (self.stairs, self.trash_pos):
                continue
            if self.chest_at(px, py) or self._occupied(px, py):
                continue
            return px, py
        return None

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
                    items=make_chest_loot(self.depth, guarded),
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

    def open_shop(self) -> None:
        self.mode = MODE_SHOP
        self.shop_index = 0
        self.shop_sell_mode = False
        self.msg("The merchant spreads out his wares.", "good")

    def close_shop(self) -> None:
        if self.mode == MODE_SHOP:
            self.mode = MODE_PLAYING
        self.shop_sell_mode = False

    def shop_move(self, delta: int) -> None:
        count = len(self.merchant_stock)
        if count:
            self.shop_index = (self.shop_index + delta) % count

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
        return True

    def interact(self) -> bool:
        """Взаимодействовать с мусоркой, сундуком или торговцем рядом."""
        if self.game_over:
            return False
        if self.merchant_nearby():
            self.open_shop()
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
            self.items.append(random_loot(pos[0], pos[1], self.depth))

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
        if width <= VIEW_W:
            left = (width - VIEW_W) // 2
        else:
            left = min(
                max(0, self.player.x - VIEW_W // 2),
                width - VIEW_W,
            )
        if height <= VIEW_H:
            top = (height - VIEW_H) // 2
        else:
            top = min(
                max(0, self.player.y - VIEW_H // 2),
                height - VIEW_H,
            )
        return left, top

    def _clamp_map(self, left: int, top: int) -> tuple[int, int]:
        width, height = self.dungeon.w, self.dungeon.h
        if width <= MAP_VIEW_W:
            left = (width - MAP_VIEW_W) // 2
        else:
            left = min(max(0, left), width - MAP_VIEW_W)
        if height <= MAP_VIEW_H:
            top = (height - MAP_VIEW_H) // 2
        else:
            top = min(max(0, top), height - MAP_VIEW_H)
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
            self.player.x - MAP_VIEW_W // 2,
            self.player.y - MAP_VIEW_H // 2,
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
        """Выстрелить из лука по ближайшему видимому врагу."""
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
        self.player_acted()
        return True

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
            self.items.append(random_loot(enemy.x, enemy.y, self.depth))
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
        item = self.item_at(nx, ny)
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
        return True

    def open_trash(self) -> None:
        if not self.near_trash():
            self.msg("There is no trash bin nearby.", "warn")
            return
        self.trash_deposit_mode = False
        self.mode = MODE_TRASH

    def close_trash(self) -> None:
        if self.mode == MODE_TRASH:
            self.mode = MODE_PLAYING
        self.trash_deposit_mode = False

    def take_from_trash(self, index: int) -> bool:
        if not (0 <= index < len(self.trash_items)):
            return False
        item = self.trash_items[index]
        if item.kind == "gold":
            self.gold += item.value
            self.trash_items.pop(index)
            self.msg(f"You find {item.value} gold in the trash.", "gold")
            return True
        if not self.inventory.add(item):
            self.msg("Your pack is full.", "warn")
            return False
        self.trash_items.pop(index)
        self.msg(f"You take {item.name} from the trash.", "item")
        return True

    def teleport_player(self) -> bool:
        spots: list[tuple[int, int]] = []
        for y in range(self.dungeon.h):
            for x in range(self.dungeon.w):
                if (
                    self.walkable(x, y)
                    and not self.enemy_at(x, y)
                    and not self.chest_at(x, y)
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
        elif self.mode == MODE_PLAYING:
            self.mode = MODE_INVENTORY

    def restart(self) -> None:
        """Начать новый забег в том же слоте после смерти."""
        slot = self.slot if self.slot is not None else first_free_slot()
        self.__init__()
        self.slot = slot
        self.mode = MODE_PLAYING
        self.save()
