"""Modal dialogs layered over the game screen."""

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from dice_and_tales.config import TEXT_SPEEDS, Settings
from dice_and_tales.core.rules import ABILITIES, ABILITY_LABELS, TRAIT_LABELS, skill_label
from dice_and_tales.game import saves


class Dialog(ModalScreen):
    """Base: a centred panel that closes on Escape."""

    BINDINGS = [Binding("escape", "close", "Close")]
    TITLE_TEXT = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog") as box:
            box.border_title = self.TITLE_TEXT
            yield from self.body()

    def body(self) -> ComposeResult:
        yield from ()

    def action_close(self) -> None:
        self.dismiss(None)


class MenuDialog(Dialog):
    """A dialog whose body is a list of options; dismisses with the chosen option id."""

    def __init__(self, title: str, options: list[tuple[str, str, bool]], intro: str = ""):
        super().__init__()
        self.TITLE_TEXT = title
        self.options = options
        self.intro = intro

    def body(self) -> ComposeResult:
        if self.intro:
            yield Static(self.intro, classes="dialog-intro")
        yield OptionList(*[Option(label, id=oid, disabled=not enabled) for oid, label, enabled in self.options])

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option.id)


class SheetDialog(Dialog):
    TITLE_TEXT = "Character Sheet"

    def __init__(self, character):
        super().__init__()
        self.character = character

    def body(self) -> ComposeResult:
        c = self.character
        t = Text()
        t.append(f"{c.name}\n", style="bold")
        t.append(f"Level {c.level} {c.title}   XP {c.xp}" + (f"/{c.next_level_xp}" if c.next_level_xp else "") + "\n\n")
        t.append(f"HP {c.current_hp}/{c.max_hp}   AC {c.armor_class}   Proficiency +{c.proficiency}   Gold {c.gold}\n")
        if c.spec.spellcasting:
            t.append(f"Spell attack {c.spell_attack_bonus:+d}   Spell save DC {c.spell_save_dc}\n")
        w = c.spec.weapon
        t.append(f"Weapon: {w.name} {c.weapon_attack_bonus:+d} to hit, {w.damage}{c.mod(w.ability):+d} {w.damage_type}\n\n")
        t.append("Abilities\n", style="bold underline")
        for ability in ABILITIES:
            t.append(f"  {ABILITY_LABELS[ability]}  {c.scores[ability]:>2}  ({c.mod(ability):+d})\n")
        t.append("\nProficient skills: ", style="bold")
        t.append(", ".join(skill_label(s) for s in c.spec.skills) + "\n\n")
        t.append("Class features\n", style="bold underline")
        for feature in c.spec.features:
            t.append(f"  • {feature}\n")
        t.append("  • Hero's Vigor: +6 HP at level 1.\n")
        t.append(f"\n{c.race.value}: ", style="bold")
        t.append(c.race_spec.blurb + "\n")
        if c.race_spec.traits:
            t.append("Traits: " + ", ".join(TRAIT_LABELS[x] for x in c.race_spec.traits) + "\n")
        yield VerticalScroll(Static(t))


class InventoryDialog(Dialog):
    """Lists items; selecting a potion drinks it (dismisses with its id)."""

    TITLE_TEXT = "Inventory"

    def __init__(self, character, in_combat: bool):
        super().__init__()
        self.character = character
        self.in_combat = in_combat

    def body(self) -> ComposeResult:
        c = self.character
        yield Static(f"Gold: {c.gold}.  Select a potion to drink it." if not self.in_combat
                     else "Use the combat options to drink potions in a fight.", classes="dialog-intro")
        if not c.inventory:
            yield Static("Your pack is empty.")
            return
        options = []
        for index, item in enumerate(c.inventory):  # ids by position: duplicates are normal
            label = Text()
            label.append(item.name, style="bold yellow" if item.kind == "quest" else "bold")
            label.append(f"\n  {item.description}", style="grey70")
            options.append(Option(label, id=str(index)))
        yield OptionList(*options)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        item = self.character.inventory[int(event.option.id)]
        if item.heal and not self.in_combat:
            self.dismiss(item.id)


class JournalDialog(Dialog):
    TITLE_TEXT = "Journal"

    def __init__(self, entries):
        super().__init__()
        self.entries = entries

    def body(self) -> ComposeResult:
        t = Text()
        if not self.entries:
            t.append("Nothing worth writing down yet.", style="italic")
        last_where = None
        for entry in self.entries:
            if entry.where != last_where:
                t.append(f"\n{entry.where}\n", style="bold underline")
                last_where = entry.where
            t.append("  • ")
            t.append(entry.text + "\n", style="italic cyan" if entry.source == "dm" else "")
        yield VerticalScroll(Static(t))


HELP = """[b]How to play[/b]
Pick an option with [b]1-9[/b] (or the arrow keys and Enter), or press [b]/[/b] and describe
anything you want to try in your own words. The AI Dungeon Master narrates the result,
but the dice decide: risky actions trigger real ability checks with your modifiers.

[b]Keys[/b]
  [b]1-9[/b]        choose an option            [b]/[/b]   describe your own action
  [b]c[/b]          character sheet             [b]i[/b]   inventory (drink potions)
  [b]j[/b]          journal                     [b]r[/b]   rest (short or long)
  [b]space[/b]      skip the text animation     [b]?[/b]   this help
  [b]ctrl+s[/b]     save                        [b]esc[/b] menu

[b]Rules in brief[/b]
  Checks: d20 + ability modifier (+2 if proficient) against a DC. Natural 20 always
  succeeds, natural 1 always fails. Advantage rolls two dice and keeps the higher.
  Combat: attack rolls go against Armour Class. Skeletons hate blunt weapons; the dead
  hate radiant light. Fleeing is a STR/DEX check (Rogues always get away).
  Rest: short rests (2 per day) heal a hit die and refresh Second Wind and Turn Undead.
  A long rest in the tavern (2 gold) restores everything.
"""


class HelpDialog(Dialog):
    TITLE_TEXT = "Help"

    def body(self) -> ComposeResult:
        yield VerticalScroll(Static(HELP))


def save_slot_options(include_auto: bool, for_saving: bool) -> list[tuple[str, str, bool]]:
    options = []
    for slot in saves.SLOTS:
        if slot == "auto" and not include_auto:
            continue
        info = saves.info(slot)
        name = "Autosave" if slot == "auto" else f"Slot {slot}"
        label = f"{name}: {info.label}" if info else f"{name}: (empty)"
        options.append((slot, label, for_saving or info is not None))
    return options


class SettingsDialog(Dialog):
    TITLE_TEXT = "Settings"

    def __init__(self, settings: Settings, dm_status: str):
        super().__init__()
        self.settings = settings
        self.dm_status = dm_status

    def body(self) -> ComposeResult:
        yield Static(self.dm_status, classes="dialog-intro")
        yield OptionList(*self._options(), id="settings-list")

    def _options(self) -> list[Option]:
        s = self.settings
        return [
            Option(f"Text speed: {s.text_speed}", id="text_speed"),
            Option(f"Dice animations: {'on' if s.animations else 'off'}", id="animations"),
            Option(f"AI Dungeon Master: {'on' if s.dm_enabled else 'off'}", id="dm_enabled"),
            Option("Done", id="done"),
        ]

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        s = self.settings
        if event.option.id == "done":
            s.save()
            self.dismiss(True)
            return
        if event.option.id == "text_speed":
            speeds = list(TEXT_SPEEDS)
            s.text_speed = speeds[(speeds.index(s.text_speed) + 1) % len(speeds)]
        elif event.option.id == "animations":
            s.animations = not s.animations
        elif event.option.id == "dm_enabled":
            s.dm_enabled = not s.dm_enabled
        option_list = self.query_one("#settings-list", OptionList)
        index = option_list.highlighted
        option_list.clear_options()
        option_list.add_options(self._options())
        option_list.highlighted = index

    def action_close(self) -> None:
        self.settings.save()
        self.dismiss(True)


class GameOverDialog(Dialog):
    BINDINGS = []

    def __init__(self, engine):
        super().__init__()
        self.engine = engine
        state = engine.state
        self.TITLE_TEXT = "Victory" if state.victory else "The End"

    def body(self) -> ComposeResult:
        state = self.engine.state
        c = state.character
        t = Text(justify="center")
        t.append(f"\n{state.ending}\n\n", style="bold yellow" if state.victory else "bold red")
        t.append(f"{c.name}, level {c.level} {c.title}\n")
        t.append(f"{state.turns} turns · {c.xp} XP · {c.gold} gold · {len(state.visited)} places seen\n\n")
        endings = len({s.ending for s in self.engine.story.scenes.values() if s.ending})
        t.append(f"There are {endings} endings to find, plus one you'd rather avoid.\n", style="italic grey70")
        yield Static(t)
        yield OptionList(
            Option("Start a new adventure", id="new"),
            Option("Load a saved game", id="load"),
            Option("Return to the title screen", id="title"),
        )

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option.id)
