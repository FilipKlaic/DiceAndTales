import pytest

from conftest import make_character
from dice_and_tales.core import dice
from dice_and_tales.core.character import Character, arrange_for_class, create_character
from dice_and_tales.core.checks import resolve_check
from dice_and_tales.core.rules import CharacterClass, Race, modifier, skill_label


class TestDice:
    def test_roll_in_range(self):
        assert all(1 <= dice.roll(6) <= 6 for _ in range(500))

    def test_roll_stat_drops_lowest(self):
        for _ in range(200):
            score, rolls = dice.roll_stat()
            assert len(rolls) == 4
            assert score == sum(sorted(rolls)[1:])
            assert 3 <= score <= 18

    def test_seed_is_reproducible(self):
        dice.seed(42)
        first = [dice.roll(20) for _ in range(10)]
        dice.seed(42)
        assert [dice.roll(20) for _ in range(10)] == first

    def test_advantage_keeps_higher(self):
        for _ in range(200):
            r = dice.roll_d20(advantage=True)
            assert r.mode == "advantage" and len(r.rolls) == 2 and r.kept == max(r.rolls)

    def test_disadvantage_keeps_lower(self):
        for _ in range(200):
            r = dice.roll_d20(disadvantage=True)
            assert r.kept == min(r.rolls)

    def test_advantage_and_disadvantage_cancel(self):
        r = dice.roll_d20(advantage=True, disadvantage=True)
        assert r.mode == "normal" and len(r.rolls) == 1

    def test_lucky_never_keeps_a_natural_one_unless_rerolled_into_it(self):
        rerolls = [dice.roll_d20(lucky=True) for _ in range(2000)]
        assert any(r.lucky_reroll for r in rerolls)
        ones = [r for r in rerolls if r.kept == 1]
        assert all(r.lucky_reroll for r in ones)

    @pytest.mark.parametrize("expr,count,sides,bonus", [
        ("1d8", 1, 8, 0), ("2d6+3", 2, 6, 3), ("d20", 1, 20, 0), ("3d4 - 1", 3, 4, -1),
    ])
    def test_parse(self, expr, count, sides, bonus):
        assert dice.parse(expr) == dice.DiceExpr(count, sides, bonus)

    @pytest.mark.parametrize("bad", ["", "d7", "0d6", "banana", "2d6+", "99d6"])
    def test_parse_rejects_garbage(self, bad):
        with pytest.raises(ValueError):
            dice.parse(bad)

    def test_critical_doubles_dice_not_bonus(self):
        result = dice.roll_expr("1d8+3", critical=True)
        assert len(result.rolls) == 2 and result.bonus == 3


class TestCharacter:
    def test_modifier_table(self):
        assert [modifier(s) for s in (1, 8, 9, 10, 11, 12, 18, 20)] == [-5, -1, -1, 0, 0, 1, 4, 5]

    def test_racial_bonuses_applied(self):
        c = make_character(race=Race.DWARF)
        assert c.scores["constitution"] == 16 and c.scores["strength"] == 15

    def test_human_gets_plus_one_everywhere(self):
        c = make_character(race=Race.HUMAN)
        assert c.scores["charisma"] == 11

    def test_starting_hp_and_kit(self):
        c = make_character(CharacterClass.WIZARD)  # d6 + CON(15 -> +2) + 6
        assert c.max_hp == c.current_hp == 14
        assert c.has_item("spellbook") and c.has_item("healing_potion")
        assert c.resources["spell_slots"] == 2

    def test_armor_class(self):
        assert make_character(CharacterClass.FIGHTER).armor_class == 16  # heavy armour ignores DEX
        assert make_character(CharacterClass.ROGUE, Race.ELF).armor_class == 12 + 3

    def test_poison_resistance(self):
        dwarf = make_character(race=Race.DWARF)
        assert dwarf.take_damage(7, "poison") == 3
        assert dwarf.take_damage(7, "slashing") == 7

    def test_hp_never_negative_and_heal_capped(self):
        c = make_character()
        c.take_damage(999)
        assert c.current_hp == 0 and not c.is_alive
        assert c.heal(999) == c.max_hp

    def test_level_up(self):
        c = make_character(CharacterClass.WIZARD)
        before = c.max_hp
        assert c.add_xp(300) == [2]
        assert c.level == 2 and c.max_hp > before and c.resources["spell_slots"] == 3

    def test_short_rests_are_limited(self):
        c = make_character()
        c.take_damage(5)
        assert c.short_rest() >= 0
        assert c.short_rest() >= 0
        assert c.short_rest() == -1

    def test_long_rest_restores_everything(self):
        c = make_character(CharacterClass.CLERIC)
        c.take_damage(5)
        c.spend("spell_slots")
        c.spend("channel_divinity")
        c.long_rest()
        assert c.current_hp == c.max_hp and c.resources == c.full_resources()

    def test_round_trip(self):
        c = make_character(CharacterClass.ROGUE, Race.HALFLING)
        c.take_damage(3)
        clone = Character.from_dict(c.to_dict())
        assert clone == c

    def test_arrange_for_class_puts_best_roll_on_key_ability(self):
        scores = dict(strength=6, dexterity=17, constitution=12, intelligence=9, wisdom=14, charisma=11)
        raw = {a: [1, 1, 1, 1] for a in scores}
        arranged, _ = arrange_for_class(scores, raw, CharacterClass.FIGHTER)
        assert arranged["strength"] == 17 and arranged["constitution"] == 14
        assert sorted(arranged.values()) == sorted(scores.values())

    def test_create_with_random_rolls(self):
        c = create_character("  ", CharacterClass.ROGUE, Race.ELF)
        assert c.name == "Nameless" and c.max_hp >= 7


class TestChecks:
    def test_proficiency_added(self):
        rogue = make_character(CharacterClass.ROGUE)
        assert rogue.check_bonus("dexterity", "stealth") == rogue.mod("dexterity") + 2
        assert rogue.check_bonus("intelligence", "arcana") == rogue.mod("intelligence")

    def test_rogue_stealth_has_advantage(self):
        result = resolve_check(make_character(CharacterClass.ROGUE), "dexterity", 10, "stealth")
        assert result.d20.mode == "advantage"

    def test_elf_perception_has_advantage(self):
        result = resolve_check(make_character(race=Race.ELF), "wisdom", 10, "perception")
        assert result.d20.mode == "advantage"

    def test_natural_twenty_always_succeeds(self, monkeypatch):
        monkeypatch.setattr(dice, "roll", lambda sides: 20)
        assert resolve_check(make_character(), "strength", 25).success

    def test_natural_one_always_fails(self, monkeypatch):
        monkeypatch.setattr(dice, "roll", lambda sides: 1)
        assert not resolve_check(make_character(), "strength", 2).success

    def test_skill_label(self):
        assert skill_label("sleight_of_hand") == "Sleight of Hand"
