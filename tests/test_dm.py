"""The AI Dungeon Master, exercised through the real Anthropic SDK against a scripted mock API."""

from conftest import make_character
from dice_and_tales.core.events import DamageEvent, GameOverEvent, GoldEvent, Notice, RollEvent, SceneEvent
from dice_and_tales.game.dm import TOOLS, DungeonMaster, validate_input
from dice_and_tales.game.engine import ENDED, Engine
from sse import ScriptedAPI, message_stream


def setup(story, responses, scene="barkeep_chat"):
    api = ScriptedAPI(responses)
    dm = DungeonMaster(story, client=api.client())
    engine, _ = Engine.new_game(story, make_character(), seed=3, dm=dm)
    engine.enter_scene(scene)
    return api, engine


def text(t):
    return message_stream([{"text": t}])


def tool(name, **args):
    return message_stream([{"tool": name, "input": args}])


def test_plain_narration_streams_and_is_remembered(story):
    api, engine = setup(story, [text("Hilda laughs and pours you another.")])
    chunks = []
    events = engine.freeform("tell Hilda a joke", on_text=chunks.append)
    assert events == []
    assert "".join(chunks).strip() == "Hilda laughs and pours you another."
    turn = engine.state.dm_history[-1]
    assert turn["action"] == "tell Hilda a joke" and turn["where"] == "At the Bar"


def test_request_shape(story):
    api, engine = setup(story, [text("ok")])
    engine.freeform("look around")
    req = api.requests[0]
    body = req["body"]
    assert body["model"] == "claude-opus-5-5"
    assert body["thinking"] == {"type": "adaptive"}
    assert body["output_config"] == {"effort": "low"}
    assert body["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in req["headers"]["anthropic-beta"]
    assert all(t["eager_input_streaming"] for t in body["tools"])
    assert body["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "Hilda" in body["system"][0]["text"]
    assert '"exits"' in body["system"][1]["text"]
    assert body["messages"][-1]["content"].endswith("Player action: look around")


def test_check_is_rolled_by_the_engine_and_returned_to_claude(story):
    api, engine = setup(story, [
        tool("request_check", ability="dexterity", skill="sleight_of_hand", dc=14, reason="the purse"),
        text("Your fingers close on nothing."),
    ])
    events = engine.freeform("steal Hilda's purse")
    assert isinstance(events[0], RollEvent) and events[0].target == 14
    tool_result = api.requests[1]["body"]["messages"][-1]["content"][0]
    assert tool_result["type"] == "tool_result" and '"dc": 14' in tool_result["content"]
    assert not tool_result["is_error"]


def test_invalid_tool_input_is_rejected_not_executed(story):
    api, engine = setup(story, [
        tool("change_gold", amount="lots", reason="greed"),
        text("Nothing happens."),
    ])
    gold = engine.character.gold
    events = engine.freeform("conjure gold")
    assert engine.character.gold == gold and events == []
    result = api.requests[1]["body"]["messages"][-1]["content"][0]
    assert result["is_error"] and "INVALID_INPUT" in result["content"]


def test_move_to_only_allows_listed_exits_and_applies_after_narration(story):
    api, engine = setup(story, [
        message_stream([{"tool": "move_to", "input": {"scene_id": "tomb_deep"}}]),
        message_stream([{"tool": "move_to", "input": {"scene_id": "tavern_entrance"}}]),
        text("You drift back into the crowd."),
    ])
    events = engine.freeform("walk away from the bar")
    first = api.requests[1]["body"]["messages"][-1]["content"][0]
    assert first["is_error"] and "not reachable" in first["content"]
    assert isinstance(events[-1], SceneEvent) and events[-1].scene_id == "tavern_entrance"
    assert engine.state.scene_id == "tavern_entrance"


def test_per_turn_limits(story):
    api, engine = setup(story, [
        message_stream([{"tool": "change_gold", "input": {"amount": 10, "reason": "a"}},
                        {"tool": "change_gold", "input": {"amount": 10, "reason": "b"}}]),
        text("done"),
    ])
    gold = engine.character.gold
    events = engine.freeform("find coins")
    assert engine.character.gold == gold + 10
    assert [type(e) for e in events] == [GoldEvent]
    results = api.requests[1]["body"]["messages"][-1]["content"]
    assert [r["is_error"] for r in results] == [False, True]


def test_damage_can_kill_and_ends_game(story):
    api, engine = setup(story, [
        tool("deal_damage", amount=10, damage_type="fire", reason="you leapt into the hearth"),
        text("The flames take you."),
    ])
    engine.character.current_hp = 3
    events = engine.freeform("jump into the fire")
    assert any(isinstance(e, DamageEvent) for e in events)
    assert any(isinstance(e, GameOverEvent) for e in events)
    assert engine.mode == ENDED


def test_start_combat_is_queued_then_started(story):
    api, engine = setup(story, [tool("start_combat", enemies=["tavern_brawler"]), text("He swings first.")])
    engine.freeform("insult the big man at the bar")
    assert engine.state.combat is not None or engine.state.ending


def test_boss_cannot_be_summoned(story):
    assert validate_input("start_combat", {"enemies": ["priest_shade"]}) is not None


def test_refusal_becomes_a_notice(story):
    api, engine = setup(story, [message_stream([{"text": ""}], stop_reason="refusal")])
    events = engine.freeform("something")
    assert isinstance(events[0], Notice) and "won't narrate" in events[0].text


def test_api_errors_become_notices(story):
    api, engine = setup(story, [500])
    events = engine.freeform("anything")
    assert isinstance(events[0], Notice) and "500" in events[0].text
    assert engine.dm.available


def test_bad_credentials_disable_the_dm(story):
    api, engine = setup(story, [401])
    engine.freeform("anything")
    assert not engine.dm.available
    assert not engine.can_freeform


def test_history_is_replayed_and_trimmed(story):
    api, engine = setup(story, [text(f"reply {i}") for i in range(10)])
    for i in range(10):
        engine.freeform(f"action {i}")
    assert len(engine.state.dm_history) == 8
    messages = api.requests[-1]["body"]["messages"]
    assert messages[0]["content"].endswith("Player action: action 1")  # actions 1-8 kept before the 10th call
    assert len(messages) == 17  # 8 past exchanges + current action


def test_no_credentials_means_unavailable(story):
    dm = DungeonMaster(story)
    assert not dm.available and "ANTHROPIC_API_KEY" in dm.disabled_reason


def test_tool_schemas_are_consistent():
    for t in TOOLS:
        schema = t["input_schema"]
        assert set(schema["required"]) <= set(schema["properties"])
        assert schema["additionalProperties"] is False
