"""Сохранение и загрузка текущего забега в JSON."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import numpy as np

from constants import (
    COLOR_ITEM,
    LOG_HISTORY,
    MAP_H,
    MAP_W,
    MODE_PLAYING,
    ROOT,
)
from dungeon import Dungeon
from entities import Chest, Entity, Item

SAVE_DIR = ROOT / "saves"
SAVE_VERSION = 1
SLOT_COUNT = 5

_LEGACY_MIGRATED = False


# --- низкоуровневый доступ к слотам ----------------------------------------


def slot_path(slot: int) -> Path:
    """Путь к файлу слота (1..SLOT_COUNT)."""
    return SAVE_DIR / f"slot{slot}.json"


def _legacy_path() -> Path:
    """Старое одиночное сохранение, которое переносим в первый слот."""
    return SAVE_DIR.parent / "savegame.json"


def _ensure_dir() -> None:
    global _LEGACY_MIGRATED
    try:
        SAVE_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    if _LEGACY_MIGRATED:
        return
    _LEGACY_MIGRATED = True
    legacy = _legacy_path()
    first = slot_path(1)
    if legacy.is_file() and not first.exists():
        try:
            legacy.replace(first)
        except OSError:
            pass


def _read_payload(slot: int) -> dict[str, Any] | None:
    if not 1 <= slot <= SLOT_COUNT:
        return None
    _ensure_dir()
    try:
        raw = slot_path(slot).read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return None
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("version") != SAVE_VERSION:
        return None
    if not isinstance(data.get("state"), dict):
        return None
    return data


def read_save(slot: int) -> dict[str, Any] | None:
    """Прочитать сохранение слота. None, если файла нет или он не подходит."""
    payload = _read_payload(slot)
    if payload is None:
        return None
    state = payload["state"]
    state["saved_at"] = float(payload.get("saved_at", 0.0))
    return state


def has_save(slot: int) -> bool:
    """Есть ли пригодное сохранение в слоте."""
    return read_save(slot) is not None


def slot_info(slot: int) -> dict[str, Any] | None:
    """Краткая информация о слоте для меню."""
    state = read_save(slot)
    if state is None:
        return None
    stats = state.get("stats", {})
    return {
        "slot": slot,
        "depth": int(state.get("depth", 1)),
        "turns": int(stats.get("turns", 0)),
        "player_level": int(stats.get("player_level", 1)),
        "gold": int(stats.get("gold", 0)),
        "saved_at": float(state.get("saved_at", 0.0)),
    }


def list_slots() -> list[dict[str, Any] | None]:
    """Все слоты по порядку; пустой слот — None."""
    _ensure_dir()
    return [slot_info(slot) for slot in range(1, SLOT_COUNT + 1)]


def has_any_save() -> bool:
    return any(info is not None for info in list_slots())


def first_free_slot() -> int | None:
    for index, info in enumerate(list_slots(), start=1):
        if info is None:
            return index
    return None


def latest_slot() -> int | None:
    saved = [info for info in list_slots() if info is not None]
    if not saved:
        return None
    return int(max(saved, key=lambda info: info["saved_at"])["slot"])


def write_save(slot: int, state: dict[str, Any]) -> None:
    """Атомарно записать сохранение слота."""
    if not 1 <= slot <= SLOT_COUNT:
        raise ValueError(f"invalid save slot: {slot}")
    _ensure_dir()
    payload = {
        "version": SAVE_VERSION,
        "saved_at": time.time(),
        "state": state,
    }
    target = slot_path(slot)
    tmp = SAVE_DIR / f".slot{slot}.tmp"
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, target)


def delete_save(slot: int) -> None:
    """Удалить сохранение слота, если оно есть."""
    if not 1 <= slot <= SLOT_COUNT:
        return
    try:
        slot_path(slot).unlink()
    except OSError:
        pass


# --- сериализация сущностей -------------------------------------------------


def _color(data: Any, default: tuple[int, int, int]) -> tuple[int, int, int]:
    if isinstance(data, (list, tuple)) and len(data) == 3:
        try:
            return (int(data[0]), int(data[1]), int(data[2]))
        except (TypeError, ValueError):
            return default
    return default


def item_to_dict(item: Item) -> dict[str, Any]:
    return {
        "name": item.name,
        "char": item.char,
        "kind": item.kind,
        "color": list(item.color),
        "x": item.x,
        "y": item.y,
        "value": item.value,
        "effect": item.effect,
        "slot": item.slot,
        "identified": item.identified,
        "quantity": item.quantity,
        "durability": item.durability,
        "max_durability": item.max_durability,
    }


def item_from_dict(data: dict[str, Any]) -> Item:
    return Item(
        name=str(data["name"]),
        char=str(data["char"]),
        kind=str(data["kind"]),
        color=_color(data.get("color"), COLOR_ITEM),
        x=int(data.get("x", 0)),
        y=int(data.get("y", 0)),
        value=int(data.get("value", 0)),
        effect=str(data.get("effect", "")),
        slot=str(data.get("slot", "")),
        identified=bool(data.get("identified", True)),
        quantity=int(data.get("quantity", 1)),
        durability=int(data.get("durability", 0)),
        max_durability=int(data.get("max_durability", 0)),
    )


def entity_to_dict(entity: Entity) -> dict[str, Any]:
    return {
        "x": entity.x,
        "y": entity.y,
        "char": entity.char,
        "name": entity.name,
        "hp": entity.hp,
        "max_hp": entity.max_hp,
        "atk": entity.atk,
        "df": entity.df,
        "color": list(entity.color),
        "xp": entity.xp,
        "speed": entity.speed,
        "behavior": entity.behavior,
        "cooldown": entity.cooldown,
    }


def entity_from_dict(data: dict[str, Any]) -> Entity:
    return Entity(
        x=int(data["x"]),
        y=int(data["y"]),
        char=str(data["char"]),
        name=str(data["name"]),
        hp=int(data["hp"]),
        max_hp=int(data["max_hp"]),
        atk=int(data["atk"]),
        df=int(data["df"]),
        color=_color(data.get("color"), COLOR_ITEM),
        xp=int(data.get("xp", 0)),
        speed=int(data.get("speed", 100)),
        behavior=str(data.get("behavior", "melee")),
        cooldown=int(data.get("cooldown", 0)),
    )


def chest_to_dict(chest: Chest) -> dict[str, Any]:
    return {
        "x": chest.x,
        "y": chest.y,
        "guarded": chest.guarded,
        "opened": chest.opened,
        "items": [item_to_dict(item) for item in chest.items],
    }


def chest_from_dict(data: dict[str, Any]) -> Chest:
    return Chest(
        int(data["x"]),
        int(data["y"]),
        bool(data.get("guarded", False)),
        bool(data.get("opened", False)),
        [item_from_dict(item) for item in data.get("items", [])],
    )


# --- снимок и восстановление игры ------------------------------------------


def _equipment_index(items: list[Item], target: Item | None) -> int:
    if target is None:
        return -1
    for index, item in enumerate(items):
        if item is target:
            return index
    return -1


def build_state(game: Any) -> dict[str, Any]:
    """Собрать сериализуемое состояние текущего забега."""
    inventory = game.inventory
    w, h = game.dungeon.w, game.dungeon.h
    return {
        "depth": game.depth,
        "player": entity_to_dict(game.player),
        "inventory": {
            "capacity": inventory.capacity,
            "items": [item_to_dict(item) for item in inventory.items],
            "weapon": _equipment_index(inventory.items, inventory.weapon),
            "armor": _equipment_index(inventory.items, inventory.armor),
        },
        "stairs": list(game.stairs),
        "stats": {
            "player_level": game.player_level,
            "player_xp": game.player_xp,
            "xp_next": game.xp_next,
            "gold": game.gold,
            "kills": game.kills,
            "turns": game.turns,
            "killed_by": game.killed_by,
            "poison_turns": game.poison_turns,
            "poison_damage": game.poison_damage,
            "regen_counter": game.regen_counter,
        },
        "enemies": [entity_to_dict(enemy) for enemy in game.enemies],
        "items": [item_to_dict(item) for item in game.items],
        "trash": {
            "pos": list(game.trash_pos) if game.trash_pos else None,
            "items": [item_to_dict(item) for item in game.trash_items],
            "noticed": game.trash_noticed,
        },
        "chests": [chest_to_dict(chest) for chest in game.chests],
        "special_rooms": [list(entry) for entry in game.special_rooms],
        "special_room_seen": [
            list(entry) for entry in game.special_room_seen
        ],
        "hints": {
            "chest_hinted": game.chest_hinted,
        },
        "dungeon": {
            "w": w,
            "h": h,
            "grid": ["".join(row) for row in game.dungeon.grid],
            "rooms": [list(room) for room in game.dungeon.rooms],
        },
        "explored": [
            "".join(
                "1" if game.explored[x, y] else "0" for x in range(w)
            )
            for y in range(h)
        ],
        "log": [list(message) for message in game.log.messages[-LOG_HISTORY:]],
    }


def _restore_inventory(game: Any, data: dict[str, Any]) -> None:
    from inventory import Inventory

    inventory = Inventory(capacity=int(data.get("capacity", 26)))
    inventory.items = [item_from_dict(item) for item in data.get("items", [])]
    weapon = int(data.get("weapon", -1))
    armor = int(data.get("armor", -1))
    if 0 <= weapon < len(inventory.items):
        inventory.weapon = inventory.items[weapon]
    if 0 <= armor < len(inventory.items):
        inventory.armor = inventory.items[armor]
    game.inventory = inventory


def _restore_dungeon(data: dict[str, Any]) -> tuple[Dungeon, int, int]:
    w = int(data.get("w", MAP_W))
    h = int(data.get("h", MAP_H))
    grid = [list(row) for row in data.get("grid", [])]
    if len(grid) != h or any(len(row) != w for row in grid):
        raise ValueError("save has a malformed dungeon grid")
    dungeon = Dungeon.__new__(Dungeon)
    dungeon.w = w
    dungeon.h = h
    dungeon.grid = grid
    dungeon.rooms = [tuple(room) for room in data.get("rooms", [])]
    return dungeon, w, h


def apply_state(game: Any, data: dict[str, Any]) -> None:
    """Восстановить объект Game из состояния, не генерируя новый этаж."""
    game.depth = int(data["depth"])
    game.player = entity_from_dict(data["player"])
    _restore_inventory(game, data.get("inventory", {}))
    game.stairs = tuple(int(v) for v in data.get("stairs", (0, 0)))

    stats = data.get("stats", {})
    game.player_level = int(stats.get("player_level", 1))
    game.player_xp = int(stats.get("player_xp", 0))
    game.xp_next = int(stats.get("xp_next", 15))
    game.gold = int(stats.get("gold", 0))
    game.kills = int(stats.get("kills", 0))
    game.turns = int(stats.get("turns", 0))
    game.killed_by = str(stats.get("killed_by", ""))
    game.poison_turns = int(stats.get("poison_turns", 0))
    game.poison_damage = int(stats.get("poison_damage", 0))
    game.regen_counter = int(stats.get("regen_counter", 0))

    game.enemies = [
        entity_from_dict(enemy) for enemy in data.get("enemies", [])
    ]
    game.items = [item_from_dict(item) for item in data.get("items", [])]

    trash = data.get("trash", {})
    pos = trash.get("pos")
    game.trash_pos = tuple(int(v) for v in pos) if pos else None
    game.trash_items = [
        item_from_dict(item) for item in trash.get("items", [])
    ]
    game.trash_noticed = bool(trash.get("noticed", False))

    game.chests = [
        chest_from_dict(chest) for chest in data.get("chests", [])
    ]
    game.special_rooms = [
        (*[int(v) for v in entry[:4]], str(entry[4]))
        for entry in data.get("special_rooms", [])
    ]
    game.special_room_seen = {
        tuple(int(v) for v in entry)
        for entry in data.get("special_room_seen", [])
    }

    hints = data.get("hints", {})
    game.chest_hinted = bool(hints.get("chest_hinted", False))

    game.dungeon, w, h = _restore_dungeon(data.get("dungeon", {}))
    explored = np.zeros((w, h), dtype=bool, order="F")
    for y, row in enumerate(data.get("explored", [])):
        if y >= h:
            break
        for x, value in enumerate(row):
            if x >= w:
                break
            if value == "1":
                explored[x, y] = True
    game.explored = explored
    game.visible = np.zeros((w, h), dtype=bool, order="F")

    game.log.messages = [
        (str(text), str(color))
        for text, color in data.get("log", [])
    ][-LOG_HISTORY:]
    game.log.offset = 0

    # Загружаемся всегда в игру, без открытых меню и прошлых экранов.
    game.mode = MODE_PLAYING
    game.game_over = False
    game.win = False
    game.quit_requested = False
    game.active_chest = None
    game.chest_deposit_mode = False
    game.trash_deposit_mode = False
    game.update_fov()
