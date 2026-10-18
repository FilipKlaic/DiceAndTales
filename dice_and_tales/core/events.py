"""Events describe what happened. The engine produces them; the UI animates them."""

from dataclasses import dataclass, field

from dice_and_tales.core.dice import D20Roll


class Event:
    """Marker base class."""


@dataclass
class Narration(Event):
    text: str
    style: str = "normal"  # normal | dialogue | danger | loot | system | dm


@dataclass
class Notice(Event):
    text: str
    style: str = "system"


@dataclass
class RollEvent(Event):
    label: str
    d20: D20Roll
    modifier: int
    total: int
    target: int
    target_label: str  # "DC" or "AC"
    success: bool
    critical: bool = False
    fumble: bool = False
    note: str = ""


@dataclass
class DamageEvent(Event):
    target: str  # "player" or the enemy's display name
    amount: int
    damage_type: str
    hp: int
    max_hp: int
    rolls: tuple[int, ...] = ()
    source: str = ""


@dataclass
class HealEvent(Event):
    target: str
    amount: int
    hp: int
    max_hp: int
    source: str = ""


@dataclass
class ItemEvent(Event):
    name: str
    gained: bool


@dataclass
class GoldEvent(Event):
    amount: int
    total: int


@dataclass
class XPEvent(Event):
    amount: int
    total: int
    levels: list[int] = field(default_factory=list)


@dataclass
class SceneEvent(Event):
    scene_id: str


@dataclass
class CombatStartEvent(Event):
    enemies: list[str]


@dataclass
class CombatEndEvent(Event):
    result: str  # victory | fled | defeat


@dataclass
class GameOverEvent(Event):
    title: str
    victory: bool
