"""Headless UI tests using Textual's pilot."""

from textual.widgets import Input, OptionList

from dice_and_tales.config import Settings
from dice_and_tales.game import saves
from dice_and_tales.game.engine import EXPLORE
from dice_and_tales.ui.app import DiceAndTalesApp
from dice_and_tales.ui.game_screen import GameScreen
from dice_and_tales.ui.menus import CreationScreen, TitleScreen
from dice_and_tales.ui.modals import GameOverDialog, HelpDialog, SheetDialog
from sse import ScriptedAPI, message_stream

FAST = Settings(text_speed="instant", animations=False, dm_enabled=True)


async def settle(pilot, screen, timeout=5.0):
    waited = 0.0
    while (screen.busy or screen.dm_thinking) and waited < timeout:
        await pilot.pause(0.05)
        waited += 0.05
    await pilot.pause(0.05)


async def create_hero(pilot, app, name="Brannoc"):
    await pilot.pause()
    assert isinstance(app.screen, TitleScreen)
    await pilot.press("enter")  # "New adventure" is first when there's no autosave
    await pilot.pause()
    assert isinstance(app.screen, CreationScreen)
    await pilot.press(*name, "enter", "enter", "enter", "enter")  # name, Fighter, Human, Begin
    await pilot.pause(0.2)
    assert isinstance(app.screen, GameScreen)
    await settle(pilot, app.screen)
    return app.screen


async def test_new_game_flow_and_dialogs():
    app = DiceAndTalesApp(settings=FAST)
    async with app.run_test(size=(140, 45)) as pilot:
        screen = await create_hero(pilot, app)
        assert screen.engine.character.name == "Brannoc"
        assert screen.engine.state.scene_id == "tavern_entrance"
        await pilot.press("1")
        await settle(pilot, screen)
        assert screen.engine.state.scene_id == "barkeep_chat"
        assert saves.info("auto") is not None

        await pilot.press("c")
        await pilot.pause()
        assert isinstance(app.screen, SheetDialog)
        await pilot.press("escape", "question_mark")
        await pilot.pause()
        assert isinstance(app.screen, HelpDialog)
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen is screen


async def test_free_text_is_disabled_without_a_dm():
    app = DiceAndTalesApp(settings=FAST)
    async with app.run_test(size=(140, 45)) as pilot:
        screen = await create_hero(pilot, app)
        action = screen.query_one("#action", Input)
        assert action.disabled and "ANTHROPIC_API_KEY" in action.placeholder


async def test_free_text_goes_to_the_dungeon_master():
    api = ScriptedAPI([
        message_stream([{"tool": "request_check", "input": {"ability": "charisma", "skill": "persuasion", "dc": 12,
                                                             "reason": "charming Hilda"}}]),
        message_stream([{"tool": "award_xp", "input": {"amount": 20, "reason": "charm"}},
                        {"tool": "add_journal", "input": {"entry": "Made Hilda laugh."}}]),
        message_stream([{"text": "Hilda snorts into her sleeve, then laughs outright."}]),
    ])
    app = DiceAndTalesApp(settings=FAST, dm_client=api.client())
    async with app.run_test(size=(140, 45)) as pilot:
        screen = await create_hero(pilot, app)
        action = screen.query_one("#action", Input)
        assert not action.disabled
        await pilot.press("slash")
        assert app.focused is action
        await pilot.press(*"tell Hilda a terrible joke", "enter")
        await settle(pilot, screen)
        assert len(api.requests) == 3
        assert screen.engine.character.xp == 20
        assert screen.engine.state.journal[-1].text == "Made Hilda laugh."
        log_text = " ".join(str(w.render()) for w in screen.query(".dm"))
        assert "Hilda snorts" in log_text
        assert screen.query(".dice-roll")
        assert not screen.busy and isinstance(app.focused, OptionList)
        # The narration of the outcome must come after the roll that decided it.
        children = list(screen.query_one("#log").children)
        roll_at = next(i for i, w in enumerate(children) if w.has_class("dice-roll"))
        narration_at = next(i for i, w in enumerate(children) if "Hilda snorts" in str(w.render()))
        assert narration_at > roll_at


async def test_continue_from_autosave_and_game_over():
    app = DiceAndTalesApp(settings=FAST)
    async with app.run_test(size=(140, 45)) as pilot:
        screen = await create_hero(pilot, app)
        engine = screen.engine
        await pilot.press("escape")
        await pilot.pause()
        await pilot.press("down", "down", "down", "down", "down", "enter")  # Quit to title
        await pilot.pause()
        assert isinstance(app.screen, TitleScreen)
        menu = app.screen.query_one("#title-menu", OptionList)
        assert menu.get_option_at_index(0).id == "continue"
        await pilot.press("enter")
        await pilot.pause(0.2)
        resumed = app.screen
        assert isinstance(resumed, GameScreen) and resumed.engine is not engine
        await settle(pilot, resumed)
        assert resumed.engine.mode == EXPLORE

        resumed.enqueue(resumed.engine.enter_scene("rest_ending"))
        await settle(pilot, resumed)
        await pilot.pause(0.2)
        assert isinstance(app.screen, GameOverDialog)
        # The ending never overwrites the last checkpoint, so it can still be continued.
        assert app.autosave_resumable()
        assert saves.load("auto").ending is None
