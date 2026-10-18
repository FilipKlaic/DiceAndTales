"""The Textual application: screen flow, settings, saves and the Dungeon Master."""

from textual.app import App

from dice_and_tales import config
from dice_and_tales.config import Settings
from dice_and_tales.game import saves
from dice_and_tales.game.dm import DungeonMaster
from dice_and_tales.game.engine import Engine
from dice_and_tales.game.story import Story, load_story
from dice_and_tales.ui.game_screen import GameScreen
from dice_and_tales.ui.menus import CreationScreen, TitleScreen
from dice_and_tales.ui.modals import MenuDialog, SettingsDialog, save_slot_options


class DiceAndTalesApp(App):
    CSS_PATH = "app.tcss"
    TITLE = "Dice & Tales"

    def __init__(self, story: Story | None = None, dm_client=None, settings: Settings | None = None):
        super().__init__()
        self.story = story or load_story()
        self.settings = settings or Settings.load()
        self._dm_client = dm_client  # injected in tests

    def on_mount(self) -> None:
        self.push_screen(TitleScreen())

    # --- Dungeon Master -------------------------------------------------

    def make_dm(self) -> DungeonMaster | None:
        if not self.settings.dm_enabled:
            return None
        return DungeonMaster(self.story, client=self._dm_client)

    def dm_status(self) -> str:
        if not self.settings.dm_enabled:
            return "AI Dungeon Master: switched off in Settings."
        dm = self.make_dm()
        if dm and dm.available:
            return f"AI Dungeon Master: ready ({dm.model}, effort {dm.effort}). Type any action in game with /"
        return f"AI Dungeon Master: offline. {dm.disabled_reason if dm else ''}"

    def dm_offline_hint(self) -> str:
        if not self.settings.dm_enabled:
            return "AI Dungeon Master is switched off (Esc > Settings)."
        return "AI Dungeon Master offline: set ANTHROPIC_API_KEY to type your own actions."

    # --- Screen flow ----------------------------------------------------

    def _reset_to_title(self) -> None:
        while len(self.screen_stack) > 2:  # default screen + title
            self.pop_screen()

    def goto_title(self) -> None:
        self._reset_to_title()
        title = self.screen
        if isinstance(title, TitleScreen):
            title.refresh_menu()

    def new_adventure(self) -> None:
        self._reset_to_title()
        self.push_screen(CreationScreen())

    def start_new_game(self, character) -> None:
        engine, events = Engine.new_game(self.story, character, dm=self.make_dm())
        self._reset_to_title()
        self.push_screen(GameScreen(engine, events))

    def load_game(self, slot: str) -> None:
        try:
            state = saves.load(slot)
            if state.scene_id not in self.story.scenes:
                raise ValueError(f"unknown scene {state.scene_id!r}")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.notify(f"Couldn't load that save: {exc}", severity="error")
            return
        engine = Engine(self.story, state, dm=self.make_dm())
        self._reset_to_title()
        screen = GameScreen(engine, None)
        if state.ending:
            screen.game_over_pending = True  # a finished run reopens on its ending, never a dead end
        self.push_screen(screen)

    def autosave_resumable(self) -> bool:
        try:
            return saves.load("auto").ending is None
        except (OSError, ValueError, KeyError, TypeError):
            return False

    def open_load_dialog(self) -> None:
        options = save_slot_options(include_auto=True, for_saving=False)
        if not any(enabled for _, _, enabled in options):
            self.notify("No saved games yet.")
            return

        def done(slot):
            if slot:
                self.load_game(slot)
        self.push_screen(MenuDialog("Load game", options), done)

    def open_settings(self, on_close=None) -> None:
        status = self.dm_status() + f"\nSaves and settings live in {config.home_dir()}"

        def done(_):
            if on_close:
                on_close()
        self.push_screen(SettingsDialog(self.settings, status), done)
