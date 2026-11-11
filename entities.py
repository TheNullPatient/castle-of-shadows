"""Сущности, шаблоны врагов и предметов."""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from constants import (
    CHEST_GEAR_INTACT,
    CHEST_GEAR_MAX_FRAC,
    CHEST_GEAR_MIN_FRAC,
    COLOR_ARMOR,
    COLOR_ENEMY,
    COLOR_ENEMY_BAT,
    COLOR_ENEMY_CULTIST,
    COLOR_ENEMY_DRAGON,
    COLOR_ENEMY_GOBLIN,
    COLOR_ENEMY_GOLEM,
    COLOR_ENEMY_ORC,
    COLOR_ENEMY_RAT,
    COLOR_ENEMY_SHADOW,
    COLOR_ENEMY_SKELETON,
    COLOR_ENEMY_SPIDER,
    COLOR_ENEMY_TROLL,
    COLOR_GOLD,
    COLOR_ITEM,
    COLOR_PLAYER,
    COLOR_POTION,
    COLOR_POTION_ANTIDOTE,
    COLOR_POTION_IRON,
    COLOR_POTION_STRENGTH,
    COLOR_SCROLL,
    COLOR_SCROLL_LIGHTNING,
    COLOR_WEAPON,
    MERCHANT_CAPACITY,
    POTION_HEAL_BASE,
    POTION_HEAL_PER_DEPTH,
    SCROLL_HEAL_BASE,
    SCROLL_HEAL_PER_DEPTH,
    SHOP_STOCK_MAX,
    SHOP_STOCK_MIN,
    TRASH_GEAR_INTACT,
    TRASH_GEAR_MAX_FRAC,
    TRASH_GEAR_MIN_FRAC,
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
    behavior: str = "melee"
    cooldown: int = 0
    boss: bool = False

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
    quantity: int = 1
    durability: int = 0
    max_durability: int = 0
    map_open: bool = False

    def __post_init__(self) -> None:
        if self.max_durability > 0 and self.durability <= 0:
            self.durability = self.max_durability

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
            quantity=self.quantity,
            durability=self.durability,
            max_durability=self.max_durability,
            map_open=self.map_open,
        )

    def copy(self) -> Item:
        return self.copy_at(self.x, self.y)

    def split(self, amount: int) -> Item:
        """Отделить ``amount`` штук в новый предмет, уменьшив этот."""
        amount = max(1, min(amount, self.quantity))
        part = self.copy()
        part.quantity = amount
        part.map_open = False
        self.quantity -= amount
        return part


@dataclass
class Chest:
    """Сундук в особой комнате. Открывается шагом в его клетку."""

    x: int
    y: int
    guarded: bool = False
    opened: bool = False
    items: list[Item] = field(default_factory=list)


@dataclass
class Trap:
    """Напольная ловушка. Скрыта, пока не сработает или её не найдут."""

    x: int
    y: int
    kind: str
    revealed: bool = False
    armed: bool = True


ENEMY_TYPES = [
    ("r", "Rat", 4, 2, 0, 2, 0, "melee"),
    ("b", "Bat", 3, 2, 0, 2, 0, "fast"),
    ("g", "Goblin", 7, 3, 1, 4, 1, "melee"),
    ("s", "Skeleton", 8, 3, 1, 5, 1, "ranged"),
    ("o", "Orc", 12, 5, 1, 7, 2, "melee"),
    ("S", "Giant Spider", 9, 3, 0, 6, 2, "poison"),
    ("c", "Cultist", 10, 4, 1, 8, 3, "summoner"),
    ("t", "Troll", 20, 7, 2, 12, 3, "melee"),
    ("G", "Stone Golem", 28, 6, 5, 14, 4, "slow"),
    ("D", "Dragon", 40, 12, 3, 20, 5, "melee"),
]

ENEMY_COLORS = {
    "Rat": COLOR_ENEMY_RAT,
    "Bat": COLOR_ENEMY_BAT,
    "Goblin": COLOR_ENEMY_GOBLIN,
    "Skeleton": COLOR_ENEMY_SKELETON,
    "Orc": COLOR_ENEMY_ORC,
    "Giant Spider": COLOR_ENEMY_SPIDER,
    "Cultist": COLOR_ENEMY_CULTIST,
    "Troll": COLOR_ENEMY_TROLL,
    "Stone Golem": COLOR_ENEMY_GOLEM,
    "Dragon": COLOR_ENEMY_DRAGON,
}

ENEMY_BY_NAME = {kind[1]: kind for kind in ENEMY_TYPES}

# (износ оружия при ударе по врагу, износ брони при его попадании по игроку).
# Тяжёлые и бронированные противники быстрее портят снаряжение.
ENEMY_GEAR_WEAR = {
    "Rat": (1, 2),
    "Bat": (1, 2),
    "Goblin": (1, 2),
    "Skeleton": (2, 2),
    "Orc": (1, 3),
    "Giant Spider": (1, 2),
    "Cultist": (1, 2),
    "Troll": (2, 3),
    "Stone Golem": (3, 3),
    "Dragon": (2, 4),
    "Skeleton King": (2, 3),
    "Troll Chieftain": (2, 4),
    "Wyvern": (3, 4),
    "Lich": (2, 3),
    "Shadow Lord": (3, 4),
}

# Боссы биомов: появляются на этажах 5, 10, 15, 20 и 25 и охраняют лестницу.
BOSS_TYPES = [
    ("K", "Skeleton King", 45, 8, 3, 35, 5, "summoner"),
    ("T", "Troll Chieftain", 65, 11, 4, 55, 6, "melee"),
    ("W", "Wyvern", 85, 13, 4, 75, 7, "melee"),
    ("L", "Lich", 105, 14, 5, 100, 8, "summoner"),
    ("X", "Shadow Lord", 140, 16, 6, 150, 9, "ranged"),
]

BOSS_COLORS = {
    "Skeleton King": COLOR_ENEMY_SKELETON,
    "Troll Chieftain": COLOR_ENEMY_TROLL,
    "Wyvern": COLOR_ENEMY_DRAGON,
    "Lich": COLOR_ENEMY_CULTIST,
    "Shadow Lord": COLOR_ENEMY_SHADOW,
}

WEAPON_TABLE = [
    Item(
        "Dagger", ")", "weapon", COLOR_WEAPON, value=1, slot="weapon",
        max_durability=35,
    ),
    Item(
        "Shortsword", ")", "weapon", COLOR_WEAPON, value=2, slot="weapon",
        max_durability=50,
    ),
    Item(
        "Battleaxe", ")", "weapon", COLOR_WEAPON, value=3, slot="weapon",
        max_durability=65,
    ),
    Item(
        "Spear", ")", "weapon", COLOR_WEAPON, value=2, slot="weapon",
        max_durability=60,
    ),
    Item(
        "Warhammer", ")", "weapon", COLOR_WEAPON, value=4, slot="weapon",
        max_durability=40,
    ),
    Item(
        "Runed Blade", ")", "weapon", COLOR_WEAPON, value=5, slot="weapon",
        max_durability=90,
    ),
    Item(
        "Dragonfang", ")", "weapon", COLOR_WEAPON, value=6, slot="weapon",
        max_durability=120,
    ),
]

# Луки не дают бонуса в ближнем бою, зато стреляют по ближайшему видимому
# врагу. Каждый выстрел тратит прочность, стрелы как отдельный ресурс не нужны.
BOW_TABLE = [
    Item(
        "Shortbow", "}", "weapon", COLOR_WEAPON, value=3, slot="weapon",
        max_durability=45, effect="ranged",
    ),
    Item(
        "Longbow", "}", "weapon", COLOR_WEAPON, value=5, slot="weapon",
        max_durability=65, effect="ranged",
    ),
]

ARMOR_TABLE = [
    Item(
        "Leather Armor", "[", "armor", COLOR_ARMOR, value=1, slot="armor",
        max_durability=45,
    ),
    Item(
        "Chain Mail", "[", "armor", COLOR_ARMOR, value=2, slot="armor",
        max_durability=65,
    ),
    Item(
        "Plate Mail", "[", "armor", COLOR_ARMOR, value=4, slot="armor",
        max_durability=70,
    ),
    Item(
        "Mithril Plate", "[", "armor", COLOR_ARMOR, value=5, slot="armor",
        max_durability=110,
    ),
    Item(
        "Dragonscale", "[", "armor", COLOR_ARMOR, value=6, slot="armor",
        max_durability=140,
    ),
]

SCROLL_TABLE = [
    Item("Scroll of Teleport", "?", "scroll", COLOR_SCROLL, effect="teleport"),
    Item("Scroll of Mapping", "?", "scroll", COLOR_SCROLL, effect="mapping"),
    Item("Scroll of Fire", "?", "scroll", COLOR_SCROLL, effect="fire"),
    Item(
        "Scroll of Healing", "?", "scroll", COLOR_SCROLL,
        value=20, effect="healing",
    ),
    Item(
        "Scroll of Lightning", "?", "scroll", COLOR_SCROLL_LIGHTNING,
        value=18, effect="lightning",
    ),
]

POTION_TABLE = [
    # Health potions встречаются чаще остальных (3 из 6).
    Item(
        "Health Potion", "!", "potion", COLOR_POTION,
        value=15, effect="health",
    ),
    Item(
        "Health Potion", "!", "potion", COLOR_POTION,
        value=15, effect="health",
    ),
    Item(
        "Health Potion", "!", "potion", COLOR_POTION,
        value=15, effect="health",
    ),
    Item(
        "Antidote Potion", "!", "potion", COLOR_POTION_ANTIDOTE,
        effect="antidote",
    ),
    Item(
        "Potion of Strength", "!", "potion", COLOR_POTION_STRENGTH,
        value=1, effect="strength",
    ),
    Item(
        "Potion of Iron Skin", "!", "potion", COLOR_POTION_IRON,
        value=1, effect="ironskin",
    ),
]


def make_player(x: int, y: int) -> Entity:
    return Entity(x, y, "@", "Hero", 30, 30, 5, 2, COLOR_PLAYER, speed=100)


def enemy_pool(depth: int) -> list[tuple]:
    """Враги, уместные на текущей глубине.

    Верхняя граница открывает новые тиры примерно каждые четыре этажа,
    нижняя — убирает крыс и летучих мышей с поздних этажей, чтобы там
    встречались действительно опасные противники, а не «мусор».
    """
    cap = min(5, 1 + depth // 4)
    lower = max(0, cap - 2)
    pool = [kind for kind in ENEMY_TYPES if lower <= kind[6] <= cap]
    return pool or [ENEMY_TYPES[0]]


def make_enemy(kind: tuple, x: int, y: int, depth: int) -> Entity:
    ch, name, hp, atk, df, xp, _tier, behavior = kind
    hp += depth + depth // 2
    atk += depth // 2
    xp += depth
    color = ENEMY_COLORS.get(name, COLOR_ENEMY)
    return Entity(
        x, y, ch, name, hp, hp, atk, df, color, xp,
        speed=100, behavior=behavior,
    )


def make_boss(kind: tuple, x: int, y: int, depth: int) -> Entity:
    """Босс биома: заметно крепче обычных врагов и всегда помечен."""
    ch, name, hp, atk, df, xp, _tier, behavior = kind
    hp += depth * 2
    atk += depth // 2
    color = BOSS_COLORS.get(name, COLOR_ENEMY)
    return Entity(
        x, y, ch, name, hp, hp, atk, df, color, xp + depth * 2,
        speed=100, behavior=behavior, boss=True,
    )


def _weapon_pool(depth: int) -> list[Item]:
    if depth < 4:
        return WEAPON_TABLE[:3]
    if depth < 10:
        return WEAPON_TABLE[1:5]
    if depth < 16:
        return WEAPON_TABLE[2:6]
    if depth < 22:
        return WEAPON_TABLE[3:7]
    return WEAPON_TABLE[4:]


def _bow_pool(depth: int) -> list[Item]:
    if depth < 8:
        return BOW_TABLE[:1]
    return BOW_TABLE


def _armor_pool(depth: int) -> list[Item]:
    if depth < 5:
        return ARMOR_TABLE[:2]
    if depth < 10:
        return ARMOR_TABLE[1:3]
    if depth < 16:
        return ARMOR_TABLE[2:4]
    return ARMOR_TABLE[3:]


def _scale_consumable(item: Item, depth: int) -> Item:
    """Поднять лечение зелий и свитков под текущую глубину."""
    if item.effect == "health" and item.kind == "potion":
        item.value = POTION_HEAL_BASE + depth * POTION_HEAL_PER_DEPTH
    elif item.effect == "healing" and item.kind == "scroll":
        item.value = SCROLL_HEAL_BASE + depth * SCROLL_HEAL_PER_DEPTH
    return item


def _age_gear(
    item: Item,
    intact_chance: float,
    min_frac: float,
    max_frac: float,
) -> Item:
    """Случайно износить снаряжение в контейнере."""
    if item.kind not in ("weapon", "armor") or item.max_durability <= 0:
        return item
    if random.random() < intact_chance:
        item.durability = item.max_durability
    else:
        frac = random.uniform(min_frac, max_frac)
        item.durability = max(1, int(item.max_durability * frac))
    return item


def age_chest_gear(item: Item) -> Item:
    return _age_gear(
        item,
        CHEST_GEAR_INTACT,
        CHEST_GEAR_MIN_FRAC,
        CHEST_GEAR_MAX_FRAC,
    )


def age_trash_gear(item: Item) -> Item:
    return _age_gear(
        item,
        TRASH_GEAR_INTACT,
        TRASH_GEAR_MIN_FRAC,
        TRASH_GEAR_MAX_FRAC,
    )


def random_loot(x: int, y: int, depth: int) -> Item:
    roll = random.random()
    if roll < 0.28:
        return Item("Gold", "$", "gold", COLOR_GOLD, x, y, random.randint(3, 8 + depth))
    if roll < 0.55:
        item = random.choice(POTION_TABLE).copy_at(x, y)
        return _scale_consumable(item, depth)
    if roll < 0.70:
        if depth >= 2 and random.random() < 0.28:
            return random.choice(_bow_pool(depth)).copy_at(x, y)
        return random.choice(_weapon_pool(depth)).copy_at(x, y)
    if roll < 0.86:
        return random.choice(_armor_pool(depth)).copy_at(x, y)
    item = random.choice(SCROLL_TABLE).copy_at(x, y)
    return _scale_consumable(item, depth)


def make_chest_loot(depth: int, guarded: bool = False) -> list[Item]:
    """Содержимое сундука: золото плюс 2-4 предмета по глубине."""
    low = 10 + depth * 3
    high = 18 + depth * 5
    gold = random.randint(low, high)
    if guarded:
        gold = int(gold * 1.5)

    items: list[Item] = []
    count = random.randint(2, 3) + (1 if guarded else 0)
    for _ in range(count):
        roll = random.random()
        if roll < 0.36:
            items.append(
                _scale_consumable(
                    random.choice(POTION_TABLE).copy(),
                    depth,
                )
            )
        elif roll < 0.65:
            items.append(
                _scale_consumable(
                    random.choice(SCROLL_TABLE).copy(),
                    depth,
                )
            )
        elif random.random() < 0.5:
            if depth >= 2 and random.random() < 0.28:
                gear = random.choice(_bow_pool(depth)).copy()
            else:
                gear = random.choice(_weapon_pool(depth)).copy()
            items.append(age_chest_gear(gear))
        else:
            items.append(
                age_chest_gear(random.choice(_armor_pool(depth)).copy())
            )

    return [
        Item("Gold", "$", "gold", COLOR_GOLD, value=gold),
        *items,
    ]


_SCROLL_PRICES = {
    "teleport": 35,
    "mapping": 25,
    "fire": 42,
    "healing": 32,
    "lightning": 48,
}


def shop_price(item: Item, depth: int) -> int:
    """Цена одной единицы товара у торговца."""
    if item.kind == "potion":
        if item.effect == "health":
            return 16 + depth * 2
        if item.effect == "antidote":
            return 12 + depth
        if item.effect in ("strength", "ironskin"):
            return 80 + depth * 6
    if item.kind == "scroll":
        return _SCROLL_PRICES.get(item.effect, 30) + depth * 2
    if item.kind in ("weapon", "armor"):
        return 35 + item.value * 24 + depth * 6
    return max(1, item.value)


def _scaled_stack(template: Item, depth: int, quantity: int) -> Item:
    item = template.copy()
    item.quantity = quantity
    return _scale_consumable(item, depth)


def make_merchant_stock(depth: int) -> list[Item]:
    """Ассортимент торговца: расходники, иногда снаряжение."""
    stock: list[Item] = []
    health = next(item for item in POTION_TABLE if item.effect == "health")
    antidote = next(item for item in POTION_TABLE if item.effect == "antidote")
    stock.append(
        _scaled_stack(health, depth, 2 + (1 if depth >= 10 else 0))
    )
    if random.random() < 0.8:
        stock.append(_scaled_stack(antidote, depth, 1))
    buffs = [
        item
        for item in POTION_TABLE
        if item.effect in ("strength", "ironskin")
    ]
    if random.random() < 0.45:
        stock.append(_scaled_stack(random.choice(buffs), depth, 1))
    for scroll in random.sample(SCROLL_TABLE, k=2):
        stock.append(_scaled_stack(scroll, depth, 1))
    cap = min(MERCHANT_CAPACITY, SHOP_STOCK_MAX)
    if random.random() < 0.6 and len(stock) < cap:
        if depth >= 2 and random.random() < 0.22:
            gear = random.choice(_bow_pool(depth)).copy()
        elif random.random() < 0.6:
            gear = random.choice(_weapon_pool(depth)).copy()
        else:
            gear = random.choice(_armor_pool(depth)).copy()
        stock.append(gear)
    while len(stock) < SHOP_STOCK_MIN:
        stock.append(
            _scaled_stack(random.choice(POTION_TABLE), depth, 1)
        )
    merged: list[Item] = []
    for item in stock:
        if item.kind in ("potion", "scroll"):
            for existing in merged:
                if (
                    existing.kind == item.kind
                    and existing.name == item.name
                    and existing.effect == item.effect
                ):
                    existing.quantity += item.quantity
                    break
            else:
                merged.append(item)
        else:
            merged.append(item)
    return merged[:cap]
