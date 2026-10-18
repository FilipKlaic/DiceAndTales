"""Ability checks: d20 + modifier (+ proficiency) against a DC."""

from dataclasses import dataclass

from dice_and_tales.core import dice
from dice_and_tales.core.character import Character
from dice_and_tales.core.events import RollEvent
from dice_and_tales.core.rules import ABILITY_LABELS, skill_label


@dataclass
class CheckResult:
    ability: str
    skill: str | None
    dc: int
    d20: dice.D20Roll
    modifier: int
    total: int
    success: bool
    reasons: list[str]

    @property
    def label(self) -> str:
        name = skill_label(self.skill) if self.skill else ABILITY_LABELS[self.ability]
        return f"{name} check"

    def to_event(self) -> RollEvent:
        return RollEvent(
            label=self.label,
            d20=self.d20,
            modifier=self.modifier,
            total=self.total,
            target=self.dc,
            target_label="DC",
            success=self.success,
            critical=self.d20.natural_20,
            fumble=self.d20.natural_1,
            note=", ".join(self.reasons),
        )

    def summary(self) -> dict:
        return {
            "check": self.label,
            "natural_roll": self.d20.kept,
            "modifier": self.modifier,
            "total": self.total,
            "dc": self.dc,
            "success": self.success,
            "natural_20": self.d20.natural_20,
            "natural_1": self.d20.natural_1,
        }


def advantage_sources(character: Character, skill: str | None) -> list[str]:
    reasons = []
    if skill == "stealth" and character.character_class.name == "ROGUE":
        reasons.append("Rogue: advantage on Stealth")
    if skill == "perception" and character.has_trait("keen_senses"):
        reasons.append("Keen Senses")
    return reasons


def resolve_check(
    character: Character,
    ability: str,
    dc: int,
    skill: str | None = None,
    advantage: bool = False,
    disadvantage: bool = False,
) -> CheckResult:
    reasons = advantage_sources(character, skill)
    if advantage:
        reasons.append("advantage")
    if disadvantage:
        reasons.append("disadvantage")
    roll = dice.roll_d20(
        advantage=advantage or bool(advantage_sources(character, skill)),
        disadvantage=disadvantage,
        lucky=character.has_trait("lucky"),
    )
    if roll.lucky_reroll:
        reasons.append("Lucky: rerolled a 1")
    if character.is_proficient(skill):
        reasons.append("proficient")
    bonus = character.check_bonus(ability, skill)
    total = roll.kept + bonus
    # 5e ability checks have no auto-success, but natural 20/1 feel great in a game.
    success = roll.natural_20 or (total >= dc and not roll.natural_1)
    return CheckResult(ability, skill, dc, roll, bonus, total, success, reasons)
