def get_choice(options: dict, freeform: bool = False) -> str:
    while True:
        raw = input("> ").strip()
        lowered = raw.lower()
        if lowered in options:
            return lowered
        if lowered == "stats":
            return "stats"
        if freeform and raw:
            return raw
        print("  Invalid choice. Try one of the options above.")


def get_text(prompt: str) -> str:
    print(prompt)
    return input("> ").strip()


def get_numbered_choice(options: list[str]) -> str:
    for i, option in enumerate(options, 1):
        print(f"  {i}. {option}")
    while True:
        user_input = input("> ").strip()
        if user_input.isdigit():
            idx = int(user_input) - 1
            if 0 <= idx < len(options):
                return options[idx]
        print(f"  Enter a number between 1 and {len(options)}.")
