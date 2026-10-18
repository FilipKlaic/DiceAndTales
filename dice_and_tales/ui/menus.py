"""Title screen and character creation."""

import asyncio
import random

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Input, Label, OptionList, Static
from textual.widgets.option_list import Option

from dice_and_tales import __version__
from dice_and_tales.core.character import apply_racial_bonuses, arrange_for_class, create_character, roll_scores
from dice_and_tales.core.rules import (
    ABILITIES, ABILITY_LABELS, CLASSES, HEROIC_HP_BONUS, RACES, CharacterClass, Race, modifier, skill_label,
)
from dice_and_tales.game import saves
from dice_and_tales.ui.art import LOGO

MAX_ROLLS = 3


class TitleScreen(Screen):
    BINDINGS = [Binding("q", "app.quit", "Quit")]

    def compose(self) -> ComposeResult:
        with Vertical(id="title-box"):
            yield Static(Text(LOGO, style="bold yellow"), id="logo")
            yield Static(Text("A tale of dice, a tavern and a tomb that should have stayed shut.", style="italic"),
                         id="tagline")
            with Center():
                yield OptionList(id="title-menu")
            yield Static(id="dm-status")
            yield Static(f"v{__version__}", id="version")
        yield Footer()

    def on_screen_resume(self) -> None:
        self.refresh_menu()

    def on_mount(self) -> None:
        self.refresh_menu()

    def refresh_menu(self) -> None:
        menu = self.query_one("#title-menu", OptionList)
        menu.clear_options()
        auto = saves.info("auto")
        if auto and self.app.autosave_resumable():
            menu.add_option(Option(f"Continue: {auto.label}", id="continue"))
        menu.add_options([
            Option("New adventure", id="new"),
            Option("Load game", id="load"),
            Option("Settings", id="settings"),
            Option("Quit", id="quit"),
        ])
        menu.highlighted = 0
        menu.focus()
        self.query_one("#dm-status", Static).update(self.app.dm_status())

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        choice = event.option.id
        if choice == "continue":
            self.app.load_game("auto")
        elif choice == "new":
            self.app.push_screen(CreationScreen())
        elif choice == "load":
            self.app.open_load_dialog()
        elif choice == "settings":
            self.app.open_settings(on_close=self.refresh_menu)
        elif choice == "quit":
            self.app.exit()


class CreationScreen(Screen):
    BINDINGS = [Binding("escape", "app.pop_screen", "Back")]

    def __init__(self):
        super().__init__()
        self.rolled, self.rolled_raw = roll_scores()
        self.rolls_used = 1
        self.rolling = False

    def compose(self) -> ComposeResult:
        with Horizontal(id="create"):
            with Vertical(id="create-left"):
                yield Label("What is your name, adventurer?", classes="field-label")
                yield Input(placeholder="Your name", max_length=24, id="name")
                yield Label("Class", classes="field-label")
                yield OptionList(*[Option(c.value, id=c.name) for c in CharacterClass], id="classes")
                yield Label("Race", classes="field-label")
                yield OptionList(*[Option(r.value, id=r.name) for r in Race], id="races")
            with Vertical(id="create-right"):
                yield Static(id="preview")
                with Horizontal(id="create-buttons"):
                    yield Button("Reroll stats", id="reroll")
                    yield Button("Begin adventure", variant="success", id="begin")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#classes", OptionList).highlighted = 0
        self.query_one("#races", OptionList).highlighted = 0
        self.query_one("#name", Input).focus()
        self.update_preview()

    @property
    def chosen_class(self) -> CharacterClass:
        index = self.query_one("#classes", OptionList).highlighted or 0
        return list(CharacterClass)[index]

    @property
    def chosen_race(self) -> Race:
        index = self.query_one("#races", OptionList).highlighted or 0
        return list(Race)[index]

    def on_option_list_option_highlighted(self, _event) -> None:
        self.update_preview()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        # Enter on a list moves to the next field.
        if event.option_list.id == "classes":
            self.query_one("#races", OptionList).focus()
        else:
            self.query_one("#begin", Button).focus()

    def on_input_submitted(self, _event: Input.Submitted) -> None:
        self.query_one("#classes", OptionList).focus()

    def update_preview(self, scores: dict[str, int] | None = None) -> None:
        cls, race = self.chosen_class, self.chosen_race
        self.base_scores, self.raw = arrange_for_class(self.rolled, self.rolled_raw, cls)
        spec, rspec = CLASSES[cls], RACES[race]
        final = apply_racial_bonuses(scores or self.base_scores, race)
        t = Text()
        t.append(f"{race.value} {cls.value}\n", style="bold yellow")
        t.append(spec.blurb + "\n\n", style="italic")
        t.append("Ability scores (4d6 drop lowest, best rolls on your class's key abilities)\n", style="bold underline")
        for ability in ABILITIES:
            bonus = rspec.bonuses.get(ability, 0)
            dice_str = ""
            if scores is None:
                kept = sorted(self.raw[ability])
                dice_str = f"  [{kept[0]}] " + " ".join(map(str, kept[1:]))
            mark = "★" if ability in (spec.weapon.ability, spec.spellcasting) else " "
            t.append(f" {mark}{ABILITY_LABELS[ability]} {final[ability]:>2} ({modifier(final[ability]):+d})")
            t.append(f"{' +' + str(bonus) if bonus else '':>4}", style="green")
            t.append(dice_str + "\n", style="grey50")
        hp = max(1, spec.hit_die + modifier(final["constitution"])) + HEROIC_HP_BONUS
        dex = modifier(final["dexterity"])
        ac = spec.base_ac + (dex if spec.ac_dex_cap is None else min(dex, spec.ac_dex_cap))
        t.append(f"\nHP {hp}   AC {ac}   Weapon: {spec.weapon.name} ({spec.weapon.damage})\n", style="bold")
        t.append("Skills: " + ", ".join(skill_label(s) for s in spec.skills) + "\n\n")
        for feature in spec.features:
            t.append(f"• {feature}\n")
        t.append(f"\n{race.value}: {rspec.blurb}\n", style="cyan")
        self.query_one("#preview", Static).update(t)
        left = MAX_ROLLS - self.rolls_used
        button = self.query_one("#reroll", Button)
        button.label = f"Reroll stats ({left} left)"
        button.disabled = left <= 0 or self.rolling

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "reroll" and self.rolls_used < MAX_ROLLS and not self.rolling:
            self.rolling = True
            self.rolls_used += 1
            if self.app.settings.animations:
                for _ in range(8):
                    self.update_preview({a: random.randint(3, 18) for a in ABILITIES})
                    await asyncio.sleep(0.05)
            self.rolled, self.rolled_raw = roll_scores()
            self.rolling = False
            self.update_preview()
        elif event.button.id == "begin":
            name = self.query_one("#name", Input).value.strip()
            if not name:
                self.notify("Every hero needs a name.", severity="warning")
                self.query_one("#name", Input).focus()
                return
            character = create_character(name, self.chosen_class, self.chosen_race, self.base_scores)
            self.app.start_new_game(character)
