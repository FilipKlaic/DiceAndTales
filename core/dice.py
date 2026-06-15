import random


def roll(sides: int) -> int:
    return random.randint(1, sides)


def roll_multiple(count: int, sides: int) -> list[int]:
    return [roll(sides) for _ in range(count)]


def roll_stat() -> int:
    rolls = roll_multiple(4, 6)
    return sum(sorted(rolls)[1:])


def d4() -> int: return roll(4)
def d6() -> int: return roll(6)
def d8() -> int: return roll(8)
def d10() -> int: return roll(10)
def d12() -> int: return roll(12)
def d20() -> int: return roll(20)
