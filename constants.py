"""Размеры консоли, цвета и константы игры."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ASSET_DIR = ROOT / "assets"
TTF_PATH = ASSET_DIR / "DejaVuSansMono.ttf"
TILESET_PATH = ASSET_DIR / "dejavu16x16_gs_tc.png"

# Размер одной клетки TTF-шрифта. 12x20 близок к пропорциям DejaVu Sans Mono:
# буквы не «разъезжаются», а окно остаётся компактным (~840x660).
TILE_W = 12
TILE_H = 20

# Автоповтор клавиш (секунды): общий для всех систем и будущего ticking-режима.
KEY_REPEAT_DELAY = 0.30
KEY_REPEAT_INTERVAL = 0.12

# Видимая область карты (один «экран») и размер самого этажа. Этаж больше
# экрана: камера следует за игроком, а FOV и сохранения работают в мировых
# координатах.
VIEW_W, VIEW_H = 70, 22
MAP_W, MAP_H = 140, 60
STATUS_H = 1
LOG_H = 9
HINT_H = 1
SCREEN_W = VIEW_W
SCREEN_H = VIEW_H + STATUS_H + LOG_H + HINT_H
STATUS_Y = VIEW_H
LOG_Y = VIEW_H + STATUS_H
HINT_Y = SCREEN_H - 1

# Полноэкранная карта: рамка по краю и строка подсказок внизу.
MAP_VIEW_W = SCREEN_W - 2
MAP_VIEW_H = SCREEN_H - 4

FOV_RADIUS = 11  # радиус обзора; стены на краю подсвечиваются отдельно
MAX_DEPTH = 25

# Биомы: каждые пять этажей меняются имена и цвета стен/пола. Боссы стоят
# на последнем этаже каждого биома (5, 10, 15, 20, 25).
BIOME_SIZE = 5
BIOME_NAMES = (
    "Dungeon Halls",
    "Flooded Crypts",
    "Ember Forges",
    "Frozen Vaults",
    "Shadow Sanctum",
)
BIOME_COLORS = (
    ((135, 135, 155), (92, 92, 108)),
    ((85, 125, 145), (55, 85, 105)),
    ((165, 95, 75), (110, 62, 48)),
    ((155, 180, 205), (95, 120, 150)),
    ((125, 90, 145), (70, 52, 88)),
)


def biome_index(depth: int) -> int:
    """Индекс биома для глубины (0..len(BIOME_NAMES)-1)."""
    return max(0, min(len(BIOME_NAMES) - 1, (depth - 1) // BIOME_SIZE))


INVENTORY_CAPACITY = 26  # a-z
FIRE_RADIUS = 3
FIRE_DAMAGE = 12
AGGRO_RANGE = 7
LOG_HISTORY = 200

# Здоровье: частичное лечение как награда за прогресс.
LEVEL_UP_HEAL_RATIO = 0.30
LEVEL_UP_HEAL_MIN = 6
DESCEND_HEAL_RATIO = 0.30
DESCEND_HEAL_MIN = 6
BOSS_HEAL_RATIO = 0.25
BOSS_HEAL_MIN = 8

# Износ экипировки: оружие — за удар, броня — за каждое попадание.
ARMOR_WEAR_PER_HIT = 2

# Дальний бой: лук бьёт по ближайшему видимому врагу в этом радиусе.
PLAYER_RANGED_RANGE = 6

# Прицеливание: маркеры луча и выбранной цели.
AIM_PATH_CHAR = "·"
AIM_TARGET_CHAR = "X"

# Прочность снаряжения в контейнерах. В сундуках вещи чаще целые, в мусорке
# чаще уже потрёпанные; доля считается от максимальной прочности.
CHEST_GEAR_INTACT = 0.55
CHEST_GEAR_MIN_FRAC = 0.55
CHEST_GEAR_MAX_FRAC = 0.90
TRASH_GEAR_INTACT = 0.12
TRASH_GEAR_MIN_FRAC = 0.20
TRASH_GEAR_MAX_FRAC = 0.70

# Лечение растёт с глубиной, иначе к 20-му этажу зелья почти бесполезны.
POTION_HEAL_BASE = 12
POTION_HEAL_PER_DEPTH = 2
SCROLL_HEAL_BASE = 18
SCROLL_HEAL_PER_DEPTH = 1

# Поведение врагов.
ENEMY_RANGED_RANGE = 6
POISON_TURNS = 6
POISON_DAMAGE = 1
POISON_PER_DEPTH = 6  # +1 урон яда за каждые 6 этажей
SUMMON_COOLDOWN = 5
MAX_ENEMIES = 14

# Стаки: зелья и свитки занимают один слот и складываются в стопку.
STACK_LIMITS = {
    "potion": 8,
    "scroll": 4,
}

# Мусорка в углу комнаты.
TRASH_CHAR = "%"
TRASH_CAPACITY = 8
TRASH_LOOT_CHANCE = 0.5
TRASH_LOOT_MAX = 3

# Сундуки в особых комнатах.
CHEST_CHAR = "="
CHEST_CAPACITY = 8
CHEST_TRAP_CHANCE = 0.22
CHEST_TRAP_PER_DEPTH = 0.02
CHEST_TRAP_MAX = 0.45
CHEST_TRAP_BONUS_GUARDED = 0.08

# Торговец появляется в отдельной комнате на этажах 2, 6, 10, 14, 18, 22.
MERCHANT_CHAR = "&"
MERCHANT_DEPTH_STEP = 4
MERCHANT_DEPTH_OFFSET = 2
MERCHANT_CAPACITY = 8
SHOP_STOCK_MIN = 4
SHOP_STOCK_MAX = 7
REPAIR_COST_DIVISOR = 2  # 1 золотая монета за 2 восстановленные единицы

# Напольные ловушки. Часть пола скрыта до срабатывания или поиска.
TRAP_CHAR = "^"
TRAP_BASE_COUNT = 2
TRAP_PER_DEPTH = 4
TRAP_MAX = 9
TRAP_SPIKE_DAMAGE_BASE = 2
TRAP_SPIKE_DAMAGE_PER_DEPTH = 3
TRAP_DART_DAMAGE_BASE = 1
TRAP_DART_DAMAGE_PER_DEPTH = 5
TRAP_POISON_TURNS_BASE = 4
TRAP_POISON_TURNS_PER_DEPTH = 8
SEARCH_RADIUS = 1

# Секретные комнаты за потайными дверями.
SECRET_DOOR_CHAR = "/"
SECRET_ROOM_CHANCE = 0.6
SECRET_ROOM_EXTRA_DEPTH = 8
SECRET_ROOM_EXTRA_CHANCE = 0.2

# Алтарь в тихой комнате-святилище: одно использование за этаж.
ALTAR_CHAR = "_"
ALTAR_HEAL_RATIO = 0.30

# RGB
COLOR_WALL = (135, 135, 155)
COLOR_FLOOR = (92, 92, 108)
COLOR_WALL_DARK = (38, 38, 62)
COLOR_FLOOR_DARK = (22, 22, 40)
COLOR_PLAYER = (255, 255, 90)
COLOR_SPAWN = (110, 200, 255)
COLOR_ENEMY = (220, 70, 70)
COLOR_ITEM = (210, 90, 210)
COLOR_GOLD = (245, 205, 60)
COLOR_STAIRS = (80, 225, 120)
COLOR_TRASH = (165, 140, 100)
COLOR_TRASH_DARK = (62, 52, 38)
COLOR_CHEST = (225, 185, 90)
COLOR_CHEST_GUARDED = (225, 110, 90)
COLOR_MERCHANT = (100, 230, 190)
COLOR_SHOP_FLOOR = (68, 112, 96)
COLOR_TRAP = (235, 110, 95)
COLOR_TRAP_SPENT = (120, 85, 85)
COLOR_SECRET_DOOR = (220, 180, 120)
COLOR_SECRET_FLOOR = (88, 70, 110)
COLOR_ALTAR = (150, 235, 255)
COLOR_SHRINE_FLOOR = (66, 92, 118)
COLOR_AIM = (255, 240, 150)
COLOR_AIM_TARGET = (255, 100, 90)
COLOR_VAULT_FLOOR = (108, 98, 70)
COLOR_GUARDED_FLOOR = (104, 72, 72)
COLOR_CAMP_FLOOR = (78, 104, 82)
COLOR_HP = (90, 225, 220)
COLOR_HP_OK = (90, 225, 130)
COLOR_HP_MID = (245, 205, 80)
COLOR_HP_LOW = (245, 80, 80)
COLOR_XP = (150, 125, 245)
COLOR_MSG = (220, 220, 220)
COLOR_WARN = (255, 145, 80)
COLOR_GOOD = (120, 230, 140)
COLOR_DIM = (90, 90, 130)
COLOR_UI = (185, 185, 210)
COLOR_BG = (0, 0, 0)
COLOR_PANEL = (12, 12, 22)
COLOR_PANEL_LIGHT = (20, 20, 34)
COLOR_POTION = (255, 105, 120)
COLOR_POTION_ANTIDOTE = (120, 220, 140)
COLOR_POTION_STRENGTH = (235, 130, 70)
COLOR_POTION_IRON = (150, 175, 210)
COLOR_WEAPON = (205, 212, 230)
COLOR_ARMOR = (110, 170, 255)
COLOR_SCROLL = (225, 195, 140)
COLOR_SCROLL_LIGHTNING = (170, 200, 255)
COLOR_ENEMY_RAT = (165, 135, 100)
COLOR_ENEMY_BAT = (155, 150, 195)
COLOR_ENEMY_GOBLIN = (120, 205, 95)
COLOR_ENEMY_SKELETON = (225, 225, 205)
COLOR_ENEMY_SPIDER = (140, 200, 90)
COLOR_ENEMY_ORC = (230, 135, 60)
COLOR_ENEMY_CULTIST = (200, 80, 170)
COLOR_ENEMY_TROLL = (175, 105, 220)
COLOR_ENEMY_GOLEM = (150, 150, 150)
COLOR_ENEMY_DRAGON = (255, 70, 60)
COLOR_ENEMY_SHADOW = (175, 85, 255)

MODE_MENU = "menu"
MODE_SLOTS = "slots"
MODE_PAUSE = "pause"
MODE_PLAYING = "playing"
MODE_INVENTORY = "inventory"
MODE_TRASH = "trash"
MODE_CHEST = "chest"
MODE_SHOP = "shop"
MODE_AIM = "aim"
MODE_HELP = "help"
MODE_DEAD = "dead"
MODE_MAP = "map"
