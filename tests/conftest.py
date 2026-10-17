import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from dice_and_tales.core import dice  # noqa: E402
from dice_and_tales.core.character import create_character  # noqa: E402
from dice_and_tales.core.rules import CharacterClass, Race  # noqa: E402
from dice_and_tales.game.engine import Engine  # noqa: E402
from dice_and_tales.game.story import load_story  # noqa: E402

AVERAGE = dict(strength=14, dexterity=14, constitution=14, intelligence=12, wisdom=12, charisma=10)


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Keep saves and settings out of the real home directory, and never hit the real API."""
    monkeypatch.setenv("DICE_TALES_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setattr("dice_and_tales.game.dm.credentials_available", lambda: False)
    dice.seed(1234)


@pytest.fixture(scope="session")
def story():
    return load_story()


def make_character(cls=CharacterClass.FIGHTER, race=Race.HUMAN, scores=None, name="Tester"):
    return create_character(name, cls, race, base_scores=dict(scores or AVERAGE))


@pytest.fixture
def engine(story):
    eng, _ = Engine.new_game(story, make_character(), seed=7)
    return eng
