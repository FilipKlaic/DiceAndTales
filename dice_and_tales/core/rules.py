"""Static rules data: abilities, skills, classes, races and the item catalog."""

from dataclasses import dataclass, field
from enum import Enum

ABILITIES = ("strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma")
ABILITY_LABELS = {a: a[:3].upper() for a in ABILITIES}

SKILLS = {
    "athletics": "strength",
    "acrobatics": "dexterity",
    "sleight_of_hand": "dexterity",
    "stealth": "dexterity",
    "arcana": "intelligence",
    "history": "intelligence",
    "investigation": "intelligence",
    "religion": "intelligence",
    "insight": "wisdom",
    "medicine": "wisdom",
    "perception": "wisdom",
    "survival": "wisdom",
    "deception": "charisma",
    "intimidation": "charisma",
    "persuasion": "charisma",
}

DAMAGE_TYPES = (
    "bludgeoning", "piercing", "slashing", "fire", "cold", "lightning",
    "poison", "necrotic", "radiant", "force", "psychic",
)

LEVEL_XP = {1: 0, 2: 300, 3: 900}
MAX_LEVEL = max(LEVEL_XP)
SHORT_RESTS_PER_DAY = 2
HEROIC_HP_BONUS = 6  # a lone hero needs more slack than a 5e party member


def modifier(score: int) -> int:
    return (score - 10) // 2


def skill_label(skill: str) -> str:
    words = skill.split("_")
    return " ".join(w if w in ("of", "the") else w.capitalize() for w in words)


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


@dataclass(frozen=True)
class Weapon:
    name: str
    damage: str
    ability: str
    damage_type: str


@dataclass(frozen=True)
class ClassSpec:
    hit_die: int
    weapon: Weapon
    base_ac: int
    ac_dex_cap: int | None  # None = full DEX, 0 = no DEX (heavy armour)
    skills: tuple[str, ...]
    spellcasting: str | None
    starting_items: tuple[str, ...]
    blurb: str
    features: tuple[str, ...]
    spell_slots: dict[int, int] = field(default_factory=dict)
    priority: tuple[str, ...] = ABILITIES  # best rolls go to these abilities first


CLASSES: dict[CharacterClass, ClassSpec] = {
    CharacterClass.FIGHTER: ClassSpec(
        hit_die=10,
        weapon=Weapon("Longsword", "1d8", "strength", "slashing"),
        base_ac=16, ac_dex_cap=0,
        skills=("athletics", "intimidation", "perception"),
        spellcasting=None,
        starting_items=("healing_potion", "torch", "rope"),
        blurb="Armoured, tough and straightforward. Hits hard and gets back up.",
        features=("Second Wind: heal 1d10 + level, once per rest.",
                  "Chain mail: AC 16."),
        priority=("strength", "constitution", "dexterity", "wisdom", "charisma", "intelligence"),
    ),
    CharacterClass.ROGUE: ClassSpec(
        hit_die=8,
        weapon=Weapon("Shortsword", "1d6", "dexterity", "piercing"),
        base_ac=12, ac_dex_cap=None,
        skills=("stealth", "sleight_of_hand", "acrobatics", "deception", "perception"),
        spellcasting=None,
        starting_items=("healing_potion", "lockpicks", "torch"),
        blurb="Quick, quiet and clever. Strikes from the shadows, slips away when it goes wrong.",
        features=("Sneak Attack: +1d6 damage on every hit.",
                  "Cunning Action: fleeing a fight always succeeds.",
                  "Advantage on Stealth checks."),
        priority=("dexterity", "constitution", "wisdom", "charisma", "intelligence", "strength"),
    ),
    CharacterClass.WIZARD: ClassSpec(
        hit_die=6,
        weapon=Weapon("Quarterstaff", "1d6", "strength", "bludgeoning"),
        base_ac=10, ac_dex_cap=None,
        skills=("arcana", "history", "investigation"),
        spellcasting="intelligence",
        starting_items=("healing_potion", "spellbook", "torch"),
        blurb="Fragile but brilliant. Bends the world with study and spell slots.",
        features=("Fire Bolt: ranged spell attack, 1d10 fire, at will.",
                  "Magic Missile: 3d4+3 force, never misses (spell slot).",
                  "Shield: +5 AC against one hit (reaction, spell slot)."),
        spell_slots={1: 2, 2: 3, 3: 4},
        priority=("intelligence", "constitution", "dexterity", "wisdom", "charisma", "strength"),
    ),
    CharacterClass.CLERIC: ClassSpec(
        hit_die=8,
        weapon=Weapon("Warhammer", "1d8", "strength", "bludgeoning"),
        base_ac=15, ac_dex_cap=0,
        skills=("religion", "insight", "medicine"),
        spellcasting="wisdom",
        starting_items=("healing_potion", "holy_symbol", "torch"),
        blurb="A servant of the light. Heals wounds and drives back the dead.",
        features=("Cure Wounds: heal 1d8 + WIS (spell slot).",
                  "Sacred Flame: target saves vs DEX or takes 1d8 radiant, at will.",
                  "Turn Undead: the undead must save or flee (once per rest)."),
        spell_slots={1: 2, 2: 3, 3: 4},
        priority=("wisdom", "strength", "constitution", "dexterity", "charisma", "intelligence"),
    ),
}


@dataclass(frozen=True)
class RaceSpec:
    bonuses: dict[str, int]
    traits: tuple[str, ...]
    blurb: str


RACES: dict[Race, RaceSpec] = {
    Race.HUMAN: RaceSpec(
        bonuses={a: 1 for a in ABILITIES},
        traits=(),
        blurb="Adaptable. +1 to every ability.",
    ),
    Race.ELF: RaceSpec(
        bonuses={"dexterity": 2, "intelligence": 1},
        traits=("keen_senses",),
        blurb="+2 DEX, +1 INT. Keen Senses: advantage on Perception.",
    ),
    Race.DWARF: RaceSpec(
        bonuses={"constitution": 2, "strength": 1},
        traits=("poison_resistance",),
        blurb="+2 CON, +1 STR. Dwarven Resilience: poison damage is halved.",
    ),
    Race.HALFLING: RaceSpec(
        bonuses={"dexterity": 2, "charisma": 1},
        traits=("lucky",),
        blurb="+2 DEX, +1 CHA. Lucky: natural 1s on a d20 are rerolled.",
    ),
}

TRAIT_LABELS = {
    "keen_senses": "Keen Senses",
    "poison_resistance": "Dwarven Resilience",
    "lucky": "Lucky",
}


@dataclass(frozen=True)
class ItemSpec:
    name: str
    description: str
    kind: str = "gear"  # gear | consumable | quest
    heal: str | None = None


ITEMS: dict[str, ItemSpec] = {
    "healing_potion": ItemSpec("Potion of Healing", "A red draught that knits flesh. Heals 2d4+2.", "consumable", heal="2d4+2"),
    "greater_healing_potion": ItemSpec("Potion of Greater Healing", "Thick and glowing. Heals 4d4+4.", "consumable", heal="4d4+4"),
    "torch": ItemSpec("Torch", "Pitch-soaked wood. Light in dark places."),
    "rope": ItemSpec("Hempen Rope", "Fifty feet of sturdy rope."),
    "lockpicks": ItemSpec("Thieves' Tools", "Picks and tension wrenches in a leather roll."),
    "spellbook": ItemSpec("Spellbook", "Your spells, written in a cramped hand."),
    "holy_symbol": ItemSpec("Holy Symbol", "A silver sun on a worn cord."),
    "tomb_map": ItemSpec("Hilda's Map", "A rough sketch of the north road and the tomb.", "quest"),
    "medallion": ItemSpec("Iron Medallion", "Dark iron that pulses like a slow heartbeat. It is cold to the touch.", "quest"),
    "priest_ring": ItemSpec("War-Priest's Signet", "A heavy ring stamped with a sun eclipsed by a skull.", "quest"),
    "silver_dagger": ItemSpec("Silvered Dagger", "Bright, well-balanced, and blessed against the dead."),
}
