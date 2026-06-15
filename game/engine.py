import sys
import time

from core.character import Character, stat_modifier
from core.dice import d20
from game.story import scenes
import ui.display as display
import ui.input_handler as input_handler


class GameEngine:
    def __init__(self, character: Character):
        self.character = character
        self.current_scene = "tavern_entrance"
        self.last_action = f"Started adventure as {character.name}"

    def run(self):
        while True:
            if self.current_scene == "restart":
                self._handle_restart()
                continue

            scene = scenes.get(self.current_scene)
            if not scene:
                print(f"Error: scene '{self.current_scene}' not found.")
                break

            display.clear(self.last_action)
            print(f"HP: {self.character.current_hp} / {self.character.max_hp}\n")
            display.print_scene(scene.description)

            if scene.check:
                self._resolve_check(scene.check)
                continue

            if scene.is_terminal:
                input("Press Enter to continue...")
                self.current_scene = "restart"
                continue

            display.print_options(scene.options)
            choice = input_handler.get_choice(scene.options)

            if choice == "stats":
                display.print_character_sheet(self.character)
                continue

            self.last_action = f"Chose: {choice}"
            self.current_scene = scene.options[choice]

    def _resolve_check(self, check):
        print(f"[ {check.description} ]")
        input("\nPress Enter to roll...")

        stat_score = getattr(self.character.stats, check.stat)
        modifier = stat_modifier(stat_score)
        roll = d20()
        total = roll + modifier
        success = total >= check.dc

        display.print_check(check.description, roll, modifier, total, check.dc, success)

        if check.combat and not success:
            damage = max(1, 4 - modifier)
            self.character.current_hp = max(0, self.character.current_hp - damage)
            print(f"  You took {damage} damage!  HP: {self.character.current_hp}/{self.character.max_hp}\n")
            time.sleep(1.5)

            if not self.character.is_alive:
                print("  You have fallen. Your adventure ends here.")
                input("\nPress Enter to continue...")
                self.current_scene = "restart"
                return

        result_text = "success" if success else "fail"
        self.last_action = f"{check.stat.upper()} check ({total} vs DC {check.dc}) — {result_text}"
        self.current_scene = check.success_scene if success else check.fail_scene

    def _handle_restart(self):
        display.clear("Game Over")
        print("Play again? (yes / no)")
        if input("> ").strip().lower() == "yes":
            self.current_scene = "tavern_entrance"
            self.character.current_hp = self.character.max_hp
            self.last_action = "Started a new adventure"
        else:
            print("\nFarewell, adventurer.")
            sys.exit(0)
