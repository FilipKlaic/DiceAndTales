"""Runtime configuration: environment overrides plus a small persisted settings file."""

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_EFFORT = "low"  # narration is latency-sensitive; raise via DICE_TALES_EFFORT
EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")
TEXT_SPEEDS = {"slow": 0.03, "normal": 0.012, "fast": 0.004, "instant": 0.0}


def home_dir() -> Path:
    return Path(os.environ.get("DICE_TALES_HOME", Path.home() / ".dice_and_tales"))


def model() -> str:
    return os.environ.get("DICE_TALES_MODEL", DEFAULT_MODEL)


def effort() -> str:
    value = os.environ.get("DICE_TALES_EFFORT", DEFAULT_EFFORT)
    return value if value in EFFORT_LEVELS else DEFAULT_EFFORT


@dataclass
class Settings:
    text_speed: str = "normal"
    dm_enabled: bool = True
    animations: bool = True

    @property
    def char_delay(self) -> float:
        return TEXT_SPEEDS.get(self.text_speed, TEXT_SPEEDS["normal"])

    @classmethod
    def load(cls) -> "Settings":
        path = home_dir() / "settings.json"
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            return cls()
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        settings = cls(**known)
        if settings.text_speed not in TEXT_SPEEDS:
            settings.text_speed = "normal"
        return settings

    def save(self) -> None:
        path = home_dir() / "settings.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2))
