"""Состояние игры: ходы, бой, FOV, спуск, статистика."""
from __future__ import annotations

import random

import numpy as np
import tcod.map
import tcod.path
from tcod.constants import FOV_SYMMETRIC_SHADOWCAST

from constants import (
    AGGRO_RANGE,
    COLOR_ENEMY,
    COLOR_GOOD,
    COLOR_GOLD,
    COLOR_HP,
    COLOR_ITEM,
    COLOR_MSG,
    COLOR_WARN,
    FOV_RADIUS,
    LOG_H,
    LOG_HISTORY,
    MAP_H,
    MAP_W,
    MAX_DEPTH,
    MODE_DEAD,
    MODE_HELP,
    MODE_INVENTORY,
    MODE_PLAYING,
    MODE_TRASH,
    TRASH_CAPACITY,
    TRASH_CHAR,
    TRASH_LOOT_CHANCE,
    TRASH_LOOT_MAX,
)
from dungeon import Dungeon
from entities import ENEMY_TYPES, Entity, Item, make_enemy, make_player, random_loot
from inventory import Inventory

MSG_COLORS = {
    "msg": COLOR_MSG,
    "item": COLOR_ITEM,
    "gold": COLOR_GOLD,
    "enemy": COLOR_ENEMY,
    "warn": COLOR_WARN,
    "heal": COLOR_GOOD,
    "good": COLOR_HP,
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
    def __init__(self) -> None:
        self.mode = MODE_PLAYING
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
        self.killed_by = ""
        self.enemies: list[Entity] = []
        self.items: list[Item] = []
        self.trash_pos: tuple[int, int] | None = None
        self.trash_items: list[Item] = []
        self.discard_mode = False
        self.visible = np.zeros((MAP_W, MAP_H), dtype=bool, order="F")
        self.explored = np.zeros((MAP_W, MAP_H), dtype=bool, order="F")
        self.dungeon: Dungeon
        self.new_level(first=True)
        self.msg("Welcome, Hero! Find '>' and descend 10 levels.")
        self.msg('Press "?" for help. i: inventory. . : wait.')

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

    def new_level(self, first: bool = False) -> None:
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
                self.player.hp = self.player.max_hp

        rl = self.dungeon.rooms[-1]
        self.stairs = (rl[0] + rl[2] // 2, rl[1] + rl[3] // 2)
        self.dungeon.grid[self.stairs[1]][self.stairs[0]] = ">"

        self.enemies = []
        self.items = []
        self.trash_items = []
        self.trash_pos = self._place_trash()
        self._spawn_enemies()
        self._spawn_items()
        self._spawn_trash_loot()
        self.explored = np.zeros((MAP_W, MAP_H), dtype=bool, order="F")
        self.update_fov()

    def _place_trash(self) -> tuple[int, int] | None:
        """Поставить мусорку в угол случайной комнаты."""
        corners: list[tuple[int, int]] = []
        for x, y, w, h in self.dungeon.rooms:
            for corner in (
                (x, y),
                (x + w - 1, y),
                (x, y + h - 1),
                (x + w - 1, y + h - 1),
            ):
                if corner == self.stairs:
                    continue
                if self.player and corner == (self.player.x, self.player.y):
                    continue
                corners.append(corner)
        if not corners:
            return None
        pos = random.choice(corners)
        self.dungeon.grid[pos[1]][pos[0]] = TRASH_CHAR
        return pos

    def _spawn_enemies(self) -> None:
        num = 3 + self.depth
        pool = [e for e in ENEMY_TYPES if e[6] <= self.depth // 2 + 1] or [ENEMY_TYPES[0]]
        for _ in range(num):
            pos = self._free_spot()
            if pos is None:
                continue
            kind = random.choice(pool)
            self.enemies.append(make_enemy(kind, pos[0], pos[1], self.depth))

    def _spawn_items(self) -> None:
        for _ in range(random.randint(3, 6)):
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
            self.trash_items.append(
                random_loot(
                    self.trash_pos[0],
                    self.trash_pos[1],
                    self.depth,
                )
            )

    def _free_spot(self) -> tuple[int, int] | None:
        rooms = self.dungeon.rooms[1:] or self.dungeon.rooms
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
        trans = np.zeros((MAP_W, MAP_H), dtype=bool, order="F")
        for y in range(MAP_H):
            row = self.dungeon.grid[y]
            for x in range(MAP_W):
                trans[x, y] = row[x] != "#"
        self.visible = tcod.map.compute_fov(
            trans,
            (self.player.x, self.player.y),
            radius=FOV_RADIUS,
            light_walls=True,
            algorithm=FOV_SYMMETRIC_SHADOWCAST,
        )
        self.explored |= self.visible

    def attack(self, attacker: Entity, defender: Entity) -> None:
        atk = self.total_atk if attacker is self.player else attacker.atk
        df = self.total_df if defender is self.player else defender.df
        dmg = max(1, atk - df + random.randint(-1, 2))
        defender.hp -= dmg
        if attacker is self.player:
            self.msg(f"You hit {defender.name} for {dmg}.")
            self._wear_equipment(self.inventory.weapon)
        else:
            self.msg(f"{attacker.name} hits you for {dmg}.", "enemy")
            if defender is self.player:
                self._wear_equipment(self.inventory.armor)

        if not defender.alive():
            if defender is self.player:
                self.killed_by = attacker.name
                self.msg("You died!", "enemy")
                self.finish(win=False)
            else:
                self.msg(f"{defender.name} dies! (+{defender.xp} XP)")
                self.enemies.remove(defender)
                self.kills += 1
                self.player_xp += defender.xp
                self._check_level_up()

    def _wear_equipment(self, item: Item | None) -> None:
        """Износить оружие/броню на единицу и сломать при нуле."""
        if item is None or item.max_durability <= 0:
            return
        item.durability = max(0, item.durability - 1)
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

    def _check_level_up(self) -> None:
        while self.player_xp >= self.xp_next:
            self.player_xp -= self.xp_next
            self.xp_next = int(self.xp_next * 1.5)
            self.player_level += 1
            self.player.max_hp += 5
            self.player.hp = self.player.max_hp
            self.player.atk += 1
            if self.player_level % 2 == 0:
                self.player.df += 1
            self.msg(f"*** Level up! LV {self.player_level} ***", "good")

    def player_acted(self) -> None:
        if self.game_over:
            return
        self.turns += 1
        self.enemy_turn()
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
        if not self.walkable(nx, ny):
            return
        self.player.x, self.player.y = nx, ny
        item = self.item_at(nx, ny)
        if item:
            self.pickup(item)
        if (nx, ny) == self.trash_pos:
            self.msg(
                f"There is a trash bin here "
                f"({len(self.trash_items)}/{TRASH_CAPACITY}). Press Tab to look inside."
            )
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
        if self.inventory.use(index, self):
            self.player_acted()
            return True
        return False

    def on_trash(self) -> bool:
        return self.trash_pos is not None and (
            self.player.x,
            self.player.y,
        ) == self.trash_pos

    def discard_item(self, index: int) -> bool:
        """Выбросить предмет из рюкзака в мусорку под ногами."""
        if not (0 <= index < len(self.inventory.items)):
            return False
        if not self.on_trash():
            self.msg(
                "You can only throw items away at the trash bin.",
                "warn",
            )
            return False
        if len(self.trash_items) >= TRASH_CAPACITY:
            self.msg(
                f"The trash is full ({TRASH_CAPACITY}/{TRASH_CAPACITY}).",
                "warn",
            )
            return False
        item = self.inventory.remove(index)
        self.trash_items.append(item)
        self.msg(
            f"You throw {item.name} into the trash. "
            f"({len(self.trash_items)}/{TRASH_CAPACITY})",
            "item",
        )
        return True

    def open_trash(self) -> None:
        if not self.on_trash():
            self.msg("There is no trash bin here.", "warn")
            return
        self.discard_mode = False
        self.mode = MODE_TRASH

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
        for y in range(MAP_H):
            for x in range(MAP_W):
                if self.walkable(x, y) and not self.enemy_at(x, y) and (x, y) != (self.player.x, self.player.y):
                    spots.append((x, y))
        if not spots:
            return False
        self.player.x, self.player.y = random.choice(spots)
        return True

    def reveal_map(self) -> None:
        for y in range(MAP_H):
            for x in range(MAP_W):
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
                self.msg(f"{e.name} dies! (+{e.xp} XP)")
                self.enemies.remove(e)
                self.kills += 1
                self.player_xp += e.xp
                self._check_level_up()
        return hits

    def _path_cost(self) -> np.ndarray:
        cost = np.zeros((MAP_W, MAP_H), dtype=np.int8, order="F")
        for y in range(MAP_H):
            for x in range(MAP_W):
                if self.dungeon.grid[y][x] != "#":
                    cost[x, y] = 1
        for e in self.enemies:
            cost[e.x, e.y] = 0
        cost[self.player.x, self.player.y] = 1
        return cost

    def enemy_turn(self) -> None:
        cost = self._path_cost()
        for e in self.enemies[:]:
            if self.game_over:
                return
            dist = abs(self.player.x - e.x) + abs(self.player.y - e.y)
            if dist == 1:
                self.attack(e, self.player)
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
                self.attack(e, self.player)
                continue
            if self.walkable(nx, ny) and not self.enemy_at(nx, ny):
                e.x, e.y = nx, ny

    def descend(self) -> None:
        if (self.player.x, self.player.y) != self.stairs:
            self.msg('You must stand on ">" to descend.')
            return
        if self.depth >= MAX_DEPTH:
            self.msg("*** You escape the Castle of Shadows! VICTORY! ***", "good")
            self.finish(win=True)
            return
        self.depth += 1
        self.msg(f"You descend to depth {self.depth}.")
        self.new_level()

    def finish(self, win: bool = False, quit_requested: bool = False) -> None:
        self.win = win
        self.quit_requested = quit_requested
        self.game_over = True
        self.discard_mode = False
        self.mode = MODE_DEAD

    def toggle_help(self) -> None:
        self.mode = MODE_PLAYING if self.mode == MODE_HELP else MODE_HELP

    def toggle_inventory(self) -> None:
        if self.mode == MODE_INVENTORY:
            self.discard_mode = False
            self.mode = MODE_PLAYING
        elif self.mode == MODE_PLAYING:
            self.discard_mode = False
            self.mode = MODE_INVENTORY

    def restart(self) -> None:
        """Начать новую игру, сохранив тот же объект Game для главного цикла."""
        self.__init__()
