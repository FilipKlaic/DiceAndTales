def get_choice(options: dict) -> str:
    while True:
        user_input = input("> ").strip().lower()
        if user_input in options:
            return user_input
        if user_input == "stats":
            return "stats"
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
