import os
import time

from core.character import Character, stat_modifier


def clear(last_action: str = None):
    os.system('cls' if os.name == 'nt' else 'clear')
    print("=== Dice & Tales ===")
    if last_action:
        print(f">> {last_action}")
    print("=" * 20)
    print()


def print_scene(description: str):
    print(description)
    print()


def print_options(options: dict):
    print("What do you do?")
    for option in options:
        print(f"  > {option}")
    print("  > stats")
    print()


def print_check(description: str, roll: int, modifier: int, total: int, dc: int, success: bool):
    print(f"\n  Rolled: d20 [{roll}] {modifier:+d} = {total}  (DC {dc})")
    print(f"  Result: {'SUCCESS' if success else 'FAILURE'}\n")
    time.sleep(2)


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
