"""LiteLLM setup — sdk/proxy detection, autodiscovery, model selection."""

from collections import OrderedDict
from pathlib import Path

from .helpers import ask_choice, ask_text, ask_secret


SCRIPTS_DIR = Path(__file__).resolve().parent.parent


def discover_models(base_url: str, api_key: str = "") -> list[str]:
    """Fetch available models from an OpenAI-compatible endpoint via openai lib."""
    try:
        from openai import OpenAI
        client = OpenAI(base_url=base_url, api_key=api_key or "none", timeout=5)
        return sorted(m.id for m in client.models.list())
    except ImportError:
        print("  openai lib nicht installiert — überspringe Autodiscovery.")
        return []
    except Exception as e:
        print(f"  Autodiscovery fehlgeschlagen: {e}")
        return []


def parse_provider_example() -> list[dict]:
    """Parse provider_example from SCRIPTS for provider key entries."""
    path = SCRIPTS_DIR / "provider_example"
    if not path.exists():
        return []

    entries = []
    comment_buf = ""
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line:
            comment_buf = ""
            continue
        if line.startswith("#") and "=" not in line:
            comment_buf = line.lstrip("#").strip()
            continue
        if line.startswith("#") and "=" in line:
            rest = line.lstrip("#").strip()
            key, _, val = rest.partition("=")
            entries.append({"key": key.strip(), "default": val.strip(),
                            "description": comment_buf})
            comment_buf = ""
            continue
        if "=" in line:
            key, _, val = line.partition("=")
            entries.append({"key": key.strip(), "default": val.strip(),
                            "description": comment_buf})
            comment_buf = ""
    return entries


def write_provider_env(repo_dir: Path, env_values: OrderedDict[str, str]) -> Path:
    """Write provider.env with the collected provider keys."""
    path = repo_dir / "provider.env"
    lines = [f"{k}={v}" for k, v in env_values.items() if v]
    path.write_text("\n".join(lines) + "\n" if lines else "")
    return path


def run_dialog(env_entries: list[dict], repo_dir: Path | None = None,
               ) -> tuple[str, OrderedDict[str, str], OrderedDict[str, str]]:
    """Run LiteLLM setup dialog.

    Args:
        env_entries: parsed env_example entries
        repo_dir: repo directory (for writing provider.env in sdk mode)

    Returns:
        (mode, app_env, provider_env)
        - app_env: goes into .env (OPENAI_API_BASE, DEFAULT_MODEL, etc.)
        - provider_env: goes into provider.env (API keys, sdk mode only)
    """
    print("\n=== LiteLLM Setup ===")
    mode_idx = ask_choice("LiteLLM Modus?", [
        "proxy  — externer OpenAI-kompatibler Endpunkt",
        "sdk    — lokales LiteLLM, direkte Provider-Keys",
    ])
    mode = "proxy" if mode_idx == 0 else "sdk"
    app_env: OrderedDict[str, str] = OrderedDict()
    provider_env: OrderedDict[str, str] = OrderedDict()

    if mode == "proxy":
        base_url = ask_text("OPENAI_API_BASE", "http://127.0.0.1:4000/v1")
        api_key = ask_secret("OPENAI_API_KEY (Bearer)")
        app_env["OPENAI_API_BASE"] = base_url
        if api_key:
            app_env["OPENAI_API_KEY"] = api_key
        app_env["LITELLM_MODE"] = "external"

        # Autodiscovery via openai lib
        print("\n  Suche Modelle...")
        models = discover_models(base_url, api_key)
        if models:
            print(f"  {len(models)} Modell(e) gefunden:")
            for i, m in enumerate(models[:25], 1):
                print(f"    {i}) {m}")
            default_model = models[0]
        else:
            default_model = "openai/gpt-5.4"
        app_env["DEFAULT_MODEL"] = ask_text("DEFAULT_MODEL", default_model)

    else:
        app_env["LITELLM_MODE"] = "local"

        # Read provider keys from provider_example (SCRIPTS)
        providers = parse_provider_example()
        if providers:
            print("\n  Provider API Keys (leer lassen zum Überspringen):")
            for entry in providers:
                key = entry["key"]
                desc = entry.get("description", "") or key
                default = entry.get("default", "")

                if key == "OLLAMA_API_BASE":
                    val = ask_text(f"  {desc} ({key})", default)
                    if val:
                        provider_env[key] = val
                elif key.endswith("_API_KEY"):
                    val = ask_secret(f"  {desc} ({key})")
                    if val:
                        provider_env[key] = val

        app_env["DEFAULT_MODEL"] = ask_text("DEFAULT_MODEL", "openai/gpt-5.4")

        # Write provider.env
        if repo_dir and provider_env:
            pf = write_provider_env(repo_dir, provider_env)
            print(f"\n  Provider-Keys geschrieben: {pf}")

    return mode, app_env, provider_env
