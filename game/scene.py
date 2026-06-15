from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Check:
    stat: str
    dc: int
    success_scene: str
    fail_scene: str
    description: str
    combat: bool = False


@dataclass
class Scene:
    description: str
    options: dict
    check: Optional[Check] = None
    is_terminal: bool = False
