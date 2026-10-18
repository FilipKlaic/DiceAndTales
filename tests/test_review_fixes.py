"""Regression tests for bugs found in the independent review."""

from conftest import make_character
from dice_and_tales.core.character import Item
from dice_and_tales.core.events import GoldEvent
from dice_and_tales.game.dm import DungeonMaster
from dice_and_tales.game.engine import Engine
from sse import ScriptedAPI, message_stream


def dm_engine(story, responses, scene):
    api = ScriptedAPI(responses)
    engine, _ = Engine.new_game(story, make_character(), seed=5, dm=DungeonMaster(story, client=api.client()))
    engine.enter_scene(scene)
    return api, engine


def test_dm_move_applies_the_options_effects(story):
    """Moving via the DM must cost the torch, exactly like choosing the option."""
    api, engine = dm_engine(story, [
        message_stream([{"tool": "move_to", "input": {"scene_id": "crypt_burned"}}]),
        message_stream([{"text": "The webs go up in flames."}]),
    ], "crypt_hall")
    assert engine.character.has_item("torch")
    engine.freeform("I hurl my torch into the webs")
    assert not engine.character.has_item("torch")
    assert engine.state.combat is not None or engine.state.ending  # crypt_burned starts a fight


def test_dm_move_sets_quest_flags(story):
    api, engine = dm_engine(story, [
        message_stream([{"tool": "move_to", "input": {"scene_id": "north_road"}}]),
        message_stream([{"text": "You pocket the map and head north."}]),
    ], "tomb_info")
    engine.freeform("I take the job and go")
    assert "took_bounty" in engine.state.flags


def test_dm_cannot_forge_story_items(story):
    _, engine = dm_engine(story, [], "town_road")
    for name in ("Tomb Map", "Hilda's Map", "Iron Medallion"):
        refused = engine.dm_tool("give_item", {"name": name, "description": "a fake"})
        assert refused.error and "story item" in refused.result["error"]
    improvised = engine.dm_tool("give_item", {"name": "Old Map", "description": "a scrawl"})
    assert not improvised.error
    road = next(c for c in engine.choices() if "north road" in c.label)
    assert not road.enabled  # improvised items never satisfy a story gate
    assert engine.character.find_item("Old Map").id == "dm:old_map"


def test_dm_rewards_have_a_per_scene_budget(story):
    _, engine = dm_engine(story, [], "barkeep_chat")
    assert not engine.dm_tool("award_xp", {"amount": 50, "reason": "a"}).error
    assert engine.dm_tool("award_xp", {"amount": 50, "reason": "again"}).error
    assert engine.character.xp == 50
    engine.dm_tool("change_gold", {"amount": 25, "reason": "a"})
    engine.dm_tool("change_gold", {"amount": 25, "reason": "b"})
    assert engine.character.gold == 10 + 30
    assert not engine.dm_tool("give_item", {"name": "Potion of Healing", "description": ""}).error
    assert engine.dm_tool("give_item", {"name": "Potion of Healing", "description": ""}).error


def test_json_retry_retracts_streamed_text(story, monkeypatch):
    """If the SDK can't parse a streamed tool input, the retry must not duplicate narration."""
    _, engine = dm_engine(story, [], "barkeep_chat")
    attempts = []

    def fake_stream(self, system, messages, narration, on_text):
        attempts.append(1)
        for chunk in ("You reach ", "for the latch"):
            narration.append(chunk)
            on_text(chunk)
        if len(attempts) == 1:
            raise ValueError("Unable to parse tool parameter JSON")
        narration.append(" and it clicks open.")
        on_text(" and it clicks open.")

        class Final:
            stop_reason = "end_turn"
            content = []
        return Final()

    monkeypatch.setattr(DungeonMaster, "_stream_turn", fake_stream)
    shown = []
    engine.freeform(
        "open the latch",
        on_text=shown.append,
        on_retract=lambda n: shown.__setitem__(slice(None), list("".join(shown)[:-n] if n else "".join(shown))),
    )
    assert engine.state.dm_history[-1]["narration"] == "You reach for the latch and it clicks open."
    assert "".join(shown) == "You reach for the latch and it clicks open."


def test_option_rewards_are_paid_once(story):
    engine, _ = Engine.new_game(story, make_character(), seed=1)
    engine.enter_scene("figure_demand")
    gold = engine.character.gold
    engine.choose("0")  # accept the purse
    engine.state.flags.discard("seren_deal")  # e.g. the DM cleared it
    engine.enter_scene("figure_demand")
    engine.choose("0")
    assert engine.character.gold == gold + 50
    texts = [j.text for j in engine.state.journal]
    assert len(texts) == len(set(texts))


def test_no_gold_event_when_nothing_changes(story):
    engine, _ = Engine.new_game(story, make_character(), seed=1)
    engine.character.gold = 0
    events = engine.enter_scene("brawl_won")
    assert not any(isinstance(e, GoldEvent) for e in events)


def test_items_unusable_after_the_game_ends(story):
    engine, _ = Engine.new_game(story, make_character(), seed=1)
    engine.character.take_damage(5)
    engine.enter_scene("rest_ending")
    hp = engine.character.current_hp
    assert engine.use_item("healing_potion") == []
    assert engine.character.current_hp == hp


def test_endings_pay_only_what_was_promised(story):
    engine, _ = Engine.new_game(story, make_character(), seed=1)
    engine.enter_scene("aldric_named")
    labels = [c.label for c in engine.choices()]
    assert labels.count("Break the medallion and set him free") == 1
    engine.choose(str(labels.index("Break the medallion and set him free")))
    assert engine.state.scene_id == "rest_eternal_unpaid"  # never took the bounty


async def test_inventory_with_duplicate_items_opens():
    from textual.widgets import OptionList

    from dice_and_tales.config import Settings
    from dice_and_tales.ui.app import DiceAndTalesApp
    from dice_and_tales.ui.modals import InventoryDialog

    app = DiceAndTalesApp(settings=Settings(text_speed="instant", animations=False))
    async with app.run_test(size=(120, 40)) as pilot:
        character = make_character()
        character.add_item(Item.from_catalog("healing_potion"))
        await app.push_screen(InventoryDialog(character, in_combat=False))
        await pilot.pause()
        assert app.screen.query_one(OptionList).option_count == len(character.inventory)
