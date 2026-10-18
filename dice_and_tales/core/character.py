"""The player character: stats, HP, resources, inventory and progression."""

import re
from dataclasses import asdict, dataclass, field

from dice_and_tales.core import dice
from dice_and_tales.core.rules import (
    ABILITIES, CLASSES, ITEMS, LEVEL_XP, MAX_LEVEL, RACES, SHORT_RESTS_PER_DAY,
    HEROIC_HP_BONUS,
    CharacterClass, ClassSpec, Race, RaceSpec, modifier,
)


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "item"


@dataclass
class Item:
    id: str
    name: str
    description: str
    kind: str = "gear"
    heal: str | None = None

    @classmethod
    def from_catalog(cls, item_id: str) -> "Item":
        spec = ITEMS[item_id]
        return cls(id=item_id, name=spec.name, description=spec.description, kind=spec.kind, heal=spec.heal)


@dataclass
class Character:
    name: str
    character_class: CharacterClass
    race: Race
    scores: dict[str, int]
    max_hp: int
    current_hp: int = -1
    level: int = 1
    xp: int = 0
    gold: int = 10
    inventory: list[Item] = field(default_factory=list)
    resources: dict[str, int] = field(default_factory=dict)

    def __post_init__(self):
        if self.current_hp < 0:
            self.current_hp = self.max_hp
        if not self.resources:
            self.resources = self.full_resources()

    # --- Derived values -------------------------------------------------

    @property
    def spec(self) -> ClassSpec:
        return CLASSES[self.character_class]

    @property
    def race_spec(self) -> RaceSpec:
        return RACES[self.race]

    @property
    def title(self) -> str:
        return f"{self.race.value} {self.character_class.value}"

    @property
    def is_alive(self) -> bool:
        return self.current_hp > 0

    @property
    def proficiency(self) -> int:
        return 2

    @property
    def armor_class(self) -> int:
        spec = self.spec
        dex = self.mod("dexterity")
        if spec.ac_dex_cap is not None:
            dex = min(dex, spec.ac_dex_cap)
        return spec.base_ac + dex

    @property
    def spell_save_dc(self) -> int:
        ability = self.spec.spellcasting or "wisdom"
        return 8 + self.proficiency + self.mod(ability)

    @property
    def next_level_xp(self) -> int | None:
        return LEVEL_XP.get(self.level + 1)

    def has_trait(self, trait: str) -> bool:
        return trait in self.race_spec.traits

    def mod(self, ability: str) -> int:
        return modifier(self.scores[ability])

    def is_proficient(self, skill: str | None) -> bool:
        return skill is not None and skill in self.spec.skills

    def check_bonus(self, ability: str, skill: str | None = None) -> int:
        bonus = self.mod(ability)
        if self.is_proficient(skill):
            bonus += self.proficiency
        return bonus

    @property
    def weapon_attack_bonus(self) -> int:
        return self.mod(self.spec.weapon.ability) + self.proficiency

    @property
    def spell_attack_bonus(self) -> int:
        return self.mod(self.spec.spellcasting or "intelligence") + self.proficiency

    def full_resources(self) -> dict[str, int]:
        res = {"short_rests": SHORT_RESTS_PER_DAY}
        slots = self.spec.spell_slots.get(self.level)
        if slots:
            res["spell_slots"] = slots
        if self.character_class is CharacterClass.FIGHTER:
            res["second_wind"] = 1
        if self.character_class is CharacterClass.CLERIC:
            res["channel_divinity"] = 1
        return res

    def max_resource(self, key: str) -> int:
        return self.full_resources().get(key, 0)

    # --- State changes --------------------------------------------------

    def take_damage(self, amount: int, damage_type: str = "bludgeoning") -> int:
        if damage_type == "poison" and self.has_trait("poison_resistance"):
            amount //= 2
        amount = max(0, amount)
        self.current_hp = max(0, self.current_hp - amount)
        return amount

    def heal(self, amount: int) -> int:
        before = self.current_hp
        self.current_hp = min(self.max_hp, self.current_hp + max(0, amount))
        return self.current_hp - before

    def spend(self, key: str) -> bool:
        if self.resources.get(key, 0) <= 0:
            return False
        self.resources[key] -= 1
        return True

    def add_item(self, item: Item) -> None:
        self.inventory.append(item)

    def find_item(self, item_id_or_name: str) -> Item | None:
        key = item_id_or_name.strip().lower()
        slug = slugify(key)
        for item in self.inventory:
            if item.id == key or item.id == slug or item.name.lower() == key:
                return item
        return None

    def remove_item(self, item_id_or_name: str) -> Item | None:
        item = self.find_item(item_id_or_name)
        if item:
            self.inventory.remove(item)
        return item

    def has_item(self, item_id: str) -> bool:
        return self.find_item(item_id) is not None

    def add_xp(self, amount: int) -> list[int]:
        """Add XP; returns the list of levels gained (usually empty)."""
        self.xp += max(0, amount)
        gained = []
        while self.level < MAX_LEVEL and self.xp >= LEVEL_XP[self.level + 1]:
            self.level += 1
            hp_gain = max(1, self.spec.hit_die // 2 + 1 + self.mod("constitution"))
            self.max_hp += hp_gain
            self.current_hp += hp_gain
            slots = self.spec.spell_slots.get(self.level)
            if slots:
                self.resources["spell_slots"] = slots
            gained.append(self.level)
        return gained

    def short_rest(self) -> int:
        """Spend a short rest: roll a hit die, refresh per-rest features. Returns HP healed."""
        if not self.spend("short_rests"):
            return -1
        healed = self.heal(dice.roll(self.spec.hit_die) + self.mod("constitution"))
        full = self.full_resources()
        for key in ("second_wind", "channel_divinity"):
            if key in full:
                self.resources[key] = full[key]
        return healed

    def long_rest(self) -> int:
        healed = self.heal(self.max_hp)
        self.resources = self.full_resources()
        return healed

    # --- Persistence ----------------------------------------------------

    def to_dict(self) -> dict:
        data = asdict(self)
        data["character_class"] = self.character_class.name
        data["race"] = self.race.name
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Character":
        data = dict(data)
        data["character_class"] = CharacterClass[data["character_class"]]
        data["race"] = Race[data["race"]]
        data["inventory"] = [Item(**item) for item in data.get("inventory", [])]
        return cls(**data)


def roll_scores() -> tuple[dict[str, int], dict[str, list[int]]]:
    """Roll 4d6-drop-lowest for every ability. Returns scores and the raw dice."""
    scores, raw = {}, {}
    for ability in ABILITIES:
        scores[ability], raw[ability] = dice.roll_stat()
    return scores, raw


def arrange_for_class(
    scores: dict[str, int], raw: dict[str, list[int]], character_class: CharacterClass
) -> tuple[dict[str, int], dict[str, list[int]]]:
    """Reassign rolled scores so the best go to the class's key abilities (standard 5e practice)."""
    rolls = sorted(((scores[a], raw[a]) for a in ABILITIES), key=lambda r: r[0], reverse=True)
    priority = CLASSES[character_class].priority
    return ({a: rolls[i][0] for i, a in enumerate(priority)}, {a: rolls[i][1] for i, a in enumerate(priority)})


def apply_racial_bonuses(scores: dict[str, int], race: Race) -> dict[str, int]:
    bonuses = RACES[race].bonuses
    return {a: scores[a] + bonuses.get(a, 0) for a in ABILITIES}


def create_character(
    name: str,
    character_class: CharacterClass,
    race: Race,
    base_scores: dict[str, int] | None = None,
) -> Character:
    if base_scores is None:
        base_scores, _ = arrange_for_class(*roll_scores(), character_class)
    scores = apply_racial_bonuses(base_scores, race)
    spec = CLASSES[character_class]
    hp = max(1, spec.hit_die + modifier(scores["constitution"])) + HEROIC_HP_BONUS
    character = Character(
        name=name.strip() or "Nameless",
        character_class=character_class,
        race=race,
        scores=scores,
        max_hp=hp,
    )
    for item_id in spec.starting_items:
        character.add_item(Item.from_catalog(item_id))
    return character

