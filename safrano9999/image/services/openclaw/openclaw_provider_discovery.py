#!/usr/bin/env python3
import json
import os
import subprocess
from pathlib import Path


def openclaw_json(*args: str) -> dict:
    result = subprocess.run(
        ["openclaw", *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        return {}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}


def main() -> None:
    status = openclaw_json("models", "status", "--json")
    auth_providers = status.get("auth", {}).get("providers", [])
    providers: set[str] = set()

    for key in os.environ:
        if not key.endswith("_API_KEY"):
            continue
        source = f"env: {key}"
        providers.update(
            entry["provider"]
            for entry in auth_providers
            if entry.get("env", {}).get("source") == source and entry.get("provider")
        )

    if os.environ.get("SAKANA_API_KEY"):
        providers.add("sakana")

    models: dict[str, dict] = {}
    for provider in sorted(providers):
        catalog = openclaw_json("models", "list", "--all", "--provider", provider, "--json")
        for model in catalog.get("models", []):
            if model.get("available") is True and model.get("missing") is False:
                models[model["key"]] = {}

    if models:
        subprocess.run(
            [
                "openclaw",
                "config",
                "set",
                "agents.defaults.models",
                json.dumps(models, separators=(",", ":")),
                "--strict-json",
                "--merge",
            ],
            check=True,
        )

    if Path("/named_volumes/CODEX_AUTH/auth.json").is_file():
        for model in ("5.5", "5.4", "5.4-mini"):
            subprocess.run(
                [
                    "openclaw",
                    "models",
                    "aliases",
                    "add",
                    f"codex-{model}",
                    f"openai/gpt-{model}",
                ],
                check=True,
            )

    print(f"Registered {len(models)} model(s) from: {', '.join(sorted(providers)) or 'none'}")


if __name__ == "__main__":
    main()
