import os
import random
import time

from core.character import Character, stat_modifier


def clear(last_action: str = None):
    os.system('cls' if os.name == 'nt' else 'clear')
    print("=== Dice & Tales ===")
    if last_action:
        print(f">> {last_action}")
    print("=" * 20)
    print()


def _typewrite(text: str, delay: float = 0.015) -> None:
    for char in text:
        print(char, end="", flush=True)
        time.sleep(delay)
    print()


def print_scene(description: str):
    _typewrite(description)
    print()


def print_options(options: dict, freeform: bool = False):
    print("What do you do?")
    for option in options:
        print(f"  > {option}")
    print("  > stats")
    if freeform:
        print("  > or describe your own action...")
    print()


def print_check(description: str, roll: int, modifier: int, total: int, dc: int, success: bool):
    print("\n  Rolling", end="", flush=True)
    for _ in range(5):
        time.sleep(0.14)
        print(".", end="", flush=True)
    print("\n")

    for i in range(12):
        fake = random.randint(1, 20)
        print(f"\r  d20 [ {fake:2d} ]  ", end="", flush=True)
        time.sleep(0.06 + i * 0.014)

    print(f"\r  d20 [ {roll:2d} ] {modifier:+d} = {total}  (DC {dc})")
    time.sleep(0.5)
    print(f"\n  {'SUCCESS' if success else 'FAILURE'}\n")
    time.sleep(1.5)


def print_character_sheet(character: Character):
    s = character.stats
    entries = [
        ("STR", s.strength),
        ("DEX", s.dexterity),
        ("CON", s.constitution),
        ("INT", s.intelligence),
        ("WIS", s.wisdom),
        ("CHA", s.charisma),
    ]
    print(f"\n{'=' * 32}")
    print(f"  {character.name}")
    print(f"  {character.race.value} {character.character_class.value}")
    print(f"  HP: {character.current_hp} / {character.max_hp}")
    print(f"{'─' * 32}")
    for label, score in entries:
        mod = stat_modifier(score)
        print(f"  {label}: {score:2d}  ({mod:+d})")
    print(f"{'=' * 32}\n")
    input("Press Enter to continue...")
