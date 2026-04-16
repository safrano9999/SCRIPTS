#!/usr/bin/env python3
"""
Shared bare-metal installer — symlinked into every repo via ../SCRIPTS/install.py.

Reads from the repo it lives in:
  - requirements.txt  → dependency check + install
  - env_example        → env var prompts + .env generation (SOT)
  - provider_example   → provider API keys template (symlink from SCRIPTS)

Detects LiteLLM (OPENAI_API_BASE in env_example) → sdk/proxy dialog + autodiscovery.
  - proxy: autodiscovery via openai lib, keys in .env
  - sdk: provider keys from provider_example → provider.env
Detects Database (DB_HOST in env_example) → optional DB bootstrap.
"""

import sys
from collections import OrderedDict
from pathlib import Path

# install/ package is next to this file in SCRIPTS/
sys.path.insert(0, str(Path(__file__).resolve().parent))

from install.deps import parse_requirements, show_status, ask_install_method, install
from install.env import parse_env_example, run_dialog as env_dialog, write_env
from install.llm import run_dialog as llm_dialog
from install.db import needs_db, bootstrap

HERE = Path(__file__).resolve().parent


def main() -> int:
    name = HERE.name
    print(f"=== Installer: {name} ===")

    # 1. Dependencies
    pkgs = parse_requirements(HERE)
    missing = show_status(pkgs)
    if missing:
        method = ask_install_method()
        install(method, HERE, missing)

    # 2. Parse env_example (SOT)
    entries = parse_env_example(HERE)
    if not entries:
        print("\n  Keine env_example — überspringe Konfiguration.")
        print("\n\u2705 Fertig.")
        return 0

    # 3. LiteLLM setup (if OPENAI_API_BASE in env_example)
    has_llm = any(e["key"] == "OPENAI_API_BASE" for e in entries)
    llm_mode = ""
    llm_env: OrderedDict[str, str] = OrderedDict()
    if has_llm:
        llm_mode, llm_env, _provider_env = llm_dialog(entries, repo_dir=HERE)

    # 4. Remaining env vars
    mod_env = env_dialog(entries, llm_mode=llm_mode, llm_env=llm_env)

    # 5. Merge (only app env, provider keys are in provider.env)
    all_env: OrderedDict[str, str] = OrderedDict()
    all_env.update(llm_env)
    all_env.update(mod_env)

    # 6. Summary + write
    if all_env:
        print("\n=== Zusammenfassung ===")
        for k, v in all_env.items():
            display = v[:8] + "..." if ("KEY" in k or "PASSWORD" in k.upper()) and v else v
            print(f"  {k}={display}")

        yn = input("\nIn .env schreiben? [Y/n]: ").strip().lower()
        if yn in ("", "y", "yes"):
            env_file = write_env(HERE, all_env)
            print(f"  Geschrieben: {env_file}")

    # 7. DB bootstrap (if DB_HOST in .env_example)
    if needs_db(entries):
        bootstrap(HERE, all_env)

    print("\n\u2705 Fertig.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
