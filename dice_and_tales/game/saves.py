"""Save slots on disk: three manual slots plus an autosave."""

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

from dice_and_tales import config
from dice_and_tales.core.rules import CharacterClass, Race
from dice_and_tales.game.state import GameState

SLOTS = ("auto", "1", "2", "3")


@dataclass
class SlotInfo:
    slot: str
    name: str
    title: str
    level: int
    where: str
    saved_at: float

    @property
    def label(self) -> str:
        stamp = time.strftime("%d %b %H:%M", time.localtime(self.saved_at))
        return f"{self.name}, L{self.level} {self.title}, {self.where} ({stamp})"


def save_dir() -> Path:
    return config.home_dir() / "saves"


def _path(slot: str) -> Path:
    if slot not in SLOTS:
        raise ValueError(f"unknown save slot {slot!r}")
    return save_dir() / f"{slot}.json"


def save(state: GameState, slot: str, where: str = "") -> Path:
    path = _path(slot)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"saved_at": time.time(), "where": where, "state": state.to_dict()}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, path)  # atomic: a crash mid-write never corrupts a slot
    return path


def load(slot: str) -> GameState:
    data = json.loads(_path(slot).read_text())
    return GameState.from_dict(data["state"])


def info(slot: str) -> SlotInfo | None:
    try:
        data = json.loads(_path(slot).read_text())
        char = data["state"]["character"]
        title = f"{Race[char['race']].value} {CharacterClass[char['character_class']].value}"
        return SlotInfo(slot, char["name"], title, char.get("level", 1), data.get("where", ""), data.get("saved_at", 0))
    except (OSError, ValueError, KeyError):
        return None


def delete(slot: str) -> None:
    try:
        _path(slot).unlink()
    except FileNotFoundError:
        pass
