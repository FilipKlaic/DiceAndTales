# Dice & Tales

A terminal-based DnD-style text adventure game built in Python.

Roll your character, choose your path, and see where the dice take you. The story unfolds through choices — some peaceful, some decided by a d20. With an Anthropic API key, you can go off-script entirely and let an AI narrator respond to anything you do.

## Features

- Character creation with class, race, and randomly rolled stats (4d6 drop lowest)
- Skill checks with visible dice rolls — DEX to sneak, STR to fight
- HP tracking with combat damage on failed checks
- Branching narrative with multiple paths and endings
- Type `stats` at any prompt to view your character sheet
- **Freeform storytelling** — skip the menu and type any action; Claude narrates what happens next
- Layered architecture (core / game / ui) built for easy expansion

## Tech Stack

![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)

## How to Run

```bash
pip install -r requirements.txt
python main.py
```

For freeform AI storytelling, set your Anthropic API key first:

```bash
export ANTHROPIC_API_KEY=your_key_here
python main.py
```

## Story Premise

You arrive at The Rusty Flagon, a tavern on the edge of a quiet town. A barkeep mentions a nearby tomb and a bounty. A hooded figure in the corner hasn't moved in three nights. What you do next — and how the dice fall — determines how it ends.

## Project Structure

```
DiceAndTales/
├── main.py          # Entry point and character creation
├── core/            # Pure game rules — dice and character model
├── game/            # Scene structure, story content, and game loop
└── ui/              # Terminal rendering and input handling
```
