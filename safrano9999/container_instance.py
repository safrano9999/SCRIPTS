#!/usr/bin/env python3
import argparse
import re
import sys
from pathlib import Path

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
FILES = (
    "{name}.env",
    "{name}_config.conf",
    "{name}_container.conf",
    "{name}-compose.yml",
    "{name}.container",
)


def read_nr(path):
    if path.is_file():
        for raw in path.read_text().splitlines():
            line = raw.split("#", 1)[0].strip()
            if line.startswith("CONTAINER_NR="):
                return line.split("=", 1)[1].strip()
    return ""


def mode(path):
    value = read_nr(path)
    if value.lower() in {"", "blank", "manual"}:
        return None
    if value.upper() == "TUN":
        return "TUN"
    if value.isdigit() and 2 <= int(value) <= 5:
        return int(value)
    raise SystemExit(f"Invalid CONTAINER_NR={value!r} in {path}")


def write_nr(path, value):
    lines = path.read_text().splitlines() if path.is_file() else []
    replacement = f"CONTAINER_NR={value or ''}"
    output = []
    for line in lines:
        if line.split("=", 1)[0].strip() == "CONTAINER_NR":
            if replacement:
                output.append(replacement)
                replacement = ""
        else:
            output.append(line)
    if replacement:
        if output and output[-1]:
            output.append("")
        output.append(replacement)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(output) + "\n")


def label(value):
    if isinstance(value, int):
        return f"Portrange {value * 10000} - {(value + 1) * 10000 - 1}"
    return value or "manual"


def ask(prompt):
    print(prompt, end="", file=sys.stderr, flush=True)
    return sys.stdin.readline().strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", type=Path)
    parser.add_argument("--name", default="")
    args = parser.parse_args()
    repo = args.repo.resolve()
    instances = repo / "CONTAINER"
    instances.mkdir(parents=True, exist_ok=True)

    for source in repo.glob("*_config.conf"):
        old_name = source.name.removesuffix("_config.conf")
        if not NAME_RE.fullmatch(old_name):
            continue
        target = instances / old_name
        target.mkdir(parents=True, exist_ok=True)
        for pattern in FILES:
            old = repo / pattern.format(name=old_name)
            new = target / old.name
            if old.exists() and not new.exists():
                old.replace(new)

    names = sorted(path.name for path in instances.iterdir() if path.is_dir())
    modes = {
        candidate: mode(instances / candidate / f"{candidate}_container.conf")
        for candidate in names
    }
    highest = max((value for value in modes.values() if isinstance(value, int)), default=1)
    next_nr = highest + 1 if highest < 5 else None

    name = args.name
    is_new = bool(name and name not in names)
    default_name = names[0] if names else ""
    if not name and not sys.stdin.isatty():
        if not default_name:
            raise SystemExit("No container exists; pass INSTANCE")
        name, is_new = default_name, False
    elif not name:
        if not names:
            name, is_new = ask("  New container name: "), True
        else:
            new_index = len(names) + 1
            default_index = names.index(default_name) + 1
            print("\n  Container:", file=sys.stderr)
            for index, candidate in enumerate(names, 1):
                print(f"    ({index}) {candidate} ({label(modes[candidate])})", file=sys.stderr)
            print(f"    ({new_index}) new\n", file=sys.stderr)
            choice = ask(f"  Choose [1-{new_index}] (default: {default_index}): ") or str(default_index)
            if choice == str(new_index):
                name, is_new = ask("  New container name: "), True
                if name in names:
                    raise SystemExit(f"Container already exists: {name}")
            elif choice.isdigit() and 1 <= int(choice) <= len(names):
                name = names[int(choice) - 1]
                is_new = False
            else:
                raise SystemExit(f"Invalid container choice: {choice}")

    if not NAME_RE.fullmatch(name):
        raise SystemExit(f"Invalid container name: {name}")
    directory = instances / name
    directory.mkdir(parents=True, exist_ok=True)
    config = directory / f"{name}_container.conf"
    current = mode(config)

    if is_new:
        current = "TUN"
    if is_new and sys.stdin.isatty():
        used = {
            selected: candidate for candidate, selected in modes.items() if isinstance(selected, int)
        }
        options = ["TUN"] + ([next_nr] if next_nr else [])
        options += [number for number in range(2, 6) if number != next_nr] + [None]
        print("\n  Publish ports:", file=sys.stderr)
        for index, option in enumerate(options, 1):
            suffix = " (default)" if option == "TUN" else ""
            if option == next_nr:
                suffix = " (next: +1)"
            elif option in used:
                suffix = f" (used: {used[option]})"
            print(f"    ({index}) {label(option)}{suffix}", file=sys.stderr)
        choice = ask(f"\n  Choose [1-{len(options)}] (default: 1): ") or "1"
        if not choice.isdigit() or not 1 <= int(choice) <= len(options):
            raise SystemExit(f"Invalid publish-port choice: {choice}")
        current = options[int(choice) - 1]
        if current in used:
            raise SystemExit(f"CONTAINER_NR={current} is already used by {used[current]}")

    write_nr(config, current)
    print(name)


if __name__ == "__main__":
    main()
