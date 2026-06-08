#!/usr/bin/env python3
"""Shared OpenClaw config helpers for safcontainer images."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DISCOVERY_TIMEOUT_SECONDS = 5


def openclaw_cmd(*args: str) -> list[str]:
    raw = os.environ.get("OPENCLAW_BIN", "").strip()
    if raw:
        base = raw.split()
    elif shutil.which("openclaw"):
        base = ["openclaw"]
    else:
        base = ["node", "/app/openclaw.mjs"]
    return [*base, *args]


def env_ref(name: str) -> dict[str, str]:
    return {"source": "env", "provider": "default", "id": name}


def int_env(name: str, default: int) -> int:
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def origin(host: str, port: int | str) -> str:
    host = str(host).strip() or "127.0.0.1"
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return f"http://{host}:{port}"


def tailscale_hosts() -> list[str]:
    hosts: list[str] = []
    try:
        result = subprocess.run(
            ["tailscale", "status", "--json"],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
        payload: Any = json.loads(result.stdout)
    except (
        FileNotFoundError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        json.JSONDecodeError,
    ):
        payload = {}

    self_info = payload.get("Self") if isinstance(payload, dict) else {}
    if isinstance(self_info, dict):
        dns_name = str(self_info.get("DNSName") or "").strip().rstrip(".")
        if dns_name:
            hosts.append(dns_name)
        for ip_addr in self_info.get("TailscaleIPs") or []:
            ip_addr = str(ip_addr).strip()
            if ip_addr:
                hosts.append(ip_addr)

    ts_hostname = os.environ.get("TS_HOSTNAME", "").strip().rstrip(".")
    if "." in ts_hostname:
        hosts.append(ts_hostname)
    return list(dict.fromkeys(hosts))


def configure_gateway(
    config: dict[str, Any],
    *,
    port: int,
    host_port: int | None = None,
    include_tailscale_origins: bool = False,
    allow_insecure_auth: bool = False,
) -> list[str]:
    gateway = config.setdefault("gateway", {})
    gateway["mode"] = "local"
    gateway["bind"] = "lan"
    gateway["port"] = port

    control_ui = gateway.setdefault("controlUi", {})
    control_ui["dangerouslyDisableDeviceAuth"] = True
    control_ui.pop("dangerouslyAllowHostHeaderOriginFallback", None)
    if allow_insecure_auth:
        control_ui["allowInsecureAuth"] = True

    host = os.environ.get("HOST", "127.0.0.1").strip() or "127.0.0.1"
    publish_port = os.environ.get("OPENCLAW_GATEWAY_PUBLISH_PORT", "").strip()
    origins = list(control_ui.get("allowedOrigins") or [])
    wanted = [origin(host, port), origin("127.0.0.1", port), origin("localhost", port)]
    if host_port:
        wanted.append(origin(host, host_port))
    if publish_port:
        wanted.extend([origin("127.0.0.1", publish_port), origin("localhost", publish_port)])
    if include_tailscale_origins:
        for tailscale_host in tailscale_hosts():
            wanted.append(origin(tailscale_host, port))
            if host_port:
                wanted.append(origin(tailscale_host, host_port))

    for item in wanted:
        if item not in origins:
            origins.append(item)
    control_ui["allowedOrigins"] = origins

    if os.environ.get("OPENCLAW_GATEWAY_TOKEN", "").strip():
        gateway["auth"] = {"mode": "token", "token": env_ref("OPENCLAW_GATEWAY_TOKEN")}
    return origins


def ensure_main_agent(
    config: dict[str, Any],
    *,
    config_path: Path,
    workspace: str = "",
    set_agent_dir: bool = False,
    mark_default: bool = False,
    heartbeat: dict[str, Any] | None = None,
    tools: dict[str, Any] | None = None,
) -> dict[str, Any]:
    agents = config.setdefault("agents", {})
    workspace_value = (
        workspace.strip()
        or os.environ.get("OPENCLAW_AGENT_WORKSPACE", "").strip()
        or os.environ.get("OPENCLAW_WORKSPACE_DIR", "").strip()
        or str(config_path.parent / "workspace")
    )
    workspace_path = str(Path(os.path.expanduser(workspace_value)).resolve())
    Path(workspace_path).mkdir(parents=True, exist_ok=True)
    agents.setdefault("defaults", {}).setdefault("workspace", workspace_path)

    agent_list = agents.setdefault("list", [])
    main = next((entry for entry in agent_list if isinstance(entry, dict) and entry.get("id") == "main"), None)
    if main is None:
        main = {"id": "main", "name": "main"}
    else:
        agent_list.remove(main)

    main["name"] = main.get("name") or "main"
    main["workspace"] = main.get("workspace") or workspace_path
    if set_agent_dir:
        main["agentDir"] = main.get("agentDir") or str(config_path.parent / "agents" / "main" / "agent")
        Path(main["agentDir"]).mkdir(parents=True, exist_ok=True)
    if mark_default:
        main["default"] = True
        for entry in agent_list:
            if isinstance(entry, dict):
                entry.pop("default", None)
    if heartbeat is not None:
        main["heartbeat"] = heartbeat
    if tools is not None:
        main["tools"] = tools
    main.pop("models", None)
    agent_list.insert(0, main)
    return main


def configure_telegram_main(
    config: dict[str, Any],
    *,
    account_name: str = "main",
    include_account: bool = False,
    include_binding: bool = False,
    owner_allow: bool = False,
) -> bool:
    if not os.environ.get("TELEGRAMTOKEN_OPENCLAW", "").strip():
        return False

    token_ref = env_ref("TELEGRAMTOKEN_OPENCLAW")
    telegram = config.setdefault("channels", {}).setdefault("telegram", {})
    telegram["enabled"] = True
    telegram["botToken"] = token_ref
    telegram["dmPolicy"] = "open"
    telegram["allowFrom"] = ["*"]
    telegram["groupPolicy"] = "open"
    telegram["groupAllowFrom"] = ["*"]
    telegram["groups"] = {"*": {"requireMention": False}}
    telegram["network"] = {"autoSelectFamily": False, "dnsResultOrder": "ipv4first"}

    if include_account:
        telegram["capabilities"] = {"inlineButtons": "dm"}
        telegram["commands"] = {"native": False, "nativeSkills": False}
        telegram["streaming"] = {"mode": "off"}
        telegram["execApprovals"] = {
            "enabled": False,
            "approvers": [],
            "agentFilter": ["main"],
            "target": "dm",
        }
        telegram["accounts"] = {
            "default": {
                "name": account_name,
                "enabled": True,
                "dmPolicy": "open",
                "allowFrom": ["*"],
                "botToken": token_ref,
                "groupPolicy": "open",
                "groupAllowFrom": ["*"],
                "streaming": {"mode": "partial"},
            }
        }
        telegram["defaultAccount"] = "default"

    if include_binding:
        bindings = config.setdefault("bindings", [])
        telegram_main_binding = {
            "type": "route",
            "match": {"channel": "telegram", "accountId": "default"},
            "agentId": "main",
            "session": {"dmScope": "main"},
        }
        bindings[:] = [
            item
            for item in bindings
            if not (isinstance(item, dict) and item.get("match") == telegram_main_binding["match"])
        ]
        bindings.append(telegram_main_binding)

    if owner_allow:
        config.setdefault("commands", {})["ownerAllowFrom"] = ["*"]
    return True


def litellm_base_url() -> str:
    raw_url = os.environ.get("LITELLM_URL", "").strip()
    port = os.environ.get("LITELLM_PORT", "").strip()
    if not raw_url or not port:
        return ""
    base = raw_url.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3].rstrip("/")
    return f"{base}:{port}/v1"


def discover_litellm_models(fallback_model: str) -> tuple[list[str], bool]:
    base_url = litellm_base_url()
    api_key = os.environ.get("LITELLM_API_KEY", "").strip()
    models = [fallback_model]
    if not base_url or not api_key:
        return models, False

    request = urllib.request.Request(
        f"{base_url}/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=DISCOVERY_TIMEOUT_SECONDS) as response:
            payload: Any = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        print(f"OpenClaw LiteLLM model discovery skipped: {exc}")
        return models, False

    discovered: list[str] = []
    for item in payload.get("data", []) if isinstance(payload, dict) else []:
        model_id = item.get("id") if isinstance(item, dict) else item
        if not isinstance(model_id, str):
            continue
        model_id = model_id.strip()
        if model_id.startswith("litellm/"):
            model_id = model_id.removeprefix("litellm/")
        if model_id and model_id not in discovered:
            discovered.append(model_id)

    for model_id in discovered:
        if model_id not in models:
            models.append(model_id)
    return models, bool(discovered)


def configure_litellm_provider(
    config: dict[str, Any],
    *,
    default_model: str,
    default_context_window: int = 128000,
    default_max_tokens: int = 8192,
) -> dict[str, Any]:
    model = os.environ.get("OPENCLAW_LITELLM_MODEL", default_model).strip()
    if model.startswith("litellm/"):
        model = model.removeprefix("litellm/")
    if not model:
        raise SystemExit("OPENCLAW_LITELLM_MODEL must not be empty")

    discovered_models, discovery_ok = discover_litellm_models(model)
    model_name = os.environ.get("OPENCLAW_LITELLM_MODEL_NAME", model).strip() or model
    context_window = int_env("OPENCLAW_LITELLM_CONTEXT_WINDOW", default_context_window)
    max_tokens = int_env("OPENCLAW_LITELLM_MAX_TOKENS", default_max_tokens)

    models_config = config.setdefault("models", {})
    models_config["mode"] = "merge"
    provider = models_config.setdefault("providers", {}).setdefault("litellm", {})
    provider["baseUrl"] = litellm_base_url()
    provider["api"] = "openai-completions"
    provider["apiKey"] = env_ref("LITELLM_API_KEY")
    provider["request"] = {"allowPrivateNetwork": True}

    merged: dict[str, dict[str, Any]] = {}
    for item in provider.get("models", []):
        if not isinstance(item, dict):
            continue
        model_id = item.get("id")
        if isinstance(model_id, str) and model_id:
            merged[model_id] = item

    for model_id in discovered_models:
        entry = {
            "id": model_id,
            "name": model_name if model_id == model else model_id,
            "reasoning": True,
            "input": ["text"],
            "contextWindow": context_window,
            "maxTokens": max_tokens,
        }
        entry.update(merged.get(model_id, {}))
        entry["id"] = model_id
        merged[model_id] = entry
    provider["models"] = list(merged.values())

    full_model = f"litellm/{model}"
    config.setdefault("agents", {}).setdefault("defaults", {}).setdefault("model", {})["primary"] = full_model
    config.setdefault("agents", {}).setdefault("defaults", {}).pop("models", None)
    return {
        "full_model": full_model,
        "discovered": discovery_ok,
        "discovered_count": len(discovered_models),
        "written_count": len(provider["models"]),
    }


def refresh_plugin_registry() -> None:
    subprocess.run(openclaw_cmd("plugins", "registry", "--refresh"), check=True)
