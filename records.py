"""Seed забега, счёт и таблица рекордов.

Текущие забеги живут в слотах ``saves/``, а завершённые — в отдельном
``records.json``. Формат намеренно простой: список лучших забегов, который
легко читать и чинить вручную.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any

from constants import ROOT, RUN_MODE_GENERAL, RUN_MODE_NAMES

RECORDS_PATH = ROOT / "records.json"
RECORDS_VERSION = 1
MAX_RECORDS = 20
MAX_SEED_LENGTH = 16

# Без похожих символов: seed должно быть легко продиктовать или переписать.
SEED_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_seed(length: int = 8) -> str:
    """Случайный seed для нового забега."""
    length = max(1, min(MAX_SEED_LENGTH, int(length)))
    return "".join(secrets.choice(SEED_ALPHABET) for _ in range(length))


def normalize_seed(value: Any) -> str:
    """Привести seed к верхнему регистру и убрать лишние символы."""
    if value is None:
        return ""
    text = "".join(
        char
        for char in str(value).upper()
        if char.isalnum() or char in "-_"
    )
    return text[:MAX_SEED_LENGTH]


def floor_seed(seed: str, depth: int) -> int:
    """Детерминированное зерно для этажа: один seed — одна и та же карта."""
    payload = f"{normalize_seed(seed)}:{int(depth)}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def format_duration(seconds: float) -> str:
    """Длительность забега в виде ``12:34`` или ``1:02:03``."""
    total = int(max(0, seconds))
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def score_for_run(
    *,
    depth: int,
    player_level: int,
    kills: int,
    gold: int,
    bosses: int,
    win: bool,
) -> int:
    """Очки забега: глубина важнее всего, победа даёт большой бонус."""
    score = (
        max(0, int(depth)) * 1000
        + max(0, int(bosses)) * 500
        + max(0, int(player_level)) * 100
        + max(0, int(kills)) * 10
        + max(0, int(gold))
    )
    if win:
        score += 5000
    return score


def _run_mode(value: Any) -> str:
    if isinstance(value, str) and value in RUN_MODE_NAMES:
        return value
    return RUN_MODE_GENERAL


def _record_sort_key(entry: dict[str, Any]) -> tuple[int, int, float]:
    return (
        int(entry.get("score", 0)),
        int(entry.get("depth", 0)),
        float(entry.get("date", 0.0)),
    )


def _normalize_entry(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    try:
        depth = int(raw.get("depth", 1))
        player_level = int(raw.get("player_level", 1))
        kills = int(raw.get("kills", 0))
        gold = int(raw.get("gold", 0))
        bosses = int(raw.get("bosses", 0))
        turns = int(raw.get("turns", 0) or 0)
        damage_dealt = int(raw.get("damage_dealt", 0) or 0)
        damage_taken = int(raw.get("damage_taken", 0) or 0)
        duration = float(raw.get("duration", 0.0))
        date = float(raw.get("date", 0.0))
        win = bool(raw.get("win", False))
        score = int(
            raw.get(
                "score",
                score_for_run(
                    depth=depth,
                    player_level=player_level,
                    kills=kills,
                    gold=gold,
                    bosses=bosses,
                    win=win,
                ),
            )
        )
    except (TypeError, ValueError):
        return None
    return {
        "date": date,
        "run_mode": _run_mode(raw.get("run_mode")),
        "seed": normalize_seed(raw.get("seed")),
        "win": win,
        "depth": max(1, depth),
        "player_level": max(1, player_level),
        "kills": max(0, kills),
        "bosses": max(0, bosses),
        "gold": max(0, gold),
        "turns": max(0, turns),
        "damage_dealt": max(0, damage_dealt),
        "damage_taken": max(0, damage_taken),
        "duration": max(0.0, duration),
        "score": max(0, score),
        "cause": str(raw.get("cause", ""))[:60],
    }


def load_records() -> list[dict[str, Any]]:
    """Прочитать таблицу рекордов, молча откатившись к пустому списку."""
    try:
        raw = json.loads(RECORDS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if isinstance(raw, dict):
        runs = raw.get("runs", [])
    else:
        runs = raw
    if not isinstance(runs, list):
        return []
    entries = [
        entry
        for entry in (_normalize_entry(item) for item in runs)
        if entry is not None
    ]
    entries.sort(key=_record_sort_key, reverse=True)
    return entries[:MAX_RECORDS]


def save_records(entries: list[dict[str, Any]]) -> bool:
    """Атомарно записать таблицу рекордов."""
    payload = {
        "version": RECORDS_VERSION,
        "runs": entries[:MAX_RECORDS],
    }
    try:
        RECORDS_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = RECORDS_PATH.with_name(RECORDS_PATH.name + ".tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, RECORDS_PATH)
    except OSError:
        return False
    return True


def add_record(summary: dict[str, Any]) -> int | None:
    """Добавить забег и вернуть его место в таблице (1 — лучший)."""
    raw = {**summary, "date": summary.get("date") or time.time()}
    entry = _normalize_entry(raw)
    if entry is None:
        return None
    entries = load_records()
    entries.append(entry)
    entries.sort(key=_record_sort_key, reverse=True)
    rank = next(
        (index + 1 for index, item in enumerate(entries) if item is entry),
        None,
    )
    save_records(entries[:MAX_RECORDS])
    if rank is None or rank > MAX_RECORDS:
        return None
    return rank
