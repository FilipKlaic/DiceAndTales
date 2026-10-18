import json
import random

import pytest

from conftest import make_character
from dice_and_tales.core import dice
from dice_and_tales.core.events import CombatStartEvent, DamageEvent, GameOverEvent, ItemEvent, RollEvent
from dice_and_tales.core.rules import CharacterClass
from dice_and_tales.game import saves
from dice_and_tales.game.engine import COMBAT, ENDED, EXPLORE, Engine
from dice_and_tales.game.state import GameState
from dice_and_tales.game.story import StoryError, parse_story, validate


def pick(engine, text):
    """Choose the option whose label contains `text`."""
    for choice in engine.choices():
        if text.lower() in choice.label.lower():
            return engine.choose(choice.key)
    raise AssertionError(f"no option matching {text!r}: {[c.label for c in engine.choices()]}")


# --- Story data -----------------------------------------------------------

def test_bundled_story_is_valid(story):
    assert validate(story) == []
    assert story.start == "tavern_entrance"
    assert sum(1 for s in story.scenes.values() if s.is_ending) >= 6


def _mini(**scene_overrides):
    scenes = {
        "a": {"text": "A", "options": [{"text": "go", "goto": "b"}]},
        "b": {"text": "B", "ending": "Done"},
    }
    scenes["a"].update(scene_overrides)
    return {"story": {"title": "t", "start": "a"}, "flags": {"known": "x"}, "scenes": scenes}


def test_validator_catches_missing_scene():
    data = _mini(options=[{"text": "go", "goto": "nowhere"}])
    with pytest.raises(StoryError, match="missing scene 'nowhere'"):
        parse_story(data)


def test_validator_catches_undeclared_flag():
    data = _mini(options=[{"text": "go", "goto": "b", "requires_flags": ["mystery"]}])
    with pytest.raises(StoryError, match="not declared"):
        parse_story(data)


def test_validator_catches_skill_ability_mismatch():
    check = {"ability": "strength", "skill": "stealth", "dc": 10, "success": "b", "failure": "b"}
    with pytest.raises(StoryError, match="uses dexterity"):
        parse_story(_mini(options=[{"text": "sneak", "check": check}]))


def test_validator_catches_unknown_enemy_and_unreachable_scene():
    data = _mini(options=[{"text": "fight", "encounter": {"enemies": ["dragon"], "victory": "b"}}])
    data["scenes"]["island"] = {"text": "lonely", "ending": "Alone"}
    with pytest.raises(StoryError) as exc:
        parse_story(data)
    assert "unknown enemy 'dragon'" in str(exc.value) and "unreachable" in str(exc.value)


# --- Engine ---------------------------------------------------------------

def test_new_game_starts_in_tavern(engine):
    assert engine.state.scene_id == "tavern_entrance"
    assert engine.mode == EXPLORE
    assert [c.label for c in engine.choices()][0] == "Approach the bar"


def test_quest_path_gives_map_and_flag(engine):
    pick(engine, "approach the bar")
    events = pick(engine, "ask about the tomb")
    assert any(isinstance(e, ItemEvent) and e.name == "Hilda's Map" for e in events)
    pick(engine, "take the quest")
    assert "took_bounty" in engine.state.flags
    assert engine.state.scene_id == "north_road"
    assert engine.state.journal[-1].text.startswith("Took the mayor's bounty")


def test_item_gated_option_is_locked_not_hidden(engine):
    pick(engine, "step back outside")
    road = next(c for c in engine.choices() if "north road" in c.label)
    assert not road.enabled and "Hilda's Map" in road.reason
    assert "isn't" in engine.choose(road.key)[0].text or "can't" in engine.choose(road.key)[0].text


def test_flag_gated_options_hidden_and_text_variant(engine):
    engine.state.flags.add("hilda_angered")
    pick(engine, "approach the bar")
    labels = [c.label for c in engine.choices()]
    assert "Ask about the tomb" not in labels
    assert any("Apologise" in l for l in labels)
    assert "rob me again" in engine.scene_text()


def test_scene_check_mode(engine):
    pick(engine, "approach the hooded figure")
    assert engine.mode == "check"
    assert engine.choices()[0].tag.startswith("DEX (Stealth) DC 10")
    events = engine.choose("roll")
    assert isinstance(events[0], RollEvent)
    assert engine.state.scene_id in ("figure_success", "figure_fail")


def test_check_failure_damage(engine, monkeypatch):
    engine.enter_scene("tomb_antechamber")
    monkeypatch.setattr(dice, "roll", lambda sides: 1)
    events = pick(engine, "search the burial alcoves")
    assert any(isinstance(e, DamageEvent) for e in events)
    assert engine.state.scene_id == "alcove_trap"


def test_on_enter_rewards_only_once(engine):
    gold = engine.character.gold
    engine.enter_scene("alcove_loot")
    engine.enter_scene("tomb_antechamber")
    engine.enter_scene("alcove_loot")
    assert engine.character.gold == gold + 15


def test_encounter_and_victory_scene(engine):
    engine.enter_scene("tomb_entrance")
    events = pick(engine, "fight the skeleton guards")
    assert any(isinstance(e, CombatStartEvent) for e in events)
    assert engine.mode == COMBAT
    assert not engine.can_save
    for _ in range(100):
        if engine.mode != COMBAT:
            break
        engine.choose(next(c.key for c in engine.choices() if c.enabled))
    assert engine.mode in (EXPLORE, ENDED)
    if engine.mode == EXPLORE:
        assert "skeletons_cleared" in engine.state.flags or engine.state.scene_id == "tomb_retreat"


def test_death_ends_the_game(engine):
    engine.character.current_hp = 1
    engine.enter_scene("tomb_antechamber")
    dice.seed(0)
    engine.state.flags.add("alcoves_searched")
    outcome = engine._dm_deal_damage(amount=5, damage_type="fire", reason="test")
    assert outcome.result["character_died"]
    assert engine.mode == ENDED and engine.state.ending == "Fallen"
    assert any(isinstance(e, GameOverEvent) for e in outcome.events)


def test_ending_scene(engine):
    events = engine.enter_scene("rest_ending")
    assert engine.mode == ENDED and engine.choices() == []
    assert isinstance(events[-1], GameOverEvent) and events[-1].title == "A Real Bed"


def test_long_rest_only_in_safe_places_and_costs_gold(engine):
    c = engine.character
    c.take_damage(5)
    engine.enter_scene("north_road")
    assert "isn't safe" in engine.long_rest()[0].text
    engine.enter_scene("tavern_entrance")
    gold = c.gold
    engine.long_rest()
    assert c.current_hp == c.max_hp and c.gold == gold - 2


def test_use_potion_outside_combat(engine):
    engine.character.take_damage(6)
    hp = engine.character.current_hp
    engine.use_item("healing_potion")
    assert engine.character.current_hp > hp
    assert not engine.character.has_item("healing_potion")


def test_class_gated_and_random_playthroughs_never_get_stuck(story):
    endings = set()
    for seed in range(300):
        rng = random.Random(seed)
        cls = rng.choice(list(CharacterClass))
        engine, _ = Engine.new_game(story, make_character(cls), seed=seed)
        for _ in range(300):
            if engine.mode == ENDED:
                break
            enabled = [c for c in engine.choices() if c.enabled]
            assert enabled, f"stuck in {engine.state.scene_id}"
            engine.choose(rng.choice(enabled).key)
        endings.add(engine.state.ending)
    assert len(endings) >= 3


def test_save_and_load_round_trip(engine):
    pick(engine, "approach the bar")
    pick(engine, "ask about the tomb")
    engine.state.dm_history.append({"where": "x", "action": "y", "narration": "z", "mechanics": []})
    saves.save(engine.state, "1", where=engine.scene.title)
    loaded = saves.load("1")
    assert loaded.to_dict() == engine.state.to_dict()
    info = saves.info("1")
    assert info.name == "Tester" and "Fighter" in info.title
    assert saves.info("2") is None


def test_save_mid_combat_round_trip(engine):
    engine.enter_scene("tomb_entrance")
    pick(engine, "fight the skeleton guards")
    data = json.loads(json.dumps(engine.state.to_dict()))
    restored = GameState.from_dict(data)
    assert restored.combat is not None and restored.combat.character is restored.character


def test_rejects_unknown_save_version(engine):
    data = engine.state.to_dict()
    data["version"] = 99
    with pytest.raises(ValueError):
        GameState.from_dict(data)
