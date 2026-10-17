"""Turn-based combat: initiative, attacks, class abilities, enemy turns."""

from dataclasses import asdict, dataclass

from dice_and_tales.core import dice
from dice_and_tales.core.character import Character
from dice_and_tales.core.checks import resolve_check
from dice_and_tales.core.events import (
    CombatEndEvent, DamageEvent, Event, HealEvent, ItemEvent, Narration, Notice, RollEvent,
)
from dice_and_tales.core.rules import CharacterClass

FLEE_DC = 12


@dataclass(frozen=True)
class EnemySpec:
    name: str
    hp: int
    ac: int
    attack_bonus: int
    damage: str
    damage_type: str
    xp: int
    dex_mod: int = 0
    wis_save: int = 0
    undead: bool = False
    turn_resistant: bool = False
    extra_damage: str | None = None
    extra_damage_type: str | None = None
    vulnerable: tuple[str, ...] = ()
    attack_verb: str = "attacks"
    description: str = ""


BESTIARY: dict[str, EnemySpec] = {
    "skeleton": EnemySpec(
        "Skeleton", hp=8, ac=12, attack_bonus=3, damage="1d6", damage_type="slashing", xp=50,
        dex_mod=2, wis_save=-1, undead=True, vulnerable=("bludgeoning",),
        attack_verb="slashes with a rusted blade",
        description="Yellowed bones bound by old magic, armed with a notched sword.",
    ),
    "zombie": EnemySpec(
        "Zombie", hp=14, ac=8, attack_bonus=3, damage="1d6", damage_type="bludgeoning", xp=50,
        dex_mod=-2, wis_save=-2, undead=True, attack_verb="slams with a rotting fist",
        description="Slow, stubborn and very hard to put down.",
    ),
    "giant_rat": EnemySpec(
        "Giant Rat", hp=5, ac=11, attack_bonus=3, damage="1d4", damage_type="piercing", xp=25,
        dex_mod=2, wis_save=0, attack_verb="bites",
        description="A dog-sized rat with yellow teeth.",
    ),
    "crypt_spider": EnemySpec(
        "Crypt Spider", hp=9, ac=12, attack_bonus=3, damage="1d4+1", damage_type="piercing", xp=50,
        dex_mod=3, wis_save=0, extra_damage="1d4", extra_damage_type="poison", attack_verb="bites",
        description="Pale, many-eyed, with fangs that drip green venom.",
    ),
    "bandit": EnemySpec(
        "Bandit", hp=10, ac=12, attack_bonus=3, damage="1d6", damage_type="slashing", xp=25,
        dex_mod=1, wis_save=0, attack_verb="swings a scimitar",
        description="A desperate cutthroat in a patched cloak.",
    ),
    "tavern_brawler": EnemySpec(
        "Brawler", hp=9, ac=10, attack_bonus=3, damage="1d4+1", damage_type="bludgeoning", xp=10,
        dex_mod=0, wis_save=0, attack_verb="throws a punch",
        description="Big, drunk and looking for an excuse.",
    ),
    "priest_shade": EnemySpec(
        "Shade of the War-Priest", hp=30, ac=12, attack_bonus=4, damage="1d8+1", damage_type="necrotic",
        xp=200, dex_mod=1, wis_save=3, undead=True, turn_resistant=True, vulnerable=("radiant",),
        attack_verb="lashes out with a hand of cold shadow",
        description="The tomb's master, a hollow-eyed ghost bound to the medallion.",
    ),
}


@dataclass
class Enemy:
    key: str
    name: str
    hp: int
    max_hp: int
    fled: bool = False

    @property
    def spec(self) -> EnemySpec:
        return BESTIARY[self.key]

    @property
    def active(self) -> bool:
        return self.hp > 0 and not self.fled


@dataclass
class CombatAction:
    id: str
    label: str
    enabled: bool = True
    reason: str = ""
    free: bool = False  # bonus actions do not end your turn


def make_enemies(keys: list[str]) -> list[Enemy]:
    totals = {k: keys.count(k) for k in keys}
    seen: dict[str, int] = {}
    enemies = []
    for key in keys:
        spec = BESTIARY[key]
        seen[key] = seen.get(key, 0) + 1
        name = spec.name if totals[key] == 1 else f"{spec.name} {chr(64 + seen[key])}"
        enemies.append(Enemy(key=key, name=name, hp=spec.hp, max_hp=spec.hp))
    return enemies


class Combat:
    def __init__(
        self,
        character: Character,
        enemy_keys: list[str],
        victory_scene: str | None = None,
        flee_scene: str | None = None,
    ):
        self.character = character
        self.enemies = make_enemies(enemy_keys)
        self.victory_scene = victory_scene
        self.flee_scene = flee_scene
        self.round = 0
        self.result: str | None = None  # victory | fled | defeat
        self.sneak_attack_used = False
        self.player_first = True

    # --- Queries --------------------------------------------------------

    @property
    def over(self) -> bool:
        return self.result is not None

    @property
    def active_enemies(self) -> list[Enemy]:
        return [e for e in self.enemies if e.active]

    @property
    def xp_reward(self) -> int:
        return sum(e.spec.xp for e in self.enemies if not e.active)

    def actions(self) -> list[CombatAction]:
        c = self.character
        targets = [(i, e) for i, e in enumerate(self.enemies) if e.active]
        multi = len(targets) > 1
        acts: list[CombatAction] = []

        def per_target(prefix: str, template: str, enabled=True, reason=""):
            for i, e in targets:
                who = e.name if multi else f"the {e.name}"
                acts.append(CombatAction(f"{prefix}:{i}", template.format(t=who), enabled, reason))

        weapon = c.spec.weapon
        per_target("attack", f"Attack {{t}} ({weapon.name})")
        slots = c.resources.get("spell_slots", 0)
        if c.character_class is CharacterClass.WIZARD:
            per_target("fire_bolt", "Fire Bolt at {t}")
            per_target("magic_missile", f"Magic Missile at {{t}} ({slots} slots)", slots > 0, "no spell slots")
        if c.character_class is CharacterClass.CLERIC:
            per_target("sacred_flame", "Sacred Flame on {t}")
            acts.append(CombatAction("cure_wounds", f"Cure Wounds ({slots} slots)", slots > 0, "no spell slots"))
            has_undead = any(e.spec.undead for _, e in targets)
            cd = c.resources.get("channel_divinity", 0)
            acts.append(CombatAction(
                "turn_undead", "Turn Undead", cd > 0 and has_undead,
                "already used this rest" if cd <= 0 else "no undead here",
            ))
        if c.character_class is CharacterClass.FIGHTER:
            sw = c.resources.get("second_wind", 0)
            acts.append(CombatAction("second_wind", "Second Wind", sw > 0, "used this rest", free=True))
        potion = self._potion()
        acts.append(CombatAction(
            "potion", f"Drink {potion.name}" if potion else "Drink a potion",
            potion is not None, "no potions",
        ))
        flee_label = "Slip away (Cunning Action)" if c.character_class is CharacterClass.ROGUE else "Flee"
        acts.append(CombatAction("flee", flee_label))
        return acts

    def _potion(self):
        for item in self.character.inventory:
            if item.heal:
                return item
        return None

    # --- Flow -----------------------------------------------------------

    def start(self) -> list[Event]:
        events: list[Event] = []
        c = self.character
        player_init = dice.roll_d20(lucky=c.has_trait("lucky"))
        player_total = player_init.kept + c.mod("dexterity")
        best_enemy = max(dice.roll(20) + e.spec.dex_mod for e in self.enemies)
        self.player_first = player_total >= best_enemy
        events.append(RollEvent(
            label="Initiative", d20=player_init, modifier=c.mod("dexterity"), total=player_total,
            target=best_enemy, target_label="vs", success=self.player_first,
        ))
        self.round = 1
        if self.player_first:
            events.append(Notice("You act first."))
        else:
            events.append(Notice("They're faster. Brace yourself!", "danger"))
            events.extend(self._enemy_turns())
        return events

    def act(self, action_id: str) -> list[Event]:
        if self.over:
            return []
        action = next((a for a in self.actions() if a.id == action_id), None)
        if action is None or not action.enabled:
            return [Notice(f"You can't do that right now{': ' + action.reason if action else ''}.")]

        name, _, target_str = action_id.partition(":")
        target = self.enemies[int(target_str)] if target_str else None
        handler = getattr(self, f"_do_{name}")
        events = handler(target) if target is not None else handler()
        if self.over or action.free:
            self._check_victory(events)
            return events
        if not self._check_victory(events):
            events.extend(self._enemy_turns())
            self.round += 1
        return events

    def _check_victory(self, events: list[Event]) -> bool:
        if self.result is None and not self.active_enemies:
            self.result = "victory"
            events.append(CombatEndEvent("victory"))
        return self.result is not None

    # --- Player actions -------------------------------------------------

    def _attack_roll(self, label: str, bonus: int, target: Enemy) -> tuple[RollEvent, bool, bool]:
        roll = dice.roll_d20(lucky=self.character.has_trait("lucky"))
        total = roll.kept + bonus
        hit = roll.natural_20 or (total >= target.spec.ac and not roll.natural_1)
        event = RollEvent(
            label=label, d20=roll, modifier=bonus, total=total, target=target.spec.ac, target_label="AC",
            success=hit, critical=roll.natural_20, fumble=roll.natural_1,
        )
        return event, hit, roll.natural_20

    def _damage_enemy(self, target: Enemy, amount: int, damage_type: str, rolls=(), source="") -> list[Event]:
        if damage_type in target.spec.vulnerable:
            amount *= 2
            source = f"{source} x2 ({damage_type} vulnerability)"
        target.hp = max(0, target.hp - amount)
        events: list[Event] = [DamageEvent(target.name, amount, damage_type, target.hp, target.max_hp, tuple(rolls), source)]
        if target.hp == 0:
            events.append(Narration(f"The {target.name} falls and does not rise.", "loot"))
        return events

    def _do_attack(self, target: Enemy) -> list[Event]:
        c = self.character
        weapon = c.spec.weapon
        event, hit, crit = self._attack_roll(f"{weapon.name} attack", c.weapon_attack_bonus, target)
        events: list[Event] = [event]
        if not hit:
            events.append(Narration(f"Your {weapon.name.lower()} misses the {target.name}."))
            return events
        result = dice.roll_expr(weapon.damage, extra_bonus=c.mod(weapon.ability), critical=crit)
        total, rolls = result.total, list(result.rolls)
        source = weapon.name
        if c.character_class is CharacterClass.ROGUE:
            sneak = dice.roll_expr("1d6", critical=crit)
            total += sneak.total
            rolls += list(sneak.rolls)
            self.sneak_attack_used = True
            source += " + Sneak Attack"
        events.extend(self._damage_enemy(target, max(1, total), weapon.damage_type, rolls, source))
        return events

    def _do_fire_bolt(self, target: Enemy) -> list[Event]:
        event, hit, crit = self._attack_roll("Fire Bolt", self.character.spell_attack_bonus, target)
        events: list[Event] = [event]
        if not hit:
            events.append(Narration("The bolt of flame scorches the wall behind it."))
            return events
        result = dice.roll_expr("1d10", critical=crit)
        events.extend(self._damage_enemy(target, result.total, "fire", result.rolls, "Fire Bolt"))
        return events

    def _do_magic_missile(self, target: Enemy) -> list[Event]:
        self.character.spend("spell_slots")
        result = dice.roll_expr("3d4+3")
        events: list[Event] = [Narration("Three darts of glowing force streak out. They never miss.", "loot")]
        events.extend(self._damage_enemy(target, result.total, "force", result.rolls, "Magic Missile"))
        return events

    def _do_sacred_flame(self, target: Enemy) -> list[Event]:
        c = self.character
        save = dice.roll_d20()
        total = save.kept + target.spec.dex_mod
        saved = total >= c.spell_save_dc
        events: list[Event] = [RollEvent(
            label=f"{target.name} DEX save", d20=save, modifier=target.spec.dex_mod, total=total,
            target=c.spell_save_dc, target_label="DC", success=not saved,
            note="your spell hits if their save fails",
        )]
        if saved:
            events.append(Narration(f"Radiant flame falls, but the {target.name} twists out of it."))
            return events
        result = dice.roll_expr("1d8")
        events.extend(self._damage_enemy(target, result.total, "radiant", result.rolls, "Sacred Flame"))
        return events

    def _do_cure_wounds(self) -> list[Event]:
        c = self.character
        c.spend("spell_slots")
        result = dice.roll_expr("1d8", extra_bonus=c.mod("wisdom"))
        healed = c.heal(max(1, result.total))
        return [HealEvent("player", healed, c.current_hp, c.max_hp, "Cure Wounds")]

    def _do_second_wind(self) -> list[Event]:
        c = self.character
        c.spend("second_wind")
        result = dice.roll_expr("1d10", extra_bonus=c.level)
        healed = c.heal(result.total)
        return [HealEvent("player", healed, c.current_hp, c.max_hp, "Second Wind")]

    def _do_potion(self) -> list[Event]:
        c = self.character
        potion = self._potion()
        c.remove_item(potion.id)
        result = dice.roll_expr(potion.heal)
        healed = c.heal(result.total)
        return [ItemEvent(potion.name, gained=False), HealEvent("player", healed, c.current_hp, c.max_hp, potion.name)]

    def _do_turn_undead(self) -> list[Event]:
        c = self.character
        c.spend("channel_divinity")
        dc = c.spell_save_dc
        events: list[Event] = [Narration("You raise your holy symbol and the light of your god blazes out.", "loot")]
        for enemy in self.active_enemies:
            if not enemy.spec.undead:
                continue
            if enemy.spec.turn_resistant:
                events.append(Narration(f"The {enemy.name} recoils but holds its ground; it is too old and too strong.", "danger"))
                continue
            save = dice.roll_d20()
            total = save.kept + enemy.spec.wis_save
            saved = total >= dc
            events.append(RollEvent(
                label=f"{enemy.name} WIS save", d20=save, modifier=enemy.spec.wis_save, total=total,
                target=dc, target_label="DC", success=not saved,
            ))
            if not saved:
                enemy.fled = True
                events.append(Narration(f"The {enemy.name} turns and flees into the dark.", "loot"))
        return events

    def _do_flee(self) -> list[Event]:
        c = self.character
        if c.character_class is CharacterClass.ROGUE:
            self.result = "fled"
            return [Narration("You feint, duck and are gone before they understand what happened."), CombatEndEvent("fled")]
        ability = "strength" if c.mod("strength") >= c.mod("dexterity") else "dexterity"
        skill = "athletics" if ability == "strength" else "acrobatics"
        check = resolve_check(c, ability, FLEE_DC, skill)
        events: list[Event] = [check.to_event()]
        if check.success:
            self.result = "fled"
            events += [Narration("You break away and run until the sounds of pursuit fade."), CombatEndEvent("fled")]
        else:
            events.append(Narration("You try to break away, but they cut you off!", "danger"))
        return events

    # --- Enemy turns ----------------------------------------------------

    def _enemy_turns(self) -> list[Event]:
        events: list[Event] = []
        c = self.character
        for enemy in self.active_enemies:
            spec = enemy.spec
            roll = dice.roll_d20()
            total = roll.kept + spec.attack_bonus
            hit = roll.natural_20 or (total >= c.armor_class and not roll.natural_1)
            events.append(RollEvent(
                label=f"{enemy.name} attacks", d20=roll, modifier=spec.attack_bonus, total=total,
                target=c.armor_class, target_label="AC", success=hit, critical=roll.natural_20,
                fumble=roll.natural_1, note="enemy roll",
            ))
            if not hit:
                events.append(Narration(f"The {enemy.name} {spec.attack_verb}, but misses."))
                continue
            damage = dice.roll_expr(spec.damage, critical=roll.natural_20)
            extra = dice.roll_expr(spec.extra_damage, critical=roll.natural_20) if spec.extra_damage else None
            incoming = damage.total + (extra.total if extra else 0)
            if self._try_shield(total, incoming, roll.natural_20):
                events.append(Narration("You snap a word of power and a shimmering Shield turns the blow aside!", "loot"))
                continue
            dealt = c.take_damage(damage.total, spec.damage_type)
            events.append(Narration(f"The {enemy.name} {spec.attack_verb}!", "danger"))
            events.append(DamageEvent("player", dealt, spec.damage_type, c.current_hp, c.max_hp, damage.rolls, enemy.name))
            if extra and c.is_alive:
                dealt = c.take_damage(extra.total, spec.extra_damage_type)
                note = " (Dwarven Resilience)" if c.has_trait("poison_resistance") and spec.extra_damage_type == "poison" else ""
                events.append(DamageEvent("player", dealt, spec.extra_damage_type, c.current_hp, c.max_hp, extra.rolls, f"venom{note}"))
            if not c.is_alive:
                self.result = "defeat"
                events.append(CombatEndEvent("defeat"))
                break
        return events

    def _try_shield(self, attack_total: int, incoming: int, critical: bool) -> bool:
        """Wizards automatically cast Shield when a hit would otherwise drop them."""
        c = self.character
        if c.character_class is not CharacterClass.WIZARD or critical:
            return False
        if incoming < c.current_hp or attack_total >= c.armor_class + 5:
            return False
        return c.spend("spell_slots")

    # --- Persistence ----------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "enemies": [asdict(e) for e in self.enemies],
            "victory_scene": self.victory_scene,
            "flee_scene": self.flee_scene,
            "round": self.round,
            "result": self.result,
            "sneak_attack_used": self.sneak_attack_used,
        }

    @classmethod
    def from_dict(cls, character: Character, data: dict) -> "Combat":
        combat = cls(character, [], data.get("victory_scene"), data.get("flee_scene"))
        combat.enemies = [Enemy(**e) for e in data["enemies"]]
        combat.round = data.get("round", 1)
        combat.result = data.get("result")
        combat.sneak_attack_used = data.get("sneak_attack_used", False)
        return combat
