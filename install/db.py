"""Database bootstrap — schema creation for repos that need it."""

import subprocess
import sys
from collections import OrderedDict
from pathlib import Path


def needs_db(env_entries: list[dict]) -> bool:
    """Check if .env_example defines DB_HOST → this repo needs a database."""
    return any(e["key"] == "DB_HOST" for e in env_entries)


def bootstrap(repo_dir: Path, env_values: OrderedDict[str, str]) -> None:
    """Try to bootstrap DB schema if the repo has a db.py with build_table/ensure_schema."""
    db_module = repo_dir / "db.py"
    if not db_module.exists():
        return

    # Determine python binary (prefer venv if exists)
    venv_python = repo_dir / "venv" / "bin" / "python"
    python_bin = str(venv_python) if venv_python.exists() else sys.executable

    # Inject env vars for the subprocess
    import os
    run_env = os.environ.copy()
    run_env.update(env_values)

    print("\n=== Datenbank ===")
    yn = input("  DB-Schema initialisieren? [Y/n]: ").strip().lower()
    if yn not in ("", "y", "yes"):
        return

    code = (
        "from db import build_table, db_healthcheck, ensure_schema\n"
        "from sqlalchemy import MetaData\n"
        "import shared\n"
        "db_cfg = shared.load_env()\n"
        "engine = shared.get_engine(db_cfg)\n"
        "db_healthcheck(engine)\n"
        "metadata = MetaData()\n"
        "build_table(metadata)\n"
        "ensure_schema(engine, metadata)\n"
        "print('  \\u2705 DB-Schema initialisiert')\n"
    )

    try:
        subprocess.run(
            [python_bin, "-c", code],
            cwd=str(repo_dir), env=run_env, check=True,
        )
    except subprocess.CalledProcessError:
        print("  \u26a0\ufe0f  DB-Bootstrap fehlgeschlagen — ggf. DB nicht erreichbar.")
    except FileNotFoundError:
        print(f"  \u26a0\ufe0f  Python nicht gefunden: {python_bin}")
