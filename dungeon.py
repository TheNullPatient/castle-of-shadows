"""Процедурная генерация: комнаты + L-образные коридоры."""
import random

from constants import MAP_H, MAP_W


class Dungeon:
    def __init__(self, w: int = MAP_W, h: int = MAP_H):
        self.w, self.h = w, h
        self.grid = [["#"] * w for _ in range(h)]
        self.rooms: list[tuple[int, int, int, int]] = []
        self._generate()

    def _generate(self) -> None:
        # Чем больше этаж, тем больше комнат: маленькая карта остаётся
        # компактной, а большая не превращается в пустое поле.
        target = max(5, min(36, (self.w * self.h) // 240))
        max_attempts = max(400, target * 60)
        attempts = 0
        while len(self.rooms) < target and attempts < max_attempts:
            attempts += 1
            w = random.randint(5, 11)
            h = random.randint(3, 6)
            x = random.randint(1, self.w - w - 1)
            y = random.randint(1, self.h - h - 1)
            new_room = (x, y, w, h)
            if any(self._overlaps(new_room, r) for r in self.rooms):
                continue
            self._carve_room(new_room)
            if self.rooms:
                self._connect(self.rooms[-1], new_room)
            self.rooms.append(new_room)
        if not self.rooms:
            # Крайне редкий случай: за 300 попыток не нашлось ни одной комнаты.
            fallback = (1, 1, min(9, self.w - 2), min(4, self.h - 2))
            self._carve_room(fallback)
            self.rooms.append(fallback)
        self._arrange_rooms()

    def _arrange_rooms(self) -> None:
        """Поставить старт в угол, а лестницу — в самую дальнюю комнату.

        Так на большом этаже игрок действительно исследует карту, а не
        находит спуск в соседней комнате. Порядок важен: `rooms[0]` — старт,
        `rooms[-1]` — лестница.
        """
        if len(self.rooms) < 2:
            return

        def center(room: tuple[int, int, int, int]) -> tuple[int, int]:
            x, y, w, h = room
            return x + w // 2, y + h // 2

        start = min(self.rooms, key=lambda room: sum(center(room)))
        sx, sy = center(start)
        stairs = max(
            self.rooms,
            key=lambda room: (
                abs(center(room)[0] - sx) + abs(center(room)[1] - sy)
            ),
        )
        self.rooms = (
            [start]
            + [room for room in self.rooms if room not in (start, stairs)]
            + [stairs]
        )

    @staticmethod
    def _overlaps(r1, r2) -> bool:
        x1, y1, w1, h1 = r1
        x2, y2, w2, h2 = r2
        return not (
            x1 + w1 + 1 < x2
            or x2 + w2 + 1 < x1
            or y1 + h1 + 1 < y2
            or y2 + h2 + 1 < y1
        )

    def _carve_room(self, room) -> None:
        x, y, w, h = room
        for i in range(x, x + w):
            for j in range(y, y + h):
                self.grid[j][i] = "."

    def _connect(self, r1, r2) -> None:
        x1, y1, w1, h1 = r1
        x2, y2, w2, h2 = r2
        cx1, cy1 = x1 + w1 // 2, y1 + h1 // 2
        cx2, cy2 = x2 + w2 // 2, y2 + h2 // 2
        if random.random() < 0.5:
            for x in range(min(cx1, cx2), max(cx1, cx2) + 1):
                self.grid[cy1][x] = "."
            for y in range(min(cy1, cy2), max(cy1, cy2) + 1):
                self.grid[y][cx2] = "."
        else:
            for y in range(min(cy1, cy2), max(cy1, cy2) + 1):
                self.grid[y][cx1] = "."
            for x in range(min(cx1, cx2), max(cx1, cx2) + 1):
                self.grid[cy2][x] = "."

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.w and 0 <= y < self.h

    def is_wall(self, x: int, y: int) -> bool:
        return not self.in_bounds(x, y) or self.grid[y][x] == "#"

    def walkable(self, x: int, y: int) -> bool:
        return self.in_bounds(x, y) and self.grid[y][x] != "#"
