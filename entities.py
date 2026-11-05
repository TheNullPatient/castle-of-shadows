"""Сущности, шаблоны врагов и предметов."""
from __future__ import annotations

import random
from dataclasses import dataclass

from constants import (
    COLOR_ARMOR,
    COLOR_ENEMY,
    COLOR_ENEMY_DRAGON,
    COLOR_ENEMY_GOBLIN,
    COLOR_ENEMY_ORC,
    COLOR_ENEMY_RAT,
    COLOR_ENEMY_TROLL,
    COLOR_GOLD,
    COLOR_ITEM,
    COLOR_PLAYER,
    COLOR_POTION,
    COLOR_SCROLL,
    COLOR_WEAPON,
)


@dataclass
class Entity:
    x: int
    y: int
    char: str
    name: str
    hp: int
    max_hp: int
    atk: int
    df: int
    color: tuple[int, int, int] = COLOR_ENEMY
    xp: int = 0
    speed: int = 100

    def alive(self) -> bool:
        return self.hp > 0


@dataclass
class Item:
    name: str
    char: str
    kind: str
    color: tuple[int, int, int] = COLOR_ITEM
    x: int = 0
    y: int = 0
    value: int = 0
    effect: str = ""
    slot: str = ""
    identified: bool = True

    def copy_at(self, x: int, y: int) -> Item:
        return Item(
            name=self.name,
            char=self.char,
            kind=self.kind,
            color=self.color,
            x=x,
            y=y,
            value=self.value,
            effect=self.effect,
            slot=self.slot,
            identified=self.identified,
        )


ENEMY_TYPES = [
    ("r", "Rat", 4, 2, 0, 2, 0),
    ("g", "Goblin", 7, 3, 1, 4, 1),
    ("o", "Orc", 12, 5, 1, 7, 2),
    ("t", "Troll", 20, 7, 2, 12, 3),
    ("D", "Dragon", 40, 12, 3, 20, 5),
]

ENEMY_COLORS = {
    "Rat": COLOR_ENEMY_RAT,
    "Goblin": COLOR_ENEMY_GOBLIN,
    "Orc": COLOR_ENEMY_ORC,
    "Troll": COLOR_ENEMY_TROLL,
    "Dragon": COLOR_ENEMY_DRAGON,
}

WEAPON_TABLE = [
    Item("Dagger", ")", "weapon", COLOR_WEAPON, value=1, slot="weapon"),
    Item("Shortsword", ")", "weapon", COLOR_WEAPON, value=2, slot="weapon"),
    Item("Battleaxe", ")", "weapon", COLOR_WEAPON, value=3, slot="weapon"),
]

ARMOR_TABLE = [
    Item("Leather Armor", "[", "armor", COLOR_ARMOR, value=1, slot="armor"),
    Item("Chain Mail", "[", "armor", COLOR_ARMOR, value=2, slot="armor"),
]

SCROLL_TABLE = [
    Item("Scroll of Teleport", "?", "scroll", COLOR_SCROLL, effect="teleport"),
    Item("Scroll of Mapping", "?", "scroll", COLOR_SCROLL, effect="mapping"),
    Item("Scroll of Fire", "?", "scroll", COLOR_SCROLL, effect="fire"),
]


def make_player(x: int, y: int) -> Entity:
    return Entity(x, y, "@", "Hero", 30, 30, 5, 2, COLOR_PLAYER, speed=100)


def make_enemy(kind: tuple, x: int, y: int, depth: int) -> Entity:
    ch, name, hp, atk, df, xp, _tier = kind
    hp += depth
    atk += depth // 2
    color = ENEMY_COLORS.get(name, COLOR_ENEMY)
    return Entity(x, y, ch, name, hp, hp, atk, df, color, xp, speed=100)


def random_loot(x: int, y: int, depth: int) -> Item:
    roll = random.random()
    if roll < 0.28:
        return Item("Gold", "$", "gold", COLOR_GOLD, x, y, random.randint(3, 8 + depth))
    if roll < 0.55:
        return Item("Health Potion", "!", "potion", COLOR_POTION, x, y, 15)
    if roll < 0.72:
        pool = WEAPON_TABLE if depth < 4 else WEAPON_TABLE[1:]
        return random.choice(pool).copy_at(x, y)
    if roll < 0.86:
        return random.choice(ARMOR_TABLE).copy_at(x, y)
    return random.choice(SCROLL_TABLE).copy_at(x, y)
