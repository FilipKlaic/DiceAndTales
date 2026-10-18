from conftest import make_character
from dice_and_tales.core import dice
from dice_and_tales.core.combat import BESTIARY, Combat, make_enemies
from dice_and_tales.core.events import CombatEndEvent, DamageEvent, HealEvent
from dice_and_tales.core.rules import CharacterClass, Race


def fight(character, enemies, policy=None):
    combat = Combat(character, enemies)
    combat.start()
    for _ in range(200):
        if combat.over:
            break
        enabled = [a for a in combat.actions() if a.enabled]
        action = policy(combat) if policy else next(a.id for a in enabled if a.id.startswith("attack"))
        combat.act(action)
    return combat


def test_duplicate_enemies_get_letters():
    names = [e.name for e in make_enemies(["skeleton", "skeleton", "zombie"])]
    assert names == ["Skeleton A", "Skeleton B", "Zombie"]


def test_fight_always_ends():
    for seed in range(200):
        dice.seed(seed)
        combat = fight(make_character(), ["skeleton", "skeleton"])
        assert combat.result in ("victory", "defeat")


def test_victory_xp_counts_defeated_enemies():
    dice.seed(3)
    combat = fight(make_character(scores=dict(strength=18, dexterity=14, constitution=16, intelligence=8,
                                              wisdom=10, charisma=8)), ["giant_rat"])
    assert combat.result == "victory"
    assert combat.xp_reward == BESTIARY["giant_rat"].xp


def test_defeat_when_hp_hits_zero():
    c = make_character()
    c.current_hp = 1
    dice.seed(0)
    combat = fight(c, ["zombie", "zombie", "zombie"])
    assert combat.result == "defeat" and c.current_hp == 0


def test_rogue_always_escapes():
    combat = Combat(make_character(CharacterClass.ROGUE), ["zombie"])
    combat.start()
    if not combat.over:
        events = combat.act("flee")
        assert combat.result == "fled"
        assert any(isinstance(e, CombatEndEvent) for e in events)


def test_second_wind_is_a_bonus_action():
    c = make_character(CharacterClass.FIGHTER)
    combat = Combat(c, ["zombie"])
    combat.start()
    c.take_damage(8)
    round_before = combat.round
    events = combat.act("second_wind")
    assert any(isinstance(e, HealEvent) for e in events)
    assert combat.round == round_before  # enemies did not get a turn
    assert c.resources["second_wind"] == 0
    assert not next(a for a in combat.actions() if a.id == "second_wind").enabled


def test_magic_missile_spends_a_slot_and_never_misses():
    c = make_character(CharacterClass.WIZARD)
    combat = Combat(c, ["zombie"])
    combat.start()
    events = combat.act("magic_missile:0")
    assert c.resources["spell_slots"] == 1
    assert any(isinstance(e, DamageEvent) and e.target == "Zombie" for e in events)


def test_skeletons_are_vulnerable_to_bludgeoning():
    c = make_character(CharacterClass.CLERIC)
    combat = Combat(c, ["skeleton"])
    skeleton = combat.enemies[0]
    events = combat._damage_enemy(skeleton, 3, "bludgeoning")
    assert skeleton.hp == 8 - 6
    assert "vulnerability" in events[0].source


def test_turn_undead_ignores_the_boss():
    c = make_character(CharacterClass.CLERIC, scores=dict(strength=12, dexterity=10, constitution=12, intelligence=8,
                                                          wisdom=18, charisma=10))
    combat = Combat(c, ["priest_shade"])
    combat.start()
    if not combat.over:
        combat.act("turn_undead")
        assert not combat.enemies[0].fled


def test_wizard_shield_saves_from_a_lethal_hit(monkeypatch):
    c = make_character(CharacterClass.WIZARD, Race.HUMAN)
    c.current_hp = 1
    combat = Combat(c, ["skeleton"])
    # Attack total of AC exactly: Shield's +5 turns it into a miss.
    assert combat._try_shield(c.armor_class, incoming=3, critical=False)
    assert c.resources["spell_slots"] == 1


def test_disabled_action_is_refused():
    combat = Combat(make_character(CharacterClass.CLERIC), ["giant_rat"])
    combat.start()
    events = combat.act("turn_undead")  # no undead here
    assert "can't" in events[0].text


def test_combat_round_trip():
    c = make_character()
    combat = Combat(c, ["skeleton", "zombie"], victory_scene="a", flee_scene="b")
    combat.enemies[0].hp = 3
    clone = Combat.from_dict(c, combat.to_dict())
    assert clone.enemies[0].hp == 3 and clone.victory_scene == "a" and clone.flee_scene == "b"
