#!/usr/bin/env python3
"""Configure OpenClaw before starting the gateway."""

import json
import os
import subprocess
from pathlib import Path

from openclaw_common import (
    configure_gateway,
    configure_openai_v1_providers,
    configure_telegram_main,
    env_ref,
    ensure_main_agent,
)


CONFIG_PATH = Path(os.environ.get("OPENCLAW_CONFIG", "/root/.openclaw/openclaw.json"))
DEFAULT_MODEL = "gemini/gemini-3.5-flash"
OPENCLAW_GATEWAY_INTERNAL_PORT = int(os.environ.get("OPENCLAW_GATEWAY_PORT", "18789") or "18789")
OPENCLAW_GATEWAY_HOST_PORT = int(os.environ.get("OPENCLAW_GATEWAY_PUBLISH_PORT", "20789") or "20789")
VIKAI_BOOTSTRAP_SCRIPT = Path("/usr/local/bin/vikai-bootstrap-openclaw-agents")
VIKAI_TOKEN_ENV = ("TOKEN_WORKER", "TOKEN_ARCHITECT", "TOKEN_QC")


def _ensure_openclaw_config() -> None:
    if CONFIG_PATH.exists() and CONFIG_PATH.stat().st_size > 0:
        return

    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text("{}\n", encoding="utf-8")


def _maybe_bootstrap_vikai_agents() -> bool:
    present = [name for name in VIKAI_TOKEN_ENV if os.environ.get(name, "").strip()]
    if not present:
        return False
    missing = [name for name in VIKAI_TOKEN_ENV if name not in present]
    if missing:
        raise SystemExit(
            "VikAI agent bootstrap requires TOKEN_WORKER, TOKEN_ARCHITECT, "
            f"and TOKEN_QC; missing: {', '.join(missing)}"
        )
    subprocess.run([str(VIKAI_BOOTSTRAP_SCRIPT)], check=True)
    return True


def _configure_brave(config: dict) -> bool:
    brave_api_key = os.environ.get("BRAVE_API_KEY", "").strip()
    if not brave_api_key:
        return False

    web_search = config.setdefault("tools", {}).setdefault("web", {}).setdefault("search", {})
    web_search["enabled"] = True
    web_search["provider"] = "brave"

    brave_web_search = (
        config.setdefault("plugins", {})
        .setdefault("entries", {})
        .setdefault("brave", {})
        .setdefault("config", {})
        .setdefault("webSearch", {})
    )
    brave_web_search["apiKey"] = env_ref("BRAVE_API_KEY")
    return True


def _enable_codex_harness(config: dict) -> None:
    config.setdefault("plugins", {}).setdefault("entries", {}).setdefault("codex", {})["enabled"] = True


def main() -> None:
    _ensure_openclaw_config()

    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    ensure_main_agent(
        config,
        config_path=CONFIG_PATH,
        set_agent_dir=True,
        mark_default=True,
        heartbeat={"every": "360m", "target": "last", "directPolicy": "allow"},
    )
    origins = configure_gateway(
        config,
        port=OPENCLAW_GATEWAY_INTERNAL_PORT,
        host_port=OPENCLAW_GATEWAY_HOST_PORT,
        include_tailscale_origins=True,
    )
    openai_v1 = configure_openai_v1_providers(config, default_model=DEFAULT_MODEL)
    telegram_configured = configure_telegram_main(
        config,
        include_binding=True,
        owner_allow=True,
    )
    _enable_codex_harness(config)
    brave_configured = _configure_brave(config)

    CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    vikai_bootstrapped = _maybe_bootstrap_vikai_agents()

    print(f"OpenClaw OpenAI v1 model configured: {openai_v1['full_model']}")
    print(f"OpenClaw OpenAI v1 providers configured: {openai_v1['provider_count']}")
    if openai_v1["discovered"]:
        print(
            "OpenClaw OpenAI v1 models discovered: "
            f"{openai_v1['discovered_count']}; models written: {openai_v1['written_count']}"
        )
    if telegram_configured:
        print("OpenClaw Telegram configured for default account -> main agent")
        print("OpenClaw Telegram command owners allowed for all Telegram senders")
    if brave_configured:
        print("OpenClaw Brave web search configured from BRAVE_API_KEY")
    print("OpenClaw Codex harness plugin enabled")
    print("OpenClaw Control UI origins configured: " + ", ".join(origins))
    if vikai_bootstrapped:
        print("OpenClaw VikAI agents configured from TOKEN_WORKER/TOKEN_ARCHITECT/TOKEN_QC")


if __name__ == "__main__":
    main()
