"""Dependency checking and installation."""

import json
import subprocess
import sys
from pathlib import Path


def _pip_installed() -> set[str]:
    try:
        out = subprocess.check_output(
            [sys.executable, "-m", "pip", "list", "--format=json"],
            stderr=subprocess.DEVNULL, text=True,
        )
        return {p["name"].lower().replace("-", "_") for p in json.loads(out)}
    except Exception:
        return set()


def _pkg_base(spec: str) -> str:
    """'flask>=3.0' → 'flask', 'psycopg[binary]' → 'psycopg'."""
    for ch in ">=<![;":
        spec = spec.split(ch)[0]
    return spec.strip().lower().replace("-", "_")


def parse_requirements(repo_dir: Path) -> list[str]:
    req = repo_dir / "requirements.txt"
    if not req.exists():
        return []
    return [l.strip() for l in req.read_text().splitlines()
            if l.strip() and not l.startswith("#")]


def check_status(pkgs: list[str]) -> tuple[list[str], list[str]]:
    """Returns (installed, missing) package specs."""
    installed_set = _pip_installed()
    installed = []
    missing = []
    for pkg in pkgs:
        if _pkg_base(pkg) in installed_set:
            installed.append(pkg)
        else:
            missing.append(pkg)
    return installed, missing


def show_status(pkgs: list[str]) -> list[str]:
    """Print status and return missing packages."""
    if not pkgs:
        print("\n  Keine requirements.txt gefunden.")
        return []

    print("\n=== Python Dependencies ===")
    installed, missing = check_status(pkgs)
    for pkg in installed:
        print(f"  \u2705 {pkg}")
    for pkg in missing:
        print(f"  \u26a0\ufe0f  {pkg}")

    if not missing:
        print("\n  Alles installiert.")
    else:
        print(f"\n  {len(missing)} fehlend.")
    return missing


def ask_install_method() -> int:
    from .helpers import ask_choice
    return ask_choice("Wie installieren?", [
        "pip install --user",
        "pip install --break-system-packages",
        "venv (virtualenv anlegen)",
        "dnf install (python3-<name>)",
        "Überspringen",
    ])


def install(method: int, repo_dir: Path, missing: list[str]) -> None:
    req = repo_dir / "requirements.txt"

    if method == 4:  # skip
        return

    if method == 2:  # venv
        venv_dir = repo_dir / "venv"
        print(f"\n  Erstelle venv: {venv_dir}")
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
        pip_bin = str(venv_dir / "bin" / "pip")
        cmd = [pip_bin, "install", "-r", str(req)]
        print(f"  Aktivieren mit: source {venv_dir}/bin/activate\n")
    elif method == 3:  # dnf
        dnf_pkgs = [f"python3-{_pkg_base(p)}" for p in missing]
        cmd = ["sudo", "dnf", "install", "-y"] + dnf_pkgs
        print("  Hinweis: Nicht alle Pakete sind über dnf verfügbar.\n")
    elif method == 1:  # break-system-packages
        cmd = [sys.executable, "-m", "pip", "install",
               "--break-system-packages", "-r", str(req)]
    else:  # pip --user
        cmd = [sys.executable, "-m", "pip", "install", "--user", "-r", str(req)]

    print(f"  $ {' '.join(cmd)}\n")
    subprocess.run(cmd)
