"""The main game screen: narrative log, choices, free-text input and the sidebar."""

import asyncio

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Input, OptionList, Static
from textual.widgets.option_list import Option

from dice_and_tales.core.events import (
    CombatEndEvent, CombatStartEvent, DamageEvent, Event, GameOverEvent, GoldEvent, HealEvent, ItemEvent,
    Narration, Notice, RollEvent, SceneEvent, XPEvent,
)
from dice_and_tales.game import saves
from dice_and_tales.game.engine import COMBAT, Engine
from dice_and_tales.ui.art import SCENES
from dice_and_tales.ui.modals import (
    GameOverDialog, HelpDialog, InventoryDialog, JournalDialog, MenuDialog, SheetDialog, save_slot_options,
)
from dice_and_tales.ui.widgets import CharacterPanel, DiceLog, DiceRoll, EnemyPanel

STYLES = {
    "normal": "",
    "dialogue": "italic",
    "danger": "bold red",
    "loot": "green",
    "system": "italic grey62",
    "dm": "",
}
COMBAT_END_TEXT = {"victory": ("VICTORY", "bold black on green"), "fled": ("YOU ESCAPED", "bold black on yellow"),
                   "defeat": ("DEFEAT", "bold white on red")}


class GameScreen(Screen):
    BINDINGS = [
        *[Binding(str(n), f"pick({n - 1})", show=False) for n in range(1, 10)],
        Binding("slash", "focus_input", "Act freely"),
        Binding("c", "sheet", "Sheet"),
        Binding("i", "inventory", "Pack"),
        Binding("j", "journal", "Journal"),
        Binding("r", "rest", "Rest"),
        Binding("question_mark", "help", "Help"),
        Binding("ctrl+s", "save", "Save"),
        Binding("space", "skip", "Skip text", show=False),
        Binding("escape", "menu", "Menu"),
    ]

    def __init__(self, engine: Engine, intro: list[Event] | None):
        super().__init__()
        self.engine = engine
        self.intro = intro
        self.queue: asyncio.Queue = asyncio.Queue()
        self.busy = True
        self.dm_thinking = False
        self.skip = False
        self.game_over_pending = False
        self._dm_paragraph: Static | None = None
        self._dm_seen: set[int] = set()

    # --- Layout ---------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Horizontal(id="game"):
            with Vertical(id="main"):
                yield VerticalScroll(id="log")
                yield Static("The Dungeon Master is thinking...", id="thinking")
                yield OptionList(id="choices")
                yield Input(id="action", max_length=300)
            with VerticalScroll(id="sidebar"):
                yield EnemyPanel(id="enemies")
                yield CharacterPanel(id="character")
                yield DiceLog(id="dicelog")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#thinking").display = False
        self.refresh_panels()
        self.run_worker(self._render_loop(), exclusive=False, group="render")
        if self.intro is not None:
            self.enqueue(self.intro)
        else:
            self.enqueue([SceneEvent(self.engine.state.scene_id), Notice("Game loaded.")])

    @property
    def settings(self):
        return self.app.settings

    @property
    def log_view(self) -> VerticalScroll:
        return self.query_one("#log", VerticalScroll)

    # --- Rendering pipeline ---------------------------------------------

    def enqueue(self, events: list[Event]) -> None:
        self.busy = True
        self._sync_controls()
        self.queue.put_nowait(("events", events))
        self.queue.put_nowait(("settle", None))

    async def _render_loop(self) -> None:
        while True:
            kind, payload = await self.queue.get()
            if kind == "events":
                for event in payload:
                    await self.render_event(event)
            elif kind == "dm_text":
                self._append_dm_text(payload)
            elif kind == "dm_retract":
                self._retract_dm_text(payload)
            elif kind == "dm_event":
                self._dm_paragraph = None  # narration after a roll starts below it
                await self.render_event(payload)
            elif kind == "settle" and self.queue.empty() and not self.dm_thinking:
                self._settle()

    def _settle(self) -> None:
        self.busy = False
        self.skip = False
        self._dm_paragraph = None
        self.refresh_panels()
        self.refresh_choices()
        self.autosave()
        if self.game_over_pending:
            self.game_over_pending = False
            self.app.push_screen(GameOverDialog(self.engine), self._game_over_choice)

    async def write(self, text: str | Text, classes: str = "para", typewrite: bool = False, style: str = "") -> Static:
        widget = Static(classes=classes)
        await self.log_view.mount(widget)
        content = text if isinstance(text, Text) else Text(text, style=style)
        if typewrite and isinstance(text, str):
            await self._typewrite(widget, text, style)
        else:
            widget.update(content)
        self.log_view.scroll_end(animate=False)
        return widget

    async def _typewrite(self, widget: Static, text: str, style: str) -> None:
        delay = self.settings.char_delay
        if delay <= 0:
            widget.update(Text(text, style=style))
            return
        step = max(1, round(0.016 / delay))
        shown = 0
        while shown < len(text) and not self.skip:
            shown = min(len(text), shown + step)
            widget.update(Text(text[:shown], style=style))
            self.log_view.scroll_end(animate=False)
            await asyncio.sleep(delay * step)
        widget.update(Text(text, style=style))

    async def render_event(self, event: Event) -> None:
        if isinstance(event, SceneEvent):
            scene = self.engine.story[event.scene_id]
            header = Text()
            art = SCENES.get(scene.art or "")
            if art:
                header.append(art.strip("\n") + "\n", style="grey50")
            header.append(f"── {scene.title} ", style="bold yellow")
            header.append("─" * max(4, 50 - len(scene.title)), style="yellow")
            await self.write(header, classes="scene-header")
            await self.write(self.engine.scene_text(event.scene_id), typewrite=True)
        elif isinstance(event, Narration):
            await self.write(event.text, typewrite=True, style=STYLES.get(event.style, ""))
        elif isinstance(event, Notice):
            await self.write(event.text, classes="notice", style=STYLES.get(event.style, "italic grey62"))
        elif isinstance(event, RollEvent):
            die = DiceRoll(event, animate=self.settings.animations and not self.skip)
            await self.log_view.mount(die)
            self.log_view.scroll_end(animate=False)
            await die.play()
            self.query_one(DiceLog).add(event)
        elif isinstance(event, DamageEvent):
            if event.target == "player":
                text = f"-{event.amount} HP ({event.damage_type}"
                text += f", from {event.source})" if event.source else ")"
                text += f"   HP {event.hp}/{event.max_hp}"
                await self.write(text, classes="effect", style="bold red")
                self._flash("#character", "hurt")
            else:
                text = f"{event.target} takes {event.amount} {event.damage_type} damage"
                text += f" [{event.source}]" if event.source else ""
                text += f"   ({event.hp}/{event.max_hp})"
                await self.write(text, classes="effect", style="yellow")
            self.refresh_panels()
        elif isinstance(event, HealEvent):
            src = f" ({event.source})" if event.source else ""
            await self.write(f"+{event.amount} HP{src}   HP {event.hp}/{event.max_hp}", classes="effect", style="bold green")
            self._flash("#character", "healed")
            self.refresh_panels()
        elif isinstance(event, ItemEvent):
            verb, style = ("Gained", "bold green") if event.gained else ("Lost", "grey62")
            await self.write(f"{verb}: {event.name}", classes="effect", style=style)
            self.refresh_panels()
        elif isinstance(event, GoldEvent):
            sign = "+" if event.amount >= 0 else ""
            await self.write(f"{sign}{event.amount} gold (now {event.total})", classes="effect", style="bold yellow")
            self.refresh_panels()
        elif isinstance(event, XPEvent):
            if event.amount:
                await self.write(f"+{event.amount} XP", classes="effect", style="magenta")
            self.refresh_panels()
        elif isinstance(event, CombatStartEvent):
            banner = Text(f" ⚔  COMBAT: {', '.join(event.enemies)}  ⚔ ", style="bold white on dark_red")
            await self.write(banner, classes="banner")
            self.refresh_panels()
        elif isinstance(event, CombatEndEvent):
            label, style = COMBAT_END_TEXT[event.result]
            await self.write(Text(f"  {label}  ", style=style), classes="banner")
            self.refresh_panels()
        elif isinstance(event, GameOverEvent):
            style = "bold black on yellow" if event.victory else "bold white on grey30"
            await self.write(Text(f"  ✦ {event.title} ✦  ", style=style), classes="banner")
            self.game_over_pending = True

    def _flash(self, selector: str, css_class: str) -> None:
        if not self.settings.animations:
            return
        widget = self.query_one(selector)
        widget.add_class(css_class)
        self.set_timer(0.5, lambda: widget.remove_class(css_class))

    def _append_dm_text(self, chunk: str) -> None:
        if self._dm_paragraph is None:
            self._dm_paragraph = Static(classes="para dm")
            self._dm_paragraph.dm_text = ""
            self.log_view.mount(self._dm_paragraph)
        self._dm_paragraph.dm_text += chunk
        self._dm_paragraph.update(Text(self._dm_paragraph.dm_text.lstrip()))
        self.log_view.scroll_end(animate=False)

    def _retract_dm_text(self, count: int) -> None:
        paragraph = self._dm_paragraph
        if paragraph is None or count <= 0:
            return
        paragraph.dm_text = paragraph.dm_text[:-count] if count < len(paragraph.dm_text) else ""
        paragraph.update(Text(paragraph.dm_text.lstrip()))

    # --- Controls -------------------------------------------------------

    def refresh_panels(self) -> None:
        self.query_one(CharacterPanel).show(self.engine)
        self.query_one(EnemyPanel).show(self.engine.state.combat)

    def refresh_choices(self) -> None:
        choices_list = self.query_one("#choices", OptionList)
        choices_list.clear_options()
        for i, choice in enumerate(self.engine.choices()):
            label = Text()
            label.append(f"{i + 1}. " if i < 9 else "   ", style="bold cyan")
            label.append(choice.label, style="" if choice.enabled else "grey50")
            if choice.tag:
                label.append(f"  [{choice.tag}]", style="grey62")
            if not choice.enabled and choice.reason:
                label.append(f"  ({choice.reason})", style="grey50 italic")
            choices_list.add_option(Option(label, id=choice.key, disabled=not choice.enabled))
        self._sync_controls()
        if choices_list.option_count:
            choices_list.highlighted = next(
                (i for i in range(choices_list.option_count) if not choices_list.get_option_at_index(i).disabled), None)
        if not isinstance(self.focused, Input):
            choices_list.focus()

    def _sync_controls(self) -> None:
        action = self.query_one("#action", Input)
        engine = self.engine
        action.disabled = self.busy or not engine.can_freeform
        if engine.can_freeform:
            action.placeholder = "Press / and describe what you do. The Dungeon Master will answer."
        elif engine.mode == COMBAT:
            action.placeholder = "In combat: choose an action above."
        elif engine.dm_available:
            action.placeholder = "Choose an option above."
        else:
            action.placeholder = self.app.dm_offline_hint()
        self.query_one("#choices", OptionList).disabled = self.busy
        self.query_one("#thinking").display = self.dm_thinking

    def do_choice(self, key: str, label: str) -> None:
        if self.busy:
            return
        self.log_view.mount(Static(Text(f"> {label}", style="bold cyan"), classes="echo"))
        events = self.engine.choose(key)
        self.enqueue(events)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        choice = next((c for c in self.engine.choices() if c.key == event.option.id), None)
        if choice:
            self.do_choice(choice.key, choice.label)

    def action_pick(self, index: int) -> None:
        if self.busy:
            return
        choices = self.engine.choices()
        if index >= len(choices):
            return
        choice = choices[index]
        if not choice.enabled:
            self.notify(f"Not available: {choice.reason}", severity="warning")
            return
        self.do_choice(choice.key, choice.label)

    def action_focus_input(self) -> None:
        action = self.query_one("#action", Input)
        if action.disabled:
            if not self.engine.dm_available:
                self.notify(self.app.dm_offline_hint(), severity="warning", timeout=6)
            return
        action.focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        event.input.value = ""
        if not text or self.busy or not self.engine.can_freeform:
            return
        self.query_one("#choices", OptionList).focus()
        self.log_view.mount(Static(Text(f"> {text}", style="bold cyan"), classes="echo"))
        self.log_view.scroll_end(animate=False)
        self.busy = True
        self.dm_thinking = True
        self._dm_seen = set()
        self._dm_paragraph = None
        self._sync_controls()
        self.run_worker(lambda: self._run_dm(text), thread=True, exclusive=True, group="dm")

    def _run_dm(self, text: str) -> None:
        call = self.app.call_from_thread

        def on_text(chunk: str) -> None:
            call(self._on_dm_text, chunk)

        def on_event(event: Event) -> None:
            self._dm_seen.add(id(event))
            call(self.queue.put_nowait, ("dm_event", event))

        def on_retract(count: int) -> None:
            call(self.queue.put_nowait, ("dm_retract", count))

        try:
            events = self.engine.freeform(text, on_text=on_text, on_event=on_event, on_retract=on_retract)
        except Exception as exc:  # never let a DM failure take the game down
            events = [Notice(f"The Dungeon Master stumbled: {exc}", "danger")]
        remaining = [e for e in events if id(e) not in self._dm_seen]
        call(self._dm_finished, remaining)

    def _on_dm_text(self, chunk: str) -> None:
        self.queue.put_nowait(("dm_text", chunk))

    def _dm_finished(self, remaining: list[Event]) -> None:
        self.dm_thinking = False
        self.query_one("#thinking").display = False
        self._dm_paragraph = None
        self.enqueue(remaining)

    def action_skip(self) -> None:
        if self.busy:
            self.skip = True

    def autosave(self) -> None:
        # Never autosave a finished game: the last checkpoint stays loadable after a death.
        if self.engine.can_save and not self.engine.state.ending:
            try:
                saves.save(self.engine.state, "auto", where=self.engine.scene.title)
            except OSError as exc:
                self.notify(f"Autosave failed: {exc}", severity="error")

    # --- Dialogs --------------------------------------------------------

    def action_sheet(self) -> None:
        self.app.push_screen(SheetDialog(self.engine.character))

    def action_journal(self) -> None:
        self.app.push_screen(JournalDialog(self.engine.state.journal))

    def action_help(self) -> None:
        self.app.push_screen(HelpDialog())

    def action_inventory(self) -> None:
        if self.busy:
            return

        def use(item_id):
            if item_id:
                self.enqueue(self.engine.use_item(item_id))
        self.app.push_screen(InventoryDialog(self.engine.character, self.engine.mode == COMBAT), use)

    def action_rest(self) -> None:
        if self.busy:
            return
        c = self.engine.character
        exploring = self.engine.can_save
        left = c.resources.get("short_rests", 0)
        safe = self.engine.scene.safe
        options = [
            ("short", f"Short rest: one hour, spend a hit die ({left} left today)", exploring and left > 0),
            ("long", "Long rest: rent a room for the night (2 gold)" if safe else "Long rest: only somewhere safe, like the tavern",
             exploring and safe and c.gold >= 2),
            ("cancel", "Never mind", True),
        ]

        def done(choice):
            if choice == "short":
                self.enqueue(self.engine.short_rest())
            elif choice == "long":
                self.enqueue(self.engine.long_rest())
        self.app.push_screen(MenuDialog("Rest", options), done)

    def action_save(self) -> None:
        if self.busy:
            return
        if not self.engine.can_save:
            self.notify("You can't save in the middle of a fight.", severity="warning")
            return

        def done(slot):
            if not slot:
                return
            try:
                saves.save(self.engine.state, slot, where=self.engine.scene.title)
                self.notify(f"Saved to slot {slot}.")
            except OSError as exc:
                self.notify(f"Save failed: {exc}", severity="error")
        self.app.push_screen(MenuDialog("Save game", save_slot_options(include_auto=False, for_saving=True)), done)

    def action_menu(self) -> None:
        if isinstance(self.focused, Input):
            self.query_one("#choices", OptionList).focus()
            return
        options = [
            ("resume", "Resume", True),
            ("save", "Save game", self.engine.can_save),
            ("load", "Load game", True),
            ("settings", "Settings", True),
            ("help", "Help", True),
            ("title", "Quit to title screen", True),
            ("quit", "Quit game", True),
        ]

        def done(choice):
            if choice == "save":
                self.action_save()
            elif choice == "load":
                self.app.open_load_dialog()
            elif choice == "settings":
                self.app.open_settings(on_close=self._settings_changed)
            elif choice == "help":
                self.action_help()
            elif choice == "title":
                self.app.goto_title()
            elif choice == "quit":
                self.app.exit()
        self.app.push_screen(MenuDialog("Menu", options), done)

    def _settings_changed(self) -> None:
        self.engine.dm = self.app.make_dm()
        self._sync_controls()

    def _game_over_choice(self, choice) -> None:
        if choice == "new":
            self.app.new_adventure()
        elif choice == "load":
            self.app.open_load_dialog()
        else:
            self.app.goto_title()
