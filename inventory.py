"""Инвентарь, экипировка и применение предметов."""
from __future__ import annotations

from typing import TYPE_CHECKING

from constants import FIRE_DAMAGE, FIRE_RADIUS, INVENTORY_CAPACITY
from entities import Item

if TYPE_CHECKING:
    from game import Game


class Inventory:
    def __init__(self, capacity: int = INVENTORY_CAPACITY):
        self.capacity = capacity
        self.items: list[Item] = []
        self.weapon: Item | None = None
        self.armor: Item | None = None

    def __len__(self) -> int:
        return len(self.items)

    def can_add(self) -> bool:
        return len(self.items) < self.capacity

    def add(self, item: Item) -> bool:
        if not self.can_add():
            return False
        self.items.append(item)
        return True

    def pop(self, index: int) -> Item:
        return self.items.pop(index)

    def letter_index(self, char: str) -> int | None:
        if len(char) != 1:
            return None
        idx = ord(char.lower()) - ord("a")
        if 0 <= idx < len(self.items):
            return idx
        return None

    def label(self, item: Item) -> str:
        extra = ""
        if item.kind == "weapon":
            extra = f" (+{item.value} ATK)"
        elif item.kind == "armor":
            extra = f" (+{item.value} DEF)"
        elif item.kind == "potion":
            extra = f" (+{item.value} HP)"
        return f"{item.name}{extra}"

    def use(self, index: int, game: Game) -> bool:
        if not (0 <= index < len(self.items)):
            return False
        item = self.items[index]
        kind = item.kind
        if kind == "potion":
            return self._use_potion(index, game)
        if kind == "weapon":
            return self._equip(index, "weapon", game)
        if kind == "armor":
            return self._equip(index, "armor", game)
        if kind == "scroll":
            return self._use_scroll(index, game)
        game.msg(f"You cannot use the {item.name}.")
        return False

    def _use_potion(self, index: int, game: Game) -> bool:
        if game.player.hp >= game.player.max_hp:
            game.msg("You are already at full health.", "warn")
            return False
        item = self.pop(index)
        missing = game.player.max_hp - game.player.hp
        heal = min(item.value, missing)
        game.player.hp += heal
        game.msg(f"You drink a potion (+{heal} HP).", "heal")
        return True

    def _equip(self, index: int, slot: str, game: Game) -> bool:
        item = self.items[index]
        current = self.weapon if slot == "weapon" else self.armor
        if current is item:
            if slot == "weapon":
                self.weapon = None
            else:
                self.armor = None
            game.msg(f"You unequip the {item.name}.")
            return True
        if slot == "weapon":
            self.weapon = item
            game.msg(f"You wield the {item.name} (+{item.value} ATK).", "item")
        else:
            self.armor = item
            game.msg(f"You put on the {item.name} (+{item.value} DEF).", "item")
        return True

    def _use_scroll(self, index: int, game: Game) -> bool:
        item = self.items[index]
        effect = item.effect
        if effect == "teleport":
            if not game.teleport_player():
                game.msg("The scroll fizzles. No space to teleport.")
                return False
            self.pop(index)
            game.msg("The world twists. You teleport!", "item")
            return True
        if effect == "mapping":
            self.pop(index)
            game.reveal_map()
            game.msg("A map of this floor unfolds in your mind.", "item")
            return True
        if effect == "fire":
            self.pop(index)
            hits = game.cast_fire(FIRE_RADIUS, FIRE_DAMAGE)
            if hits:
                game.msg(f"Fire erupts around you! ({hits} burned)", "warn")
            else:
                game.msg("Flames roar, but nobody is in sight.", "warn")
            return True
        game.msg("The scroll is blank.")
        return False
