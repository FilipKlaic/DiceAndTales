"""The game engine: the single source of truth for game state.

The engine never prints or reads input. Every call returns a list of Events
describing what happened, and the UI decides how to show them. Both the
authored story and the AI Dungeon Master change the world only through the
engine, so the dice and the rules always apply.
"""

import random
from dataclasses import dataclass, field
from typing import Callable

from dice_and_tales.core import dice
from dice_and_tales.core.character import Character, Item, slugify
from dice_and_tales.core.checks import resolve_check
from dice_and_tales.core.combat import BESTIARY, Combat
from dice_and_tales.core.events import (
    CombatStartEvent, DamageEvent, Event, GameOverEvent, GoldEvent, HealEvent,
    ItemEvent, Narration, Notice, SceneEvent, XPEvent,
)
from dice_and_tales.core.rules import ABILITIES, ABILITY_LABELS, DAMAGE_TYPES, ITEMS, SKILLS, skill_label
from dice_and_tales.game.state import GameState, JournalEntry
from dice_and_tales.game.story import CheckSpec, Condition, Effects, Encounter, Option, Scene, Story

LONG_REST_COST = 2
DEATH_TITLE = "Fallen"
# What the Dungeon Master may hand out per scene, so free text can't be farmed for rewards.
DM_SCENE_BUDGET = {"xp": 50, "gold": 30, "items": 2, "consumables": 1, "heal": 10}

EXPLORE, CHECK, COMBAT, ENDED = "explore", "check", "combat", "ended"


@dataclass
class Choice:
    label: str
    key: str
    enabled: bool = True
    reason: str = ""
    tag: str = ""


@dataclass
class ToolOutcome:
    """Result of an AI Dungeon Master tool call, after the engine applied the rules."""

    result: dict
    events: list[Event] = field(default_factory=list)
    error: bool = False


def check_tag(spec: CheckSpec) -> str:
    name = ABILITY_LABELS[spec.ability]
    if spec.skill:
        name += f" ({skill_label(spec.skill)})"
    return f"{name} DC {spec.dc}"


class Engine:
    def __init__(self, story: Story, state: GameState, dm=None):
        self.story = story
        self.state = state
        self.dm = dm
        self._pending: list[tuple[str, object]] = []  # DM-requested transitions, applied after narration

    @classmethod
    def new_game(cls, story: Story, character: Character, seed: int | None = None, dm=None) -> tuple["Engine", list[Event]]:
        seed = seed if seed is not None else random.randrange(2**31)
        dice.seed(seed)
        state = GameState(character=character, scene_id=story.start, seed=seed)
        engine = cls(story, state, dm)
        return engine, engine.enter_scene(story.start)

    # --- Queries --------------------------------------------------------

    @property
    def character(self) -> Character:
        return self.state.character

    @property
    def scene(self) -> Scene:
        return self.story[self.state.scene_id]

    @property
    def mode(self) -> str:
        if self.state.ending:
            return ENDED
        if self.state.combat and not self.state.combat.over:
            return COMBAT
        if self.scene.check:
            return CHECK
        return EXPLORE

    @property
    def dm_available(self) -> bool:
        return self.dm is not None and getattr(self.dm, "available", False)

    @property
    def can_freeform(self) -> bool:
        return self.dm_available and self.mode == EXPLORE

    @property
    def can_save(self) -> bool:
        return self.mode in (EXPLORE, CHECK)

    def meets(self, cond: Condition) -> bool:
        c = self.character
        flags = self.state.flags
        return (
            all(f in flags for f in cond.requires_flags)
            and not any(f in flags for f in cond.forbids_flags)
            and all(c.has_item(i) for i in cond.requires_items)
            and (cond.requires_class is None or c.character_class.name == cond.requires_class)
            and (cond.requires_race is None or c.race.name == cond.requires_race)
            and c.gold >= cond.min_gold
        )

    def scene_text(self, scene_id: str | None = None) -> str:
        scene = self.story[scene_id] if scene_id else self.scene
        text = scene.text
        extra = []
        for variant in scene.variants:
            if self.meets(variant.condition):
                if variant.replace:
                    text = variant.text
                else:
                    extra.append(variant.text)
        return "\n\n".join([text, *extra])

    def visible_options(self) -> list[tuple[Option, bool, str]]:
        """Options to show, with (enabled, reason). Flag/class gates hide; item/gold gates lock."""
        out = []
        for opt in self.scene.options:
            cond = opt.condition
            soft = Condition(requires_items=cond.requires_items, min_gold=cond.min_gold)
            hard = Condition(
                requires_flags=cond.requires_flags, forbids_flags=cond.forbids_flags,
                requires_class=cond.requires_class, requires_race=cond.requires_race,
            )
            if not self.meets(hard):
                continue
            enabled = self.meets(soft)
            reason = ""
            if not enabled:
                missing = [ITEMS[i].name for i in cond.requires_items if not self.character.has_item(i)]
                reason = f"needs {', '.join(missing)}" if missing else f"needs {cond.min_gold} gold"
            out.append((opt, enabled, reason))
        return out

    def choices(self) -> list[Choice]:
        mode = self.mode
        if mode == ENDED:
            return []
        if mode == COMBAT:
            return [Choice(a.label, a.id, a.enabled, a.reason, "bonus action, keeps your turn" if a.free else "")
                    for a in self.state.combat.actions()]
        if mode == CHECK:
            return [Choice("Roll the dice", "roll", tag=check_tag(self.scene.check))]
        choices = []
        for i, (opt, enabled, reason) in enumerate(self.visible_options()):
            tag = check_tag(opt.check) if opt.check else ("fight" if opt.encounter else "")
            choices.append(Choice(opt.text, str(i), enabled, reason, tag))
        return choices

    def exits(self) -> dict[str, str]:
        """Scene ids reachable from here by plain `goto` options: what the DM may move the player to."""
        return {opt.goto: opt.text for opt, enabled, _ in self.visible_options() if opt.goto and enabled}

    def _exit_option(self, scene_id: str) -> Option | None:
        return next((opt for opt, enabled, _ in self.visible_options() if enabled and opt.goto == scene_id), None)

    # --- Player actions -------------------------------------------------

    def choose(self, key: str) -> list[Event]:
        mode = self.mode
        self.state.turns += 1
        if mode == COMBAT:
            return self._combat_action(key)
        if mode == CHECK:
            return self._resolve_check(self.scene.check)
        if mode == ENDED:
            return []
        visible = self.visible_options()
        try:
            opt, enabled, reason = visible[int(key)]
        except (ValueError, IndexError):
            return [Notice("That isn't one of the options.")]
        if not enabled:
            return [Notice(f"You can't do that yet ({reason}).")]
        return self._take_option(opt)

    def _take_option(self, opt: Option) -> list[Event]:
        """Apply an option's effects (rewards only the first time it's taken), then follow it."""
        key = f"{self.state.scene_id}:{self.scene.options.index(opt)}"
        first_time = key not in self.state.used_options
        self.state.used_options.add(key)
        events = self.apply_effects(opt.effects, first_time=first_time)
        if opt.check:
            events += self._resolve_check(opt.check)
        elif opt.encounter:
            events += self.start_combat(opt.encounter)
        else:
            events += self.enter_scene(opt.goto)
        return events

    def short_rest(self) -> list[Event]:
        if self.mode not in (EXPLORE, CHECK):
            return [Notice("There's no time to rest now!", "danger")]
        c = self.character
        healed = c.short_rest()
        if healed < 0:
            return [Notice("You're too wound up to rest again. You need a proper night's sleep.")]
        return [
            Narration("You find a quiet corner, bind your wounds and catch your breath for an hour."),
            HealEvent("player", healed, c.current_hp, c.max_hp, "Short rest"),
            Notice(f"Short rests left today: {c.resources.get('short_rests', 0)}"),
        ]

    def long_rest(self) -> list[Event]:
        if self.mode not in (EXPLORE, CHECK):
            return [Notice("There's no time to rest now!", "danger")]
        if not self.scene.safe:
            return [Notice("It isn't safe to sleep here. Find somewhere with a roof and a lock.")]
        c = self.character
        if c.gold < LONG_REST_COST:
            return [Notice(f"A room costs {LONG_REST_COST} gold, and you can't afford it.")]
        c.gold -= LONG_REST_COST
        healed = c.long_rest()
        return [
            Narration("You rent a room upstairs and sleep like the dead. Which, around here, is a poor choice of words."),
            GoldEvent(-LONG_REST_COST, c.gold),
            HealEvent("player", healed, c.current_hp, c.max_hp, "Long rest"),
            Notice("HP, spell slots and abilities fully restored."),
        ]

    def use_item(self, item_id: str) -> list[Event]:
        c = self.character
        item = c.find_item(item_id)
        if item is None:
            return [Notice("You don't have that.")]
        if self.mode == ENDED:
            return []
        if self.mode == COMBAT:
            return [Notice("Use the combat options to drink potions in a fight.")]
        if not item.heal:
            return [Notice(f"{item.name}: {item.description}")]
        c.remove_item(item.id)
        result = dice.roll_expr(item.heal)
        healed = c.heal(result.total)
        return [ItemEvent(item.name, gained=False), HealEvent("player", healed, c.current_hp, c.max_hp, item.name)]

    def journal(self, text: str, source: str = "story") -> None:
        if any(entry.text == text for entry in self.state.journal):
            return
        self.state.journal.append(JournalEntry(text=text, where=self.scene.title, source=source))

    # --- Scene flow -----------------------------------------------------

    def enter_scene(self, scene_id: str) -> list[Event]:
        first_time = scene_id not in self.state.visited
        self.state.scene_id = scene_id
        self.state.visited.add(scene_id)
        scene = self.scene
        events: list[Event] = [SceneEvent(scene_id)]
        events += self.apply_effects(scene.on_enter, first_time)
        if not self.character.is_alive:
            return events + self._die()
        if scene.encounter:
            events += self.start_combat(scene.encounter)
        if scene.is_ending:
            self.state.ending = scene.ending
            self.state.victory = scene.victory
            events.append(GameOverEvent(scene.ending, scene.victory))
        return events

    def apply_effects(self, eff: Effects, first_time: bool = True) -> list[Event]:
        """Flags and items always apply; gold, XP, healing and journal entries only once."""
        c = self.character
        events: list[Event] = []
        self.state.flags.update(eff.set_flags)
        self.state.flags.difference_update(eff.clear_flags)
        for item_id in eff.give_items:
            if ITEMS[item_id].kind == "quest" and c.has_item(item_id):
                continue
            c.add_item(Item.from_catalog(item_id))
            events.append(ItemEvent(ITEMS[item_id].name, gained=True))
        for item_id in eff.take_items:
            removed = c.remove_item(item_id)
            if removed:
                events.append(ItemEvent(removed.name, gained=False))
        if not first_time:
            return events
        if eff.gold:
            before = c.gold
            c.gold = max(0, c.gold + eff.gold)
            if c.gold != before:
                events.append(GoldEvent(c.gold - before, c.gold))
        if eff.heal:
            healed = c.heal(dice.roll_expr(eff.heal).total)
            events.append(HealEvent("player", healed, c.current_hp, c.max_hp))
        if eff.xp:
            events += self.award_xp(eff.xp)
        if eff.journal:
            self.journal(eff.journal)
        return events

    def award_xp(self, amount: int) -> list[Event]:
        c = self.character
        levels = c.add_xp(amount)
        events: list[Event] = [XPEvent(amount, c.xp, levels)]
        for level in levels:
            events.append(Notice(f"LEVEL UP! You are now level {level}. Max HP is {c.max_hp}.", "loot"))
            self.journal(f"Reached level {level}.")
        return events

    def _resolve_check(self, spec: CheckSpec) -> list[Event]:
        c = self.character
        result = resolve_check(c, spec.ability, spec.dc, spec.skill)
        events: list[Event] = [result.to_event()]
        if not result.success and spec.damage:
            damage = dice.roll_expr(spec.damage)
            dealt = c.take_damage(damage.total, spec.damage_type)
            events.append(DamageEvent("player", dealt, spec.damage_type, c.current_hp, c.max_hp, damage.rolls))
            if not c.is_alive:
                return events + self._die()
        return events + self.enter_scene(spec.success if result.success else spec.failure)

    # --- Combat ---------------------------------------------------------

    def start_combat(self, encounter: Encounter) -> list[Event]:
        combat = Combat(self.character, list(encounter.enemies), encounter.victory, encounter.flee)
        self.state.combat = combat
        names = [e.name for e in combat.enemies]
        events: list[Event] = [CombatStartEvent(names)]
        events += combat.start()
        return events + self._after_combat_step()

    def _combat_action(self, action_id: str) -> list[Event]:
        events = self.state.combat.act(action_id)
        return events + self._after_combat_step()

    def _after_combat_step(self) -> list[Event]:
        combat = self.state.combat
        if combat is None or not combat.over:
            return []
        self.state.combat = None
        if combat.result == "defeat":
            return self._die()
        events: list[Event] = []
        if combat.result == "victory":
            events += self.award_xp(combat.xp_reward)
            self.journal(f"Defeated {', '.join(e.name for e in combat.enemies)}.")
            if combat.victory_scene:
                events += self.enter_scene(combat.victory_scene)
        elif combat.result == "fled" and combat.flee_scene:
            events += self.enter_scene(combat.flee_scene)
        return events

    def _die(self) -> list[Event]:
        self.state.combat = None
        self.state.ending = DEATH_TITLE
        self.state.victory = False
        self.journal("Fell in battle. The story ends here.")
        return [Narration("Your vision narrows to a point of light, and then even that is gone.", "danger"),
                GameOverEvent(DEATH_TITLE, False)]

    # --- AI Dungeon Master ----------------------------------------------

    def freeform(
        self,
        action: str,
        on_text: Callable[[str], None] | None = None,
        on_event: Callable[[Event], None] | None = None,
        on_retract: Callable[[int], None] | None = None,
    ) -> list[Event]:
        """Hand a free-text action to the Dungeon Master. Runs a network call; call off the UI thread."""
        if not self.can_freeform:
            return [Notice("The Dungeon Master isn't available right now.")]
        self.state.turns += 1
        self._pending = []
        events = self.dm.act(self, action, on_text=on_text, on_event=on_event, on_retract=on_retract)
        if self.state.ending:  # the DM's damage killed the character
            return events
        for kind, payload in self._pending:
            if kind == "move":
                opt = self._exit_option(payload)
                events += self._take_option(opt) if opt else self.enter_scene(payload)
            elif kind == "combat":
                events += self.start_combat(payload)
            if self.mode != EXPLORE:
                break
        self._pending = []
        return events

    def dm_context(self) -> dict:
        c = self.character
        return {
            "scene_title": self.scene.title,
            "scene_text": self.scene_text(),
            "exits": self.exits(),
            "options": [ch.label for ch in self.choices() if ch.enabled],
            "flags": sorted(self.state.flags),
            "journal": [j.text for j in self.state.journal[-12:]],
            "character": {
                "name": c.name, "title": c.title, "level": c.level,
                "hp": f"{c.current_hp}/{c.max_hp}", "ac": c.armor_class, "gold": c.gold,
                "scores": {ABILITY_LABELS[a]: f"{c.scores[a]} ({c.mod(a):+d})" for a in ABILITIES},
                "proficient_skills": list(c.spec.skills),
                "traits": list(c.race_spec.traits),
                "inventory": [i.name for i in c.inventory],
            },
        }

    def _spend_budget(self, kind: str, amount: int = 1) -> int:
        """Spend up to `amount` of this scene's DM budget for `kind`; returns what was allowed."""
        key = f"{self.state.scene_id}:{kind}"
        used = self.state.dm_budget.get(key, 0)
        allowed = max(0, min(amount, DM_SCENE_BUDGET[kind] - used))
        self.state.dm_budget[key] = used + allowed
        return allowed

    def dm_tool(self, name: str, args: dict) -> ToolOutcome:
        """Apply one Dungeon Master tool call under the game's rules."""
        handler = getattr(self, f"_dm_{name}", None)
        if handler is None:
            return ToolOutcome({"error": f"unknown tool {name!r}"}, error=True)
        try:
            return handler(**args)
        except (TypeError, ValueError, KeyError) as exc:
            return ToolOutcome({"error": f"invalid input: {exc}"}, error=True)

    def _dm_request_check(self, ability: str, dc: int, reason: str, skill: str | None = None,
                          advantage: str = "none") -> ToolOutcome:
        if skill:
            skill = slugify(skill)
            if skill not in SKILLS:
                return ToolOutcome({"error": f"unknown skill {skill!r}; valid: {sorted(SKILLS)}"}, error=True)
            ability = SKILLS[skill]
        if ability not in ABILITIES:
            return ToolOutcome({"error": f"unknown ability {ability!r}"}, error=True)
        dc = max(5, min(25, int(dc)))
        result = resolve_check(self.character, ability, dc, skill,
                               advantage=advantage == "advantage", disadvantage=advantage == "disadvantage")
        return ToolOutcome(result.summary(), [result.to_event()])

    def _dm_deal_damage(self, amount: int, damage_type: str, reason: str) -> ToolOutcome:
        c = self.character
        if damage_type not in DAMAGE_TYPES:
            damage_type = "bludgeoning"
        amount = max(1, min(10, int(amount)))
        dealt = c.take_damage(amount, damage_type)
        events: list[Event] = [DamageEvent("player", dealt, damage_type, c.current_hp, c.max_hp, source=reason)]
        result = {"damage_dealt": dealt, "hp": f"{c.current_hp}/{c.max_hp}"}
        if not c.is_alive:
            events += self._die()
            result["character_died"] = True
        return ToolOutcome(result, events)

    def _dm_heal(self, amount: int, reason: str) -> ToolOutcome:
        c = self.character
        allowed = self._spend_budget("heal", max(1, min(10, int(amount))))
        if not allowed:
            return ToolOutcome({"error": "no more healing is available here; the player should rest or use a potion"}, error=True)
        healed = c.heal(allowed)
        return ToolOutcome({"healed": healed, "hp": f"{c.current_hp}/{c.max_hp}"},
                           [HealEvent("player", healed, c.current_hp, c.max_hp, reason)])

    def _dm_give_item(self, name: str, description: str) -> ToolOutcome:
        c = self.character
        name = name.strip()[:40]
        if not name:
            return ToolOutcome({"error": "item needs a name"}, error=True)
        catalog_id = next((k for k, v in ITEMS.items() if v.name.lower() == name.lower() or k == slugify(name)), None)
        if catalog_id and ITEMS[catalog_id].kind == "quest":
            return ToolOutcome({"error": f"{name!r} is a story item; the player must find it in the authored story"}, error=True)
        if len(c.inventory) >= 20:
            return ToolOutcome({"error": "the character's pack is full"}, error=True)
        if catalog_id and ITEMS[catalog_id].heal and not self._spend_budget("consumables"):
            return ToolOutcome({"error": "no more potions can be found here"}, error=True)
        if not self._spend_budget("items"):
            return ToolOutcome({"error": "nothing more of value turns up here"}, error=True)
        # Improvised items get their own namespace so they can never satisfy a story gate.
        item = Item.from_catalog(catalog_id) if catalog_id else Item(f"dm:{slugify(name)}", name, description.strip()[:200])
        c.add_item(item)
        return ToolOutcome({"added": item.name, "inventory": [i.name for i in c.inventory]},
                           [ItemEvent(item.name, gained=True)])

    def _dm_take_item(self, name: str) -> ToolOutcome:
        item = self.character.remove_item(name)
        if item is None:
            return ToolOutcome({"error": f"the character has no {name!r}",
                                "inventory": [i.name for i in self.character.inventory]}, error=True)
        return ToolOutcome({"removed": item.name}, [ItemEvent(item.name, gained=False)])

    def _dm_change_gold(self, amount: int, reason: str) -> ToolOutcome:
        c = self.character
        amount = max(-50, min(50, int(amount)))
        if c.gold + amount < 0:
            return ToolOutcome({"error": f"the character only has {c.gold} gold"}, error=True)
        if amount > 0:
            amount = self._spend_budget("gold", amount)
            if not amount:
                return ToolOutcome({"error": "there's no more money to be made here"}, error=True)
        c.gold += amount
        return ToolOutcome({"gold": c.gold}, [GoldEvent(amount, c.gold)])

    def _dm_set_flag(self, flag: str, value: bool = True) -> ToolOutcome:
        flag = slugify(flag)
        if value:
            self.state.flags.add(flag)
        else:
            self.state.flags.discard(flag)
        return ToolOutcome({"flags": sorted(self.state.flags)})

    def _dm_move_to(self, scene_id: str) -> ToolOutcome:
        exits = self.exits()
        if scene_id not in exits:
            return ToolOutcome({"error": f"{scene_id!r} is not reachable from here", "valid_exits": exits}, error=True)
        if any(kind in ("move", "combat") for kind, _ in self._pending):
            return ToolOutcome({"error": "a scene change or fight is already queued this turn"}, error=True)
        self._pending.append(("move", scene_id))
        return ToolOutcome({"queued": f"the player will arrive at '{self.story[scene_id].title}' after your narration"})

    def _dm_start_combat(self, enemies: list[str]) -> ToolOutcome:
        if not enemies or len(enemies) > 3:
            return ToolOutcome({"error": "choose 1 to 3 enemies"}, error=True)
        unknown = [e for e in enemies if e not in BESTIARY]
        if unknown:
            return ToolOutcome({"error": f"unknown enemies {unknown}", "bestiary": sorted(BESTIARY)}, error=True)
        if "priest_shade" in enemies:
            return ToolOutcome({"error": "the war-priest's shade can only be fought in the authored story"}, error=True)
        if any(kind in ("move", "combat") for kind, _ in self._pending):
            return ToolOutcome({"error": "a scene change or fight is already queued this turn"}, error=True)
        self._pending.append(("combat", Encounter(enemies=list(enemies))))
        return ToolOutcome({"queued": "combat begins after your narration; the game runs the fight"})

    def _dm_award_xp(self, amount: int, reason: str) -> ToolOutcome:
        amount = self._spend_budget("xp", max(0, min(50, int(amount))))
        if not amount:
            return ToolOutcome({"error": "no more experience is to be gained here; move the story on"}, error=True)
        events = self.award_xp(amount)
        return ToolOutcome({"xp": self.character.xp, "level": self.character.level}, events)

    def _dm_add_journal(self, entry: str) -> ToolOutcome:
        self.journal(entry.strip()[:300], source="dm")
        return ToolOutcome({"ok": True})
