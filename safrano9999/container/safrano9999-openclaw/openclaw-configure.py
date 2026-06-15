#!/usr/bin/env python3
"""Configure OpenClaw for the safcontainer plugin gateway."""

import json
import os
from pathlib import Path

from openclaw_common import (
    configure_gateway,
    configure_telegram_main,
    ensure_main_agent,
    openclaw_cmd,
    refresh_plugin_registry,
)
from safrano9999_plugins import (
    disable_plugin_command_auth,
    register_openclaw_plugins,
)


CONFIG_PATH = Path(os.environ.get("OPENCLAW_CONFIG", "/root/.openclaw/openclaw.json"))
GATEWAY_PORT = int(os.environ.get("OPENCLAW_GATEWAY_PORT", "18789") or "18789")
PLUGINS_DIR = Path(os.environ.get("OPENCLAW_PLUGINS_DIR", "/opt/safrano9999-openclaw"))

CONTAINER_ONLY_COMMAND_ALIASES = {
    "ZEROINBOX": ("zeroinbox", "mails"),
    "KACHELMANN": ("kachelmann", "routines"),
}

CONTAINER_ONLY_ALIAS_BLOCKS = {
    "ZEROINBOX": """    api.registerCommand({
      name: "mails",
      description: "Alias for /zeroinbox in this container.",
      acceptsArgs: true,
      requireAuth: false,
      handler: async (ctx) => {
        const raw = readString(ctx?.args) ?? "";
        return runZeroinboxCommand(api, raw);
      },
    });
""",
    "KACHELMANN": """    api.registerCommand({
      name: "routines",
      description: "Alias for /kachelmann in this container.",
      acceptsArgs: true,
      requireAuth: false,
      handler: async (ctx) => {
        const raw = ctx.args ?? "";
        if (["status", "reminder"].includes(raw.trim().toLowerCase())) {
          return { text: await runKachelmannStatus(api) };
        }
        return createKachelmannReply(await runKachelmann(api, { raw }));
      },
    });
""",
}


def _ensure_openclaw_config() -> None:
    if CONFIG_PATH.exists() and CONFIG_PATH.stat().st_size > 0:
        return
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    os.environ["OPENCLAW_BIN"] = " ".join(openclaw_cmd())
    command = openclaw_cmd(
        "onboard",
        "--non-interactive",
        "--accept-risk",
        "--skip-health",
        "--auth-choice",
        "skip",
        "--skip-daemon",
        "--skip-search",
        "--gateway-auth",
        "token",
        "--gateway-token-ref-env",
        "OPENCLAW_GATEWAY_TOKEN",
        "--gateway-bind",
        "lan",
        "--gateway-port",
        str(GATEWAY_PORT),
        "--suppress-gateway-token-output",
    )
    import subprocess

    subprocess.run(command, check=True)


def _apply_container_only_command_aliases() -> None:
    for repo, (command_name, alias) in CONTAINER_ONLY_COMMAND_ALIASES.items():
        plugin_id = command_name
        candidates = (
            PLUGINS_DIR / repo / "index.js",
            CONFIG_PATH.parent / "extensions" / plugin_id / "index.js",
        )
        for plugin_file in candidates:
            if not plugin_file.exists():
                continue
            source = plugin_file.read_text(encoding="utf-8")
            source = source.replace(f'      nativeNames: {{ telegram: "{alias}" }},\n', "")
            if f'name: "{alias}"' not in source:
                needle = f'      name: "{command_name}",\n'
                command_start = source.find(needle)
                command_end = source.find("    });\n", command_start)
                alias_block = CONTAINER_ONLY_ALIAS_BLOCKS.get(repo)
                if command_start == -1 or command_end == -1 or not alias_block:
                    print(f"OpenClaw container alias skipped: /{alias} ({plugin_file})")
                    continue
                insert_at = command_end + len("    });\n")
                source = source[:insert_at] + alias_block + source[insert_at:]
            plugin_file.write_text(source, encoding="utf-8")
        print(f"OpenClaw container alias enabled: /{alias} -> /{command_name}")


def main() -> None:
    _ensure_openclaw_config()
    _apply_container_only_command_aliases()
    disable_plugin_command_auth(PLUGINS_DIR, log_prefix="OpenClaw container command auth disabled")

    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    configure_gateway(
        config,
        port=GATEWAY_PORT,
        include_tailscale_origins=False,
        allow_insecure_auth=True,
    )
    telegram_configured = configure_telegram_main(
        config,
        include_account=True,
    )
    ensure_main_agent(
        config,
        config_path=CONFIG_PATH,
        heartbeat={"every": "360m", "target": "last", "directPolicy": "allow"},
        tools={"allow": ["*"], "deny": []},
    )

    # Fedora-style LiteLLM/OpenClaw-Harness, intentionally disabled here:
    # from openclaw_common import configure_litellm_provider
    # configure_litellm_provider(config, default_model="deepseek-v4-flash")

    registered = register_openclaw_plugins(
        config,
        PLUGINS_DIR,
        telegram_target=os.environ.get("OPENCLAW_TELEGRAM_TARGET", ""),
    )
    CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    refresh_plugin_registry()

    print("OpenClaw model provider intentionally not configured")
    if telegram_configured:
        print("OpenClaw Telegram configured")
    print(f"OpenClaw plugins registered: {', '.join(registered)}")


if __name__ == "__main__":
    main()
