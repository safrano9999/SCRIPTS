"""Parse .env_example (SOT) and generate .env files."""

from collections import OrderedDict
from pathlib import Path

from .helpers import ask_text, ask_secret


def parse_env_example(repo_dir: Path) -> list[dict]:
    """Parse .env_example into structured entries.

    Format:
      # Description for next line
      KEY=default           → active, will be prompted
      # KEY=default         → optional (commented out), offered but skippable
    """
    path = repo_dir / "env_example"
    if not path.exists():
        return []

    entries = []
    comment_buf = ""
    for raw in path.read_text().splitlines():
        line = raw.strip()

        if not line:
            comment_buf = ""
            continue

        # Pure comment line (no =)
        if line.startswith("#") and "=" not in line:
            comment_buf = line.lstrip("#").strip()
            continue

        # Commented-out var: # KEY=value
        if line.startswith("#") and "=" in line:
            rest = line.lstrip("#").strip()
            key, _, val = rest.partition("=")
            entries.append({
                "key": key.strip(), "default": val.strip(),
                "description": comment_buf, "optional": True,
            })
            comment_buf = ""
            continue

        # Active var: KEY=value
        if "=" in line:
            key, _, val = line.partition("=")
            entries.append({
                "key": key.strip(), "default": val.strip(),
                "description": comment_buf, "optional": False,
            })
            comment_buf = ""

    return entries


def load_existing_env(repo_dir: Path) -> OrderedDict[str, str]:
    """Load existing .env if present."""
    env_file = repo_dir / ".env"
    out: OrderedDict[str, str] = OrderedDict()
    if not env_file.exists():
        return out
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip()
    return out


def run_dialog(entries: list[dict], llm_mode: str = "",
               llm_env: OrderedDict[str, str] | None = None) -> OrderedDict[str, str]:
    """Prompt user for env vars from .env_example entries.

    Args:
        entries: parsed .env_example
        llm_mode: 'proxy' or 'sdk' (to skip irrelevant keys)
        llm_env: already-collected LLM env vars (skip these)
    """
    llm_env = llm_env or OrderedDict()
    env_out: OrderedDict[str, str] = OrderedDict()

    print("\n=== Konfiguration ===")
    for entry in entries:
        key = entry["key"]

        # Already set by LLM dialog
        if key in llm_env:
            continue

        # In proxy mode skip provider keys (handled by proxy)
        if llm_mode == "proxy" and key.endswith("_API_KEY") and key != "OPENAI_API_KEY":
            continue

        # In sdk mode provider keys were handled by llm dialog
        if llm_mode == "sdk" and key.endswith("_API_KEY"):
            continue

        # Skip LLM vars handled elsewhere
        if key in ("OPENAI_API_BASE", "LITELLM_MODE", "DEFAULT_MODEL", "OLLAMA_API_BASE"):
            continue

        desc = entry.get("description", "") or ""
        label = f"{desc} ({key})" if desc and desc != key else key
        is_secret = "KEY" in key or "PASSWORD" in key.upper()

        if entry["optional"]:
            yn = input(f"  {label} [optional] konfigurieren? [y/N]: ").strip().lower()
            if yn not in ("y", "yes"):
                continue

        if is_secret:
            val = ask_secret(f"  {label}", entry["default"])
        else:
            val = ask_text(f"  {label}", entry["default"])

        env_out[key] = val

    return env_out


def write_env(repo_dir: Path, env_values: OrderedDict[str, str]) -> Path:
    """Write .env, merging with existing values."""
    env_file = repo_dir / ".env"
    existing = load_existing_env(repo_dir)
    merged = OrderedDict(existing)
    merged.update(env_values)

    env_file.write_text(
        "\n".join(f"{k}={v}" for k, v in merged.items()) + "\n"
    )
    return env_file
