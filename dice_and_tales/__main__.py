"""Entry point: `python -m dice_and_tales` or the `dice-and-tales` command."""

import argparse
import sys

from dice_and_tales import __version__


def main() -> None:
    parser = argparse.ArgumentParser(prog="dice-and-tales", description="A terminal adventure with an AI Dungeon Master.")
    parser.add_argument("--story", help="path to an alternative story.toml")
    parser.add_argument("--check-story", action="store_true", help="validate the story file and exit")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args()

    from dice_and_tales.game.story import StoryError, load_story

    try:
        story = load_story(args.story)
    except (StoryError, OSError) as exc:
        sys.exit(f"Could not load story: {exc}")
    if args.check_story:
        print(f"OK: '{story.title}', {len(story.scenes)} scenes.")
        return

    from dice_and_tales.ui.app import DiceAndTalesApp

    DiceAndTalesApp(story=story).run()


if __name__ == "__main__":
    main()
