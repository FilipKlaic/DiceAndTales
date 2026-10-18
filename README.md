# Dice & Tales

A terminal D&D-style adventure where an **AI Dungeon Master improvises inside real dice rules**.

Roll a hero, walk into The Rusty Flagon, and choose your path, or ignore the options entirely and type whatever you want to try. Claude narrates what happens, but it can't fudge anything: when your action is risky, it asks the game for an ability check, and the engine rolls a real d20 with your real modifiers. Damage, loot, gold and movement only happen through the engine, so the AI tells the story and the dice decide it.

![Python](https://img.shields.io/badge/python-3.11+-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)

## Features

- **AI Dungeon Master with real rules.** Free-text actions go to Claude with a set of game tools (`request_check`, `deal_damage`, `give_item`, `move_to`, `start_combat`, ...). The engine validates every call, caps it and applies it, then hands the result back for Claude to narrate.
- **An authored story with a backbone.** 50 scenes, 6 endings and a few secrets. NPCs remember what you did (try picking Hilda's pocket), and options unlock from flags, items, class and race.
- **Turn-based combat.** Initiative, attack rolls against AC, crits, damage vulnerabilities, and enemies with their own turns.
- **Classes that play differently:**
  - Fighter: Second Wind
  - Rogue: Sneak Attack, Cunning Action escape, stealth advantage
  - Wizard: Fire Bolt, Magic Missile, an automatic Shield
  - Cleric: Cure Wounds, Sacred Flame, Turn Undead
- **Races with traits:** Halfling Lucky rerolls, Dwarven poison resistance, Elven keen senses, Human versatility.
- **Progression and resources:** XP and levelling to level 3, spell slots, short and long rests, potions, inventory and gold.
- **A full terminal UI** built with [Textual]:
  - Animated d20 rolls. Natural 20s flash gold and natural 1s shake.
  - Scene art, a typewriter effect you can skip with space, and a live sidebar with HP/XP bars, enemies and a dice log.
  - Mouse support.
- **Persistence:** autosave on every move, three manual save slots, an auto-written journal and persistent settings.
- **Works offline.** Without an API key you still get the full authored game. Only free-text actions need Claude.

## Install and play

```bash
pip install -e .
dice-and-tales
```

or, without installing:

```bash
python -m dice_and_tales
```

For the AI Dungeon Master, set your Anthropic API key first:

```bash
export ANTHROPIC_API_KEY=your_key_here
```

### Controls

| Key | Action |
| --- | --- |
| `1`-`9`, arrows + Enter | choose an option |
| `/` | describe your own action |
| `c` / `i` / `j` | character sheet / inventory / journal |
| `r` | rest (short anywhere, long in the tavern) |
| `space` | skip the text animation |
| `ctrl+s` | save |
| `?` | help |
| `esc` | menu |

### Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | none | enables the AI Dungeon Master |
| `DICE_TALES_MODEL` | `claude-opus-5-5` | model used for narration |
| `DICE_TALES_EFFORT` | `low` | thinking effort (`low` to `max`); low keeps narration snappy |
| `DICE_TALES_HOME` | `~/.dice_and_tales` | where saves and settings live |

Text speed, dice animations and the AI DM can also be toggled in-game under Settings.

## How the AI Dungeon Master works

```
player types: "I try to swipe Hilda's coin purse"
        |
        v
Claude (system prompt: world, rules, current state, exits)
        |  request_check(dexterity, sleight_of_hand, dc=14)
        v
Engine rolls d20 + DEX + proficiency -> 10 vs 14, failure
        |  result returned as a tool_result
        v
Claude: "Hilda's hand clamps around your wrist..."  + set_flag(hilda_angered)
        |
        v
Authored story reacts: Hilda is cold to you until you win her back
```

- **The engine is the source of truth.** Tool inputs are schema-validated and clamped (for example, at most 10 damage per call and ±50 gold), and limited per action. Movement is restricted to the current scene's exits, and the final boss can't be summoned.
- Scene changes and fights the DM asks for are applied *after* the narration finishes, so the story reads in order.
- Claude sees a cached, static system prompt (world, rules, flags, bestiary) plus a fresh snapshot of the game state and the last few exchanges.
- Requests use adaptive thinking, streaming with eager tool-input streaming, and server-side refusal fallbacks. API errors turn into in-world notices instead of crashing the game.

## Writing stories

The whole adventure lives in [`dice_and_tales/data/story.toml`](dice_and_tales/data/story.toml). Scenes have text, optional conditional text variants, options (`goto`, `check` or `encounter`), on-enter effects (flags, items, gold, XP, journal) and endings. The loader validates everything at startup:
- broken links
- undeclared flags
- unknown items or enemies
- skills paired with the wrong ability
- dead ends
- unreachable scenes

```bash
python -m dice_and_tales --check-story               # validate the bundled story
python -m dice_and_tales --story my_story.toml       # play your own
```

## Project structure

```
dice_and_tales/
├── core/     # pure rules: dice, characters, checks, combat, events
├── game/     # story loader, engine, AI Dungeon Master, saves
├── data/     # story.toml
└── ui/       # Textual app, screens, widgets, stylesheet
tests/        # rules, combat, story, engine, DM (through a mock API), headless UI
```

## Development

```bash
pip install -e ".[dev]"
pytest
```

The DM tests run the real `anthropic` SDK against a scripted mock transport, so they cover request building, streaming and the tool loop without network access or an API key.

[Textual]: https://textual.textualize.io/
