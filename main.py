from core.character import CharacterClass, Race, create_character
from game.engine import GameEngine
from game.narrator import Narrator
import ui.display as display
from ui.input_handler import get_text, get_numbered_choice


def create_new_character():
    display.clear()
    print("=== Dice & Tales ===\n")
    print("Before your adventure begins, we must know who you are.\n")

    name = get_text("What is your name, adventurer?")

    print("\nChoose your class:")
    classes = list(CharacterClass)
    class_choice = get_numbered_choice([c.value for c in classes])
    chosen_class = next(c for c in classes if c.value == class_choice)

    print("\nChoose your race:")
    races = list(Race)
    race_choice = get_numbered_choice([r.value for r in races])
    chosen_race = next(r for r in races if r.value == race_choice)

    character = create_character(name, chosen_class, chosen_race)

    display.clear("Character created!")
    print("Your stats have been rolled.\n")
    display.print_character_sheet(character)

    return character


def main():
    character = create_new_character()
    narrator = Narrator()
    if not narrator.available:
        print("\nNote: ANTHROPIC_API_KEY not set — freeform storytelling disabled.")
        print("Set it to type your own actions and have the story respond.\n")
        input("Press Enter to start the adventure...")
        narrator = None
    engine = GameEngine(character, narrator)
    engine.run()


if __name__ == "__main__":
    main()
