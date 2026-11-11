"""Инвентарь, экипировка и применение предметов."""
from __future__ import annotations

from typing import TYPE_CHECKING

from constants import (
    FIRE_DAMAGE,
    FIRE_RADIUS,
    INVENTORY_CAPACITY,
    STACK_LIMITS,
)
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
        """Положить предмет в рюкзак, по возможности объединяя стопки.

        Возвращает True, только если удалось перенести весь предмет. Если
        место кончилось, у ``item`` останется неразмещённое количество.
        """
        limit = STACK_LIMITS.get(item.kind, 1)
        if limit > 1:
            for stack in self.items:
                if not self._same_stack(stack, item):
                    continue
                room = limit - stack.quantity
                if room <= 0:
                    continue
                moved = min(room, item.quantity)
                stack.quantity += moved
                stack.map_open = stack.map_open or item.map_open
                item.quantity -= moved
                if item.quantity <= 0:
                    return True

        while item.quantity > 0 and self.can_add():
            take = min(limit, item.quantity) if limit > 1 else item.quantity
            self.items.append(item.split(take))
        return item.quantity <= 0

    @staticmethod
    def _same_stack(a: Item, b: Item) -> bool:
        return (
            a.kind == b.kind
            and a.name == b.name
            and a.effect == b.effect
            and a.kind in STACK_LIMITS
        )

    def remove(self, index: int) -> Item:
        """Убрать предмет из рюкзака целиком, сняв его с экипировки."""
        item = self.items.pop(index)
        if self.weapon is item:
            self.weapon = None
        if self.armor is item:
            self.armor = None
        return item

    def consume(self, index: int) -> Item:
        """Израсходовать одну штуку из стопки (зелье, свиток)."""
        item = self.items[index]
        item.quantity -= 1
        if item.quantity <= 0:
            self.items.pop(index)
        return item

    def pop(self, index: int) -> Item:
        return self.remove(index)

    def letter_index(self, char: str) -> int | None:
        if len(char) != 1:
            return None
        idx = ord(char.lower()) - ord("a")
        if 0 <= idx < len(self.items):
            return idx
        return None

    @staticmethod
    def item_label(item: Item) -> str:
        extra = ""
        if item.kind == "weapon":
            ranged = ", ranged" if item.effect == "ranged" else ""
            extra = f" (+{item.value}{ranged})"
        elif item.kind == "armor":
            extra = f" (+{item.value})"
        elif item.kind == "potion":
            if item.effect == "health":
                extra = f" (+{item.value} HP)"
            elif item.effect == "antidote":
                extra = " (antidote)"
            elif item.effect == "strength":
                extra = f" (+{item.value} ATK)"
            elif item.effect == "ironskin":
                extra = f" (+{item.value} DEF)"
            else:
                extra = f" (+{item.value})"
        elif item.kind == "gold":
            extra = f" ({item.value})"
        elif item.kind == "scroll" and item.effect == "mapping":
            if item.map_open:
                extra = " (map open)"
        if item.max_durability > 0:
            extra += f" [{item.durability}/{item.max_durability}]"
        if item.quantity > 1:
            extra += f"×{item.quantity}"
        return f"{item.name}{extra}"

    def label(self, item: Item) -> str:
        return self.item_label(item)

    @staticmethod
    def equipped_label(item: Item | None) -> str:
        if item is None:
            return "-"
        if item.max_durability > 0:
            return f"{item.name} [{item.durability}/{item.max_durability}]"
        return item.name

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
        item = self.items[index]
        if item.effect == "antidote":
            self.consume(index)
            if game.cure_poison():
                game.msg("The antidote purges the poison from your veins.", "heal")
            else:
                game.msg("You drink the antidote. You were not poisoned.", "heal")
            return True
        if item.effect == "strength":
            self.consume(index)
            game.player.atk += item.value
            game.msg(f"You feel stronger! (+{item.value} ATK)", "good")
            return True
        if item.effect == "ironskin":
            self.consume(index)
            game.player.df += item.value
            game.msg(f"Your skin hardens! (+{item.value} DEF)", "good")
            return True

        if game.player.hp >= game.player.max_hp:
            game.msg("You are already at full health.", "warn")
            return False
        self.consume(index)
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
            if item.effect == "ranged":
                game.msg(
                    f"You wield the {item.name} (+{item.value} ranged ATK). "
                    f"Press f to shoot.",
                    "item",
                )
            else:
                game.msg(
                    f"You wield the {item.name} (+{item.value} ATK).",
                    "item",
                )
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
            self.consume(index)
            game.msg("The world twists. You teleport!", "item")
            return True
        if effect == "mapping":
            first = not item.map_open
            if first:
                item.map_open = True
                game.reveal_map()
                game.msg(
                    "A map of this floor unfolds in your mind. "
                    "It will last until you descend.",
                    "item",
                )
            else:
                game.msg("You unfold the map again.", "item")
            game.open_map()
            # Первое раскрытие стоит хода, повторное открытие — нет.
            game.skip_turn = not first
            return True
        if effect == "fire":
            self.consume(index)
            hits = game.cast_fire(FIRE_RADIUS, FIRE_DAMAGE)
            if hits:
                game.msg(f"Fire erupts around you! ({hits} burned)", "warn")
            else:
                game.msg("Flames roar, but nobody is in sight.", "warn")
            return True
        if effect == "healing":
            missing = game.player.max_hp - game.player.hp
            if missing <= 0:
                game.msg("You are already at full health.", "warn")
                return False
            self.consume(index)
            heal = min(item.value, missing)
            game.player.hp += heal
            game.msg(f"Soft light knits your wounds (+{heal} HP).", "heal")
            return True
        if effect == "lightning":
            self.consume(index)
            target = game.cast_lightning(item.value)
            if not target:
                game.msg("Thunder rolls, but no foe is in sight.", "warn")
            return True
        game.msg("The scroll is blank.")
        return False
