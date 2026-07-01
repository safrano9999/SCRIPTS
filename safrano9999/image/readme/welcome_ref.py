#!/usr/bin/env python3
"""Generate a value-free WELCOME variable reference from repository examples."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ASSIGNMENT = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=")
SECTIONS = (
    ("Environment", ("env*example",)),
    ("Configuration", ("config*example",)),
    ("Container", ("container*example", "config*.container")),
    ("Build", ("*build*example",)),
)


def collect(root: Path, patterns: tuple[str, ...], seen: set[str]) -> list[str]:
    names: list[str] = []
    files = sorted({path for pattern in patterns for path in root.glob(pattern) if path.is_file()})
    for path in files:
        secret = False
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line == "#secret":
                secret = True
                continue
            match = ASSIGNMENT.match(line)
            if match:
                name = match.group(1)
                if not secret and name not in seen:
                    seen.add(name)
                    names.append(name)
                secret = False
            elif not line:
                secret = False
    return names


def main() -> None:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    output = Path(sys.argv[2] if len(sys.argv) > 2 else root / "ref.conf")
    seen: set[str] = set()
    lines: list[str] = []
    for section, patterns in SECTIONS:
        lines.append(f"[{section}]")
        lines.extend(collect(root, patterns, seen))
        lines.append("")
    output.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"Written: {output}")


if __name__ == "__main__":
    main()
