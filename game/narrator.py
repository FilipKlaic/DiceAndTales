import os
import anthropic
from core.character import Character, stat_modifier


class Narrator:
    def __init__(self):
        self._client: anthropic.Anthropic | None = None
        self._history: list[dict] = []

    @property
    def available(self) -> bool:
        return bool(os.environ.get("ANTHROPIC_API_KEY"))

    def narrate(self, scene_description: str, character: Character, action: str) -> str:
        system = _build_system(character)
        messages = list(self._history[-6:])
        user_msg = f"Scene: {scene_description}\n\nI {action}"
        messages.append({"role": "user", "content": user_msg})

        parts: list[str] = []
        with self._get_client().messages.stream(
            model="claude-opus-4-8",
            max_tokens=400,
            thinking={"type": "adaptive"},
            system=system,
            messages=messages,
        ) as stream:
            for text in stream.text_stream:
                print(text, end="", flush=True)
                parts.append(text)
            print()

        narrative = "".join(parts)
        self._history.append({"role": "user", "content": user_msg})
        self._history.append({"role": "assistant", "content": narrative})
        return narrative

    def _get_client(self) -> anthropic.Anthropic:
        if self._client is None:
            self._client = anthropic.Anthropic()
        return self._client


def _build_system(character: Character) -> str:
    s = character.stats
    stats = (
        f"STR {s.strength} ({stat_modifier(s.strength):+d}), "
        f"DEX {s.dexterity} ({stat_modifier(s.dexterity):+d}), "
        f"CON {s.constitution} ({stat_modifier(s.constitution):+d}), "
        f"INT {s.intelligence} ({stat_modifier(s.intelligence):+d}), "
        f"WIS {s.wisdom} ({stat_modifier(s.wisdom):+d}), "
        f"CHA {s.charisma} ({stat_modifier(s.charisma):+d})"
    )
    return f"""You are the narrator of a DnD-style text adventure set in medieval fantasy.
The setting: The Rusty Flagon, a tavern on the edge of a quiet town, with a nearby ancient tomb rumored to hold treasure and danger.

Character: {character.name} ({character.race.value} {character.character_class.value})
HP: {character.current_hp}/{character.max_hp} | {stats}

When the player takes a freeform action, narrate what happens in 2-3 short paragraphs.
Be atmospheric — describe sights, sounds, and sensations. Reflect the character's stats where it makes sense.
End each response with what the character now sees or faces next.
Keep your response under 150 words. Do not repeat the player's input back to them."""
