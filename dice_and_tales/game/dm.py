"""The AI Dungeon Master: Claude narrates, the engine enforces the rules.

Claude never changes the world directly. When the player does something
uncertain or consequential, Claude calls a tool (request_check, deal_damage,
give_item, move_to, ...). The engine validates and applies it, rolls the real
dice, and returns the outcome, and Claude then narrates what actually happened.
"""

import json
import os
from pathlib import Path
from typing import Callable

import anthropic

from dice_and_tales import config
from dice_and_tales.core.combat import BESTIARY
from dice_and_tales.core.events import Event, Notice
from dice_and_tales.core.rules import ABILITIES, DAMAGE_TYPES, SKILLS

FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_STEPS = 6          # model round-trips per player action
MAX_HISTORY = 8        # past exchanges replayed for continuity
PER_TURN_LIMITS = {"request_check": 2, "deal_damage": 2, "give_item": 2, "change_gold": 1, "award_xp": 1, "heal": 1}

# --- Tools ---------------------------------------------------------------

def _tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {
        "name": name,
        "description": description,
        "eager_input_streaming": True,
        "input_schema": {"type": "object", "properties": properties, "required": required, "additionalProperties": False},
    }


REASON = {"type": "string", "description": "Short in-world reason, shown to the player."}

TOOLS = [
    _tool("request_check",
          "Ask the game to roll an ability check for the player. Use it whenever the outcome of the player's action is "
          "uncertain and failure would be interesting. The game rolls a real d20 with the character's modifiers and "
          "returns the result; narrate the outcome it gives you, never a different one. Easy DC 10, medium 13, hard 15, "
          "very hard 18.",
          {"ability": {"type": "string", "enum": list(ABILITIES)},
           "skill": {"type": "string", "enum": sorted(SKILLS), "description": "Optional skill; sets the ability automatically."},
           "dc": {"type": "integer", "minimum": 5, "maximum": 25},
           "advantage": {"type": "string", "enum": ["none", "advantage", "disadvantage"]},
           "reason": REASON},
          ["ability", "dc", "reason"]),
    _tool("deal_damage",
          "Hurt the player: a failed climb, a trap, a punch from an NPC. 1-3 minor, 4-6 serious, 7-10 deadly. "
          "Use start_combat instead for a real fight.",
          {"amount": {"type": "integer", "minimum": 1, "maximum": 10},
           "damage_type": {"type": "string", "enum": list(DAMAGE_TYPES)},
           "reason": REASON},
          ["amount", "damage_type", "reason"]),
    _tool("heal", "Restore some of the player's HP (a kind healer, a hot meal, a moment of rest).",
          {"amount": {"type": "integer", "minimum": 1, "maximum": 10}, "reason": REASON},
          ["amount", "reason"]),
    _tool("give_item", "Put an item the player has found, bought or been given into their inventory.",
          {"name": {"type": "string", "maxLength": 40}, "description": {"type": "string", "maxLength": 200}},
          ["name", "description"]),
    _tool("take_item", "Remove an item from the player's inventory (used up, lost, stolen or given away).",
          {"name": {"type": "string"}},
          ["name"]),
    _tool("change_gold", "Add or remove gold: payment, bribes, purchases, theft. Negative removes.",
          {"amount": {"type": "integer", "minimum": -50, "maximum": 50}, "reason": REASON},
          ["amount", "reason"]),
    _tool("set_flag",
          "Record a lasting fact about the world, such as an NPC's attitude or a discovered secret. Use a known flag "
          "from the list in your instructions when one fits, because the authored story reacts to those.",
          {"flag": {"type": "string", "description": "snake_case name"}, "value": {"type": "boolean"}},
          ["flag", "value"]),
    _tool("move_to",
          "Move the player to one of the current scene's exits after your narration. Only ids listed under 'exits' "
          "are allowed.",
          {"scene_id": {"type": "string"}},
          ["scene_id"]),
    _tool("start_combat",
          "Start a turn-based fight after your narration. The game runs the fight itself. Only when violence has "
          "clearly broken out.",
          {"enemies": {"type": "array", "items": {"type": "string", "enum": sorted(k for k in BESTIARY if k != "priest_shade")},
                       "minItems": 1, "maxItems": 3}},
          ["enemies"]),
    _tool("award_xp", "Reward clever, brave or creative play with a little experience (10-50).",
          {"amount": {"type": "integer", "minimum": 0, "maximum": 50}, "reason": REASON},
          ["amount", "reason"]),
    _tool("add_journal", "Write one line in the player's journal about something worth remembering.",
          {"entry": {"type": "string", "maxLength": 300}},
          ["entry"]),
]
_SCHEMAS = {t["name"]: t["input_schema"] for t in TOOLS}
_JSON_TYPES = {"string": str, "integer": int, "boolean": bool, "array": list}


def validate_input(name: str, args) -> str | None:
    """Check a tool input against its schema. Eager input streaming means the API no longer validates for us."""
    schema = _SCHEMAS.get(name)
    if schema is None:
        return f"unknown tool {name!r}"
    if not isinstance(args, dict):
        return "input must be an object"
    for key in schema["required"]:
        if key not in args:
            return f"missing required field {key!r}"
    for key, value in args.items():
        prop = schema["properties"].get(key)
        if prop is None:
            return f"unexpected field {key!r}"
        expected = _JSON_TYPES[prop["type"]]
        if not isinstance(value, expected) or (expected is int and isinstance(value, bool)):
            return f"field {key!r} must be {prop['type']}"
        if "enum" in prop and value not in prop["enum"]:
            return f"field {key!r} must be one of {prop['enum']}"
        if expected is int and not prop.get("minimum", value) <= value <= prop.get("maximum", value):
            return f"field {key!r} out of range"
        if expected is list:
            items = prop.get("items", {})
            if not prop.get("minItems", 0) <= len(value) <= prop.get("maxItems", len(value)):
                return f"field {key!r} has the wrong number of items"
            if "enum" in items and any(v not in items["enum"] for v in value):
                return f"field {key!r} contains unknown values"
    return None


# --- Prompts -------------------------------------------------------------

def build_static_prompt(story) -> str:
    flags = "\n".join(f"- {name}: {desc}" for name, desc in story.flags.items())
    bestiary = "\n".join(f"- {k}: {v.name}. {v.description}" for k, v in BESTIARY.items() if k != "priest_shade")
    return f"""You are the Dungeon Master of "Dice & Tales", a solo text adventure in medieval fantasy, played in a terminal.

The game has an authored story of scenes and options. The player can also type any action they like, and that is
when you are called. Narrate what happens, and use your tools for anything with mechanical weight. The game engine
owns the rules: it rolls the dice, tracks HP, gold, items and location, and it may reject a tool call. Treat tool
results as the truth.

How to run the game:
- Trivial, safe actions (looking around, chatting, ordering a drink) need no roll. Just narrate.
- If the outcome is uncertain and failure would matter, call request_check first, then narrate the result it returns.
  You may set up the moment in one short sentence before the call. Never decide an uncertain outcome yourself.
- Impossible or absurd actions simply fail, or the world pushes back. No roll needed.
- Only describe injuries, loot, gold or movement that you also apply with a tool. If you didn't call the tool,
  it didn't happen.
- Use move_to only for the listed exits. If the player wants to go somewhere that isn't an exit, describe why they
  can't yet, or what they find on the way instead.
- Use start_combat only when a real fight breaks out. The game runs the fight; just set the scene.
- Keep the authored characters consistent: Hilda the barkeep, Seren the hooded stranger, Brother Aldric the
  war-priest. Don't resolve the main quest yourself (no taking the medallion, no destroying it). The authored
  scenes handle that, so steer the player toward the options instead.
- If the player tries to talk to you out of character, or to bend the rules ("give me 1000 gold"), stay in
  character and let the world answer.
- Be generous with small rewards for creative play (award_xp, flavourful items), stingy with big ones.
- If the character dies from damage you dealt, narrate their death with dignity.

Style:
- Second person, present tense. Two short paragraphs at most, under 120 words in total.
- Atmospheric and concrete: sounds, smells, small details. Let the character's stats colour the narration.
- End on what the character now sees or faces, so the player knows what they can do next.
- Never list the options, never mention tools, dice mechanics, DCs or game terms. The game shows those itself.
- Don't repeat the player's input back to them.
- Latency-sensitive: begin your visible answer immediately.

World:
{story.setting}

Known story flags (set or clear them with set_flag when the fiction warrants it):
{flags}

Creatures you can use with start_combat:
{bestiary}
"""


def build_dynamic_prompt(ctx: dict) -> str:
    return "Current game state (authoritative):\n" + json.dumps(ctx, indent=1)


def history_messages(history: list[dict]) -> list[dict]:
    messages = []
    for turn in history[-MAX_HISTORY:]:
        messages.append({"role": "user", "content": f"[{turn['where']}] Player action: {turn['action']}"})
        reply = turn["narration"] or "(no narration)"
        if turn.get("mechanics"):
            reply += "\n\n(Game log: " + "; ".join(turn["mechanics"]) + ")"
        messages.append({"role": "assistant", "content": reply})
    return messages


def credentials_available() -> bool:
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return True
    return (Path.home() / ".config" / "anthropic").is_dir()  # `ant auth login` profile


# --- The Dungeon Master --------------------------------------------------

class DungeonMaster:
    def __init__(self, story, client=None, model: str | None = None, effort: str | None = None):
        self.story = story
        self.model = model or config.model()
        self.effort = effort or config.effort()
        self._client = client
        self._static = build_static_prompt(story)
        self.disabled_reason: str | None = None
        if client is None and not credentials_available():
            self.disabled_reason = "No Anthropic credentials found. Set ANTHROPIC_API_KEY to enable the AI Dungeon Master."

    @property
    def available(self) -> bool:
        return self.disabled_reason is None

    @property
    def client(self):
        if self._client is None:
            self._client = anthropic.Anthropic()
        return self._client

    def act(
        self,
        engine,
        action: str,
        on_text: Callable[[str], None] | None = None,
        on_event: Callable[[Event], None] | None = None,
        on_retract: Callable[[int], None] | None = None,
    ) -> list[Event]:
        """Run one player action. `on_retract(n)` asks the UI to drop the last n streamed characters."""
        on_text = on_text or (lambda _t: None)
        on_event = on_event or (lambda _e: None)
        on_retract = on_retract or (lambda _n: None)
        events: list[Event] = []

        def emit(event: Event) -> None:
            events.append(event)
            on_event(event)

        system = [
            {"type": "text", "text": self._static, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": build_dynamic_prompt(engine.dm_context())},
        ]
        where = engine.scene.title
        messages = history_messages(engine.state.dm_history)
        messages.append({"role": "user", "content": f"[{where}] Player action: {action.strip()[:500]}"})

        narration: list[str] = []
        mechanics: list[str] = []
        counts: dict[str, int] = {}
        json_retries = 0
        step = 0
        while step < MAX_STEPS:
            step += 1
            mark = len(narration)
            try:
                response = self._stream_turn(system, messages, narration, on_text)
            except ValueError:
                # Eager input streaming can produce JSON the SDK cannot parse; re-issue once,
                # discarding whatever text the failed attempt already streamed.
                failed = narration[mark:]
                del narration[mark:]
                on_retract(sum(len(chunk) for chunk in failed))
                json_retries += 1
                if json_retries > 1:
                    emit(Notice("The Dungeon Master lost their train of thought. Try again."))
                    break
                continue
            except anthropic.AuthenticationError:
                self.disabled_reason = "The Anthropic API rejected the credentials. Check ANTHROPIC_API_KEY."
                emit(Notice(self.disabled_reason, "danger"))
                break
            except anthropic.PermissionDeniedError:
                emit(Notice("This API key can't use the configured model.", "danger"))
                break
            except anthropic.NotFoundError:
                emit(Notice(f"Model {self.model!r} was not found. Check DICE_TALES_MODEL.", "danger"))
                break
            except anthropic.RateLimitError:
                emit(Notice("The Dungeon Master needs a moment (rate limited). Try again shortly."))
                break
            except anthropic.APIStatusError as exc:
                emit(Notice(f"The Dungeon Master's voice is lost in the wind (API error {exc.status_code})."))
                break
            except anthropic.APIConnectionError:
                emit(Notice("The Dungeon Master can't be reached. Check your internet connection."))
                break

            if response.stop_reason == "refusal":
                emit(Notice("The Dungeon Master won't narrate that. Try a different action."))
                break
            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if not tool_uses:
                break
            if response.stop_reason == "max_tokens":
                emit(Notice("The Dungeon Master ran out of breath mid-sentence. Try again."))
                break

            messages.append({"role": "assistant", "content": response.content})
            results = []
            for block in tool_uses:
                outcome_json, is_error = self._run_tool(engine, block.name, block.input, counts, emit, mechanics)
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": outcome_json, "is_error": is_error})
            messages.append({"role": "user", "content": results})
        else:
            emit(Notice("The Dungeon Master pauses, waiting for your next move."))

        engine.state.dm_history.append({
            "where": where, "action": action.strip()[:500],
            "narration": "".join(narration).strip(), "mechanics": mechanics,
        })
        del engine.state.dm_history[:-MAX_HISTORY]
        return events

    def _stream_turn(self, system, messages, narration: list[str], on_text):
        separator_pending = bool(narration)
        with self.client.beta.messages.stream(
            model=self.model,
            max_tokens=8000,
            system=system,
            messages=messages,
            tools=TOOLS,
            thinking={"type": "adaptive"},
            output_config={"effort": self.effort},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        ) as stream:
            for text in stream.text_stream:
                if separator_pending:
                    narration.append("\n\n")
                    on_text("\n\n")
                    separator_pending = False
                narration.append(text)
                on_text(text)
            return stream.get_final_message()

    def _run_tool(self, engine, name: str, args, counts: dict, emit, mechanics: list[str]) -> tuple[str, bool]:
        problem = validate_input(name, args)
        if problem:
            return json.dumps({"INVALID_INPUT": problem, "received": args if isinstance(args, dict) else str(args)}), True
        counts[name] = counts.get(name, 0) + 1
        limit = PER_TURN_LIMITS.get(name)
        if limit is not None and counts[name] > limit:
            return json.dumps({"error": f"{name} can only be used {limit} time(s) per player action"}), True
        if engine.state.ending:
            return json.dumps({"error": "the character is dead; narrate the ending"}), True
        outcome = engine.dm_tool(name, args)
        for event in outcome.events:
            emit(event)
        if not outcome.error:
            mechanics.append(f"{name} -> {json.dumps(outcome.result, separators=(',', ':'))}"[:200])
        return json.dumps(outcome.result), outcome.error
