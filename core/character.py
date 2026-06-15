from dataclasses import dataclass, field
from enum import Enum

from core.dice import roll_stat


class CharacterClass(Enum):
    FIGHTER = "Fighter"
    ROGUE = "Rogue"
    WIZARD = "Wizard"
    CLERIC = "Cleric"


class Race(Enum):
    HUMAN = "Human"
    ELF = "Elf"
    DWARF = "Dwarf"
    HALFLING = "Halfling"


@dataclass
class Stats:
    strength: int
    dexterity: int
    constitution: int
    intelligence: int
    wisdom: int
    charisma: int


def stat_modifier(score: int) -> int:
    return (score - 10) // 2


def _roll_stats() -> Stats:
    return Stats(
        strength=roll_stat(),
        dexterity=roll_stat(),
        constitution=roll_stat(),
        intelligence=roll_stat(),
        wisdom=roll_stat(),
        charisma=roll_stat(),
    )


def _base_hp(character_class: CharacterClass, constitution: int) -> int:
    hit_dice = {
        CharacterClass.FIGHTER: 10,
        CharacterClass.ROGUE: 8,
        CharacterClass.WIZARD: 6,
        CharacterClass.CLERIC: 8,
    }
    return hit_dice[character_class] + stat_modifier(constitution)


@dataclass
class Character:
    name: str
    character_class: CharacterClass
    race: Race
    stats: Stats
    max_hp: int
    current_hp: int = field(init=False)

    def __post_init__(self):
        self.current_hp = self.max_hp

    @property
    def is_alive(self) -> bool:
        return self.current_hp > 0


def create_character(name: str, character_class: CharacterClass, race: Race) -> Character:
    stats = _roll_stats()
    hp = max(1, _base_hp(character_class, stats.constitution))
    return Character(name=name, character_class=character_class, race=race, stats=stats, max_hp=hp)
