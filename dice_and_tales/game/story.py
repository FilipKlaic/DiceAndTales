"""Story data model, TOML loader and validator."""

import tomllib
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from dice_and_tales.core import dice
from dice_and_tales.core.combat import BESTIARY
from dice_and_tales.core.rules import ABILITIES, DAMAGE_TYPES, ITEMS, SKILLS, CharacterClass, Race


class StoryError(ValueError):
    pass


@dataclass
class Condition:
    requires_flags: list[str] = field(default_factory=list)
    forbids_flags: list[str] = field(default_factory=list)
    requires_items: list[str] = field(default_factory=list)
    requires_class: str | None = None
    requires_race: str | None = None
    min_gold: int = 0

    @property
    def empty(self) -> bool:
        return not (self.requires_flags or self.forbids_flags or self.requires_items
                    or self.requires_class or self.requires_race or self.min_gold)


@dataclass
class Effects:
    set_flags: list[str] = field(default_factory=list)
    clear_flags: list[str] = field(default_factory=list)
    give_items: list[str] = field(default_factory=list)
    take_items: list[str] = field(default_factory=list)
    gold: int = 0
    xp: int = 0
    heal: str | None = None
    journal: str | None = None


@dataclass
class CheckSpec:
    ability: str
    dc: int
    success: str
    failure: str
    skill: str | None = None
    damage: str | None = None  # damage taken on failure
    damage_type: str = "bludgeoning"


@dataclass
class Encounter:
    enemies: list[str]
    victory: str | None = None
    flee: str | None = None


@dataclass
class Option:
    text: str
    goto: str | None = None
    check: CheckSpec | None = None
    encounter: Encounter | None = None
    condition: Condition = field(default_factory=Condition)
    effects: Effects = field(default_factory=Effects)


@dataclass
class TextVariant:
    text: str
    condition: Condition
    replace: bool = False


@dataclass
class Scene:
    id: str
    title: str
    text: str
    art: str | None = None
    options: list[Option] = field(default_factory=list)
    variants: list[TextVariant] = field(default_factory=list)
    check: CheckSpec | None = None
    encounter: Encounter | None = None
    on_enter: Effects = field(default_factory=Effects)
    safe: bool = False
    ending: str | None = None
    victory: bool = True

    @property
    def is_ending(self) -> bool:
        return self.ending is not None

    def targets(self) -> list[str]:
        out = []
        for spec in [self.check] + [o.check for o in self.options]:
            if spec:
                out += [spec.success, spec.failure]
        for enc in [self.encounter] + [o.encounter for o in self.options]:
            if enc:
                out += [t for t in (enc.victory, enc.flee) if t]
        out += [o.goto for o in self.options if o.goto]
        return out


@dataclass
class Story:
    title: str
    start: str
    setting: str
    scenes: dict[str, Scene]
    flags: dict[str, str]

    def __getitem__(self, scene_id: str) -> Scene:
        return self.scenes[scene_id]


# --- Parsing -------------------------------------------------------------

_CONDITION_KEYS = set(Condition.__dataclass_fields__)
_EFFECT_KEYS = set(Effects.__dataclass_fields__)


def _condition(raw: dict) -> Condition:
    return Condition(**{k: raw[k] for k in _CONDITION_KEYS if k in raw})


def _effects(raw: dict | None) -> Effects:
    raw = raw or {}
    unknown = set(raw) - _EFFECT_KEYS
    if unknown:
        raise StoryError(f"unknown effect keys {sorted(unknown)}")
    return Effects(**raw)


def _check(raw: dict | None) -> CheckSpec | None:
    return CheckSpec(**raw) if raw else None


def _encounter(raw: dict | None) -> Encounter | None:
    return Encounter(**raw) if raw else None


def _option(raw: dict) -> Option:
    allowed = {"text", "goto", "check", "encounter", "effects"} | _CONDITION_KEYS
    unknown = set(raw) - allowed
    if unknown:
        raise StoryError(f"option {raw.get('text')!r}: unknown keys {sorted(unknown)}")
    return Option(
        text=raw["text"],
        goto=raw.get("goto"),
        check=_check(raw.get("check")),
        encounter=_encounter(raw.get("encounter")),
        condition=_condition(raw),
        effects=_effects(raw.get("effects")),
    )


def _scene(scene_id: str, raw: dict) -> Scene:
    try:
        return Scene(
            id=scene_id,
            title=raw.get("title", scene_id.replace("_", " ").title()),
            text=raw["text"].strip(),
            art=raw.get("art"),
            options=[_option(o) for o in raw.get("options", [])],
            variants=[
                TextVariant(text=v["text"].strip(), condition=_condition(v), replace=v.get("replace", False))
                for v in raw.get("variants", [])
            ],
            check=_check(raw.get("check")),
            encounter=_encounter(raw.get("encounter")),
            on_enter=_effects(raw.get("on_enter")),
            safe=raw.get("safe", False),
            ending=raw.get("ending"),
            victory=raw.get("victory", True),
        )
    except (KeyError, TypeError) as exc:
        raise StoryError(f"scene {scene_id!r}: {exc}") from exc


def parse_story(data: dict) -> Story:
    meta = data.get("story", {})
    scenes = {sid: _scene(sid, raw) for sid, raw in data.get("scenes", {}).items()}
    story = Story(
        title=meta.get("title", "Untitled"),
        start=meta.get("start", ""),
        setting=meta.get("setting", "").strip(),
        scenes=scenes,
        flags=data.get("flags", {}),
    )
    problems = validate(story)
    if problems:
        raise StoryError("story failed validation:\n  " + "\n  ".join(problems))
    return story


def load_story(path: str | Path | None = None) -> Story:
    if path is None:
        text = resources.files("dice_and_tales.data").joinpath("story.toml").read_text(encoding="utf-8")
    else:
        text = Path(path).read_text(encoding="utf-8")
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise StoryError(f"story.toml is not valid TOML: {exc}") from exc
    return parse_story(data)


# --- Validation ----------------------------------------------------------

def _validate_condition(where: str, cond: Condition, flags: dict, problems: list[str]) -> None:
    for item in cond.requires_items:
        if item not in ITEMS:
            problems.append(f"{where}: unknown item {item!r}")
    if cond.requires_class and cond.requires_class not in CharacterClass.__members__:
        problems.append(f"{where}: unknown class {cond.requires_class!r}")
    if cond.requires_race and cond.requires_race not in Race.__members__:
        problems.append(f"{where}: unknown race {cond.requires_race!r}")
    for flag in cond.requires_flags + cond.forbids_flags:
        if flag not in flags:
            problems.append(f"{where}: flag {flag!r} is not declared in [flags]")


def _validate_effects(where: str, eff: Effects, flags: dict, problems: list[str]) -> None:
    for item in eff.give_items + eff.take_items:
        if item not in ITEMS:
            problems.append(f"{where}: unknown item {item!r}")
    for flag in eff.set_flags + eff.clear_flags:
        if flag not in flags:
            problems.append(f"{where}: flag {flag!r} is not declared in [flags]")
    if eff.heal:
        _validate_dice(where, eff.heal, problems)


def _validate_dice(where: str, expr: str, problems: list[str]) -> None:
    try:
        dice.parse(expr)
    except ValueError as exc:
        problems.append(f"{where}: {exc}")


def _validate_check(where: str, check: CheckSpec, problems: list[str]) -> None:
    if check.ability not in ABILITIES:
        problems.append(f"{where}: unknown ability {check.ability!r}")
    if check.skill and SKILLS.get(check.skill) is None:
        problems.append(f"{where}: unknown skill {check.skill!r}")
    elif check.skill and SKILLS[check.skill] != check.ability:
        problems.append(f"{where}: skill {check.skill!r} uses {SKILLS[check.skill]}, not {check.ability}")
    if not 5 <= check.dc <= 25:
        problems.append(f"{where}: DC {check.dc} out of range 5-25")
    if check.damage:
        _validate_dice(where, check.damage, problems)
    if check.damage_type not in DAMAGE_TYPES:
        problems.append(f"{where}: unknown damage type {check.damage_type!r}")


def validate(story: Story) -> list[str]:
    problems: list[str] = []
    if story.start not in story.scenes:
        problems.append(f"start scene {story.start!r} does not exist")

    for sid, scene in story.scenes.items():
        where = f"scene {sid!r}"
        for target in scene.targets():
            if target not in story.scenes:
                problems.append(f"{where}: links to missing scene {target!r}")
        actionable = scene.options or scene.check or scene.encounter
        if scene.is_ending and actionable:
            problems.append(f"{where}: endings cannot have options, checks or encounters")
        if not scene.is_ending and not actionable:
            problems.append(f"{where}: dead end (no options, check, encounter or ending)")
        if scene.check and scene.encounter:
            problems.append(f"{where}: a scene cannot have both a check and an encounter")
        if scene.check:
            _validate_check(where, scene.check, problems)
        for enc in [scene.encounter] + [o.encounter for o in scene.options]:
            if enc:
                if not enc.enemies:
                    problems.append(f"{where}: encounter with no enemies")
                for key in enc.enemies:
                    if key not in BESTIARY:
                        problems.append(f"{where}: unknown enemy {key!r}")
        _validate_effects(f"{where} on_enter", scene.on_enter, story.flags, problems)
        for variant in scene.variants:
            _validate_condition(f"{where} variant", variant.condition, story.flags, problems)
        for opt in scene.options:
            owhere = f"{where} option {opt.text!r}"
            kinds = sum(x is not None for x in (opt.goto, opt.check, opt.encounter))
            if kinds != 1:
                problems.append(f"{owhere}: needs exactly one of goto, check or encounter")
            if opt.check:
                _validate_check(owhere, opt.check, problems)
            _validate_condition(owhere, opt.condition, story.flags, problems)
            _validate_effects(owhere, opt.effects, story.flags, problems)

    reachable = _reachable(story)
    for sid in story.scenes:
        if sid not in reachable:
            problems.append(f"scene {sid!r} is unreachable from {story.start!r}")
    return problems


def _reachable(story: Story) -> set[str]:
    seen: set[str] = set()
    stack = [story.start] if story.start in story.scenes else []
    while stack:
        sid = stack.pop()
        if sid in seen:
            continue
        seen.add(sid)
        stack.extend(t for t in story.scenes[sid].targets() if t in story.scenes)
    return seen
