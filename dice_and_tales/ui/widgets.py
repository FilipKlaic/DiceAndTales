"""Reusable widgets: stat bars, the character panel, enemy list, dice log and the animated die."""

import asyncio
import random

from rich.text import Text
from textual.widgets import Static

from dice_and_tales.core.events import RollEvent
from dice_and_tales.core.rules import ABILITIES, ABILITY_LABELS, TRAIT_LABELS
from dice_and_tales.ui.art import DIE_BOX


def bar(current: int, maximum: int, width: int = 18, colour: str | None = None) -> Text:
    maximum = max(1, maximum)
    filled = round(width * max(0, current) / maximum)
    if colour is None:
        ratio = current / maximum
        colour = "green" if ratio > 0.6 else "yellow" if ratio > 0.3 else "red"
    out = Text()
    out.append("█" * filled, style=colour)
    out.append("░" * (width - filled), style="grey37")
    return out


def pips(current: int, maximum: int) -> str:
    return "●" * current + "○" * max(0, maximum - current)


class CharacterPanel(Static):
    """Name, HP, XP, AC, gold, resources, abilities and pack, all at a glance."""

    def show(self, engine) -> None:
        c = engine.character
        t = Text()
        t.append(f"{c.name}\n", style="bold")
        t.append(f"Level {c.level} {c.title}\n\n", style="italic")
        t.append("HP  ")
        t.append_text(bar(c.current_hp, c.max_hp))
        t.append(f" {c.current_hp}/{c.max_hp}\n")
        nxt = c.next_level_xp
        if nxt:
            t.append("XP  ")
            t.append_text(bar(c.xp, nxt, colour="magenta"))
            t.append(f" {c.xp}/{nxt}\n")
        else:
            t.append(f"XP  {c.xp} (max level)\n")
        t.append(f"AC {c.armor_class}   Gold {c.gold}\n", style="bold")

        res = c.resources
        lines = []
        if "spell_slots" in res:
            lines.append(f"Spell slots {pips(res['spell_slots'], c.max_resource('spell_slots'))}")
        if "second_wind" in res:
            lines.append(f"Second Wind {pips(res['second_wind'], 1)}")
        if "channel_divinity" in res:
            lines.append(f"Turn Undead {pips(res['channel_divinity'], 1)}")
        lines.append(f"Short rests {pips(res.get('short_rests', 0), c.max_resource('short_rests'))}")
        t.append("\n".join(lines) + "\n\n", style="cyan")

        for i, ability in enumerate(ABILITIES):
            t.append(f"{ABILITY_LABELS[ability]} {c.scores[ability]:>2} ({c.mod(ability):+d})")
            t.append("\n" if i % 2 else "   ")
        traits = [TRAIT_LABELS[x] for x in c.race_spec.traits]
        if traits:
            t.append("Traits: " + ", ".join(traits) + "\n", style="italic")

        t.append("\nPack\n", style="bold underline")
        if not c.inventory:
            t.append("  (empty)\n", style="grey50")
        for item in c.inventory[:10]:
            style = "yellow" if item.kind == "quest" else "green" if item.heal else ""
            t.append(f"  {item.name}\n", style=style)
        if len(c.inventory) > 10:
            t.append(f"  ...and {len(c.inventory) - 10} more (press i)\n", style="grey50")
        self.update(t)


class EnemyPanel(Static):
    def show(self, combat) -> None:
        self.display = combat is not None and not combat.over
        if not self.display:
            return
        t = Text()
        t.append(f"COMBAT, round {combat.round}\n", style="bold red")
        for enemy in combat.enemies:
            if enemy.fled:
                t.append(f"{enemy.name}: fled\n", style="grey50 strike")
            elif enemy.hp <= 0:
                t.append(f"{enemy.name}: defeated\n", style="grey50 strike")
            else:
                t.append(f"{enemy.name}  AC {enemy.spec.ac}\n")
                t.append_text(bar(enemy.hp, enemy.max_hp, width=16, colour="red"))
                t.append(f" {enemy.hp}/{enemy.max_hp}\n")
        self.update(t)


def roll_line(event: RollEvent) -> Text:
    t = Text(no_wrap=True, overflow="ellipsis")
    mark, style = ("✓", "green") if event.success else ("✗", "red")
    if event.critical:
        style = "bold yellow"
    target = f"{event.target_label} {event.target}" if event.target_label != "vs" else str(event.target)
    t.append(f"{mark} {event.total:>2} vs {target:<6}", style=style)
    t.append(f" {event.label}", style="grey70")
    return t


class DiceLog(Static):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lines: list[Text] = []

    def add(self, event: RollEvent) -> None:
        self.lines = (self.lines + [roll_line(event)])[-8:]
        t = Text()
        t.append("Dice log\n", style="bold underline")
        for line in reversed(self.lines):
            t.append_text(line)
            t.append("\n")
        self.update(t)


class DiceRoll(Static):
    """An inline die that tumbles, lands and reports the outcome."""

    def __init__(self, event: RollEvent, animate: bool = True):
        super().__init__(classes="dice-roll")
        self.event = event
        self.animate_roll = animate

    def frame(self, shown: int, final: bool) -> Text:
        e = self.event
        top, mid, bot = DIE_BOX
        style = "bold"
        if final:
            style = "bold yellow" if e.critical else "bold red" if e.fumble else ("bold green" if e.success else "bold red")
        t = Text()
        t.append(top + "\n", style=style)
        t.append(mid.format(n=shown), style=style)
        if final:
            target = f"vs {e.target_label} {e.target}" if e.target_label != "vs" else f"vs {e.target}"
            t.append(f"  {e.label}: {e.d20.kept} {e.modifier:+d} = {e.total}  {target}  ")
            if e.critical:
                t.append("✦ NATURAL 20 ✦", style="bold black on yellow")
            elif e.fumble:
                t.append("✖ NATURAL 1 ✖", style="bold white on red")
            elif e.success:
                t.append("SUCCESS", style="bold green")
            else:
                t.append("FAILURE", style="bold red")
        else:
            t.append(f"  {e.label}...", style="italic")
        t.append("\n" + bot, style=style)
        notes = []
        if len(e.d20.rolls) > 1:
            notes.append(f"{e.d20.mode}: rolled {', '.join(map(str, e.d20.rolls))}")
        if e.note:
            notes.append(e.note)
        if final and notes:
            t.append("   " + " · ".join(notes), style="grey62 italic")
        return t

    async def play(self) -> None:
        if self.animate_roll:
            for i in range(10):
                self.update(self.frame(random.randint(1, 20), final=False))
                await asyncio.sleep(0.04 + i * 0.012)
        self.update(self.frame(self.event.d20.kept, final=True))
        if self.animate_roll and self.event.critical:
            self.add_class("crit")
            await asyncio.sleep(0.6)
            self.remove_class("crit")
        elif self.animate_roll and self.event.fumble:
            for dx in (2, -2, 1, -1, 0):
                self.styles.offset = (dx, 0)
                await asyncio.sleep(0.05)
