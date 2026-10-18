"""Everything that defines a run, serialisable to JSON."""

import time
from dataclasses import dataclass, field

from dice_and_tales.core.character import Character
from dice_and_tales.core.combat import Combat

SAVE_VERSION = 1


@dataclass
class JournalEntry:
    text: str
    where: str
    source: str = "story"  # story | dm


@dataclass
class GameState:
    character: Character
    scene_id: str
    seed: int
    flags: set[str] = field(default_factory=set)
    visited: set[str] = field(default_factory=set)
    journal: list[JournalEntry] = field(default_factory=list)
    dm_history: list[dict] = field(default_factory=list)
    used_options: set[str] = field(default_factory=set)
    dm_budget: dict[str, int] = field(default_factory=dict)
    combat: Combat | None = None
    ending: str | None = None
    victory: bool = False
    turns: int = 0
    started_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "version": SAVE_VERSION,
            "character": self.character.to_dict(),
            "scene_id": self.scene_id,
            "seed": self.seed,
            "flags": sorted(self.flags),
            "visited": sorted(self.visited),
            "journal": [vars(j) for j in self.journal],
            "dm_history": self.dm_history,
            "used_options": sorted(self.used_options),
            "dm_budget": self.dm_budget,
            "combat": self.combat.to_dict() if self.combat else None,
            "ending": self.ending,
            "victory": self.victory,
            "turns": self.turns,
            "started_at": self.started_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GameState":
        if data.get("version") != SAVE_VERSION:
            raise ValueError(f"unsupported save version {data.get('version')!r}")
        character = Character.from_dict(data["character"])
        combat = Combat.from_dict(character, data["combat"]) if data.get("combat") else None
        return cls(
            character=character,
            scene_id=data["scene_id"],
            seed=data.get("seed", 0),
            flags=set(data.get("flags", [])),
            visited=set(data.get("visited", [])),
            journal=[JournalEntry(**j) for j in data.get("journal", [])],
            dm_history=data.get("dm_history", []),
            used_options=set(data.get("used_options", [])),
            dm_budget=data.get("dm_budget", {}),
            combat=combat,
            ending=data.get("ending"),
            victory=data.get("victory", False),
            turns=data.get("turns", 0),
            started_at=data.get("started_at", time.time()),
        )
