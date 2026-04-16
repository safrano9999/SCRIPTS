"""Shared helpers for the install system."""

import getpass


def ask_choice(question: str, options: list[str]) -> int:
    print(f"\n{question}")
    for i, opt in enumerate(options, 1):
        print(f"  {i}) {opt}")
    while True:
        choice = input(f"[1-{len(options)}]: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(options):
            return int(choice) - 1
        print("Ungültige Eingabe.")


def ask_text(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"{prompt}{suffix}: ").strip()
    return val if val else default


def ask_secret(prompt: str, default: str = "") -> str:
    suffix = f" [{default[:4]}...]" if default else ""
    val = getpass.getpass(f"{prompt}{suffix}: ").strip()
    return val if val else default
