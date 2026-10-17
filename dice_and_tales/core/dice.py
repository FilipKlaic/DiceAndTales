"""Dice rolling. All randomness in the game flows through one seedable RNG."""

import random
import re
from dataclasses import dataclass

rng = random.Random()

_EXPR = re.compile(r"^\s*(\d*)\s*d\s*(\d+)\s*(?:([+-])\s*(\d+))?\s*$", re.IGNORECASE)


def seed(value: int | None) -> None:
    rng.seed(value)


def roll(sides: int) -> int:
    return rng.randint(1, sides)


def roll_multiple(count: int, sides: int) -> list[int]:
    return [roll(sides) for _ in range(count)]


def roll_stat() -> tuple[int, list[int]]:
    """4d6, drop the lowest. Returns the score and all four dice."""
    dice = roll_multiple(4, 6)
    return sum(sorted(dice)[1:]), dice


@dataclass(frozen=True)
class D20Roll:
    rolls: tuple[int, ...]
    kept: int
    mode: str = "normal"  # normal | advantage | disadvantage
    lucky_reroll: bool = False

    @property
    def natural_20(self) -> bool:
        return self.kept == 20

    @property
    def natural_1(self) -> bool:
        return self.kept == 1


def roll_d20(advantage: bool = False, disadvantage: bool = False, lucky: bool = False) -> D20Roll:
    """Roll a d20 with 5e advantage rules. Lucky (Halfling) rerolls natural 1s once."""
    mode = "normal"
    if advantage and not disadvantage:
        mode = "advantage"
    elif disadvantage and not advantage:
        mode = "disadvantage"

    count = 1 if mode == "normal" else 2
    rolls = []
    rerolled = False
    for _ in range(count):
        value = roll(20)
        if lucky and value == 1:
            rerolled = True
            value = roll(20)
        rolls.append(value)

    if mode == "advantage":
        kept = max(rolls)
    elif mode == "disadvantage":
        kept = min(rolls)
    else:
        kept = rolls[0]
    return D20Roll(rolls=tuple(rolls), kept=kept, mode=mode, lucky_reroll=rerolled)


@dataclass(frozen=True)
class DiceExpr:
    count: int
    sides: int
    bonus: int = 0

    def __str__(self) -> str:
        if not self.bonus:
            return f"{self.count}d{self.sides}"
        sign = "+" if self.bonus > 0 else "-"
        return f"{self.count}d{self.sides}{sign}{abs(self.bonus)}"

    @property
    def maximum(self) -> int:
        return self.count * self.sides + self.bonus


def parse(expr: str) -> DiceExpr:
    match = _EXPR.match(expr)
    if not match:
        raise ValueError(f"not a dice expression: {expr!r}")
    count = int(match.group(1) or 1)
    sides = int(match.group(2))
    bonus = int(match.group(4) or 0)
    if match.group(3) == "-":
        bonus = -bonus
    if count < 1 or count > 20 or sides not in (4, 6, 8, 10, 12, 20, 100):
        raise ValueError(f"unsupported dice expression: {expr!r}")
    return DiceExpr(count, sides, bonus)


@dataclass(frozen=True)
class DiceResult:
    expr: str
    rolls: tuple[int, ...]
    bonus: int
    total: int


def roll_expr(expr: str | DiceExpr, extra_bonus: int = 0, critical: bool = False) -> DiceResult:
    """Roll e.g. "2d6+3". A critical doubles the number of dice, not the bonus."""
    parsed = parse(expr) if isinstance(expr, str) else expr
    count = parsed.count * (2 if critical else 1)
    rolls = tuple(roll_multiple(count, parsed.sides))
    bonus = parsed.bonus + extra_bonus
    return DiceResult(expr=str(parsed), rolls=rolls, bonus=bonus, total=max(0, sum(rolls) + bonus))
