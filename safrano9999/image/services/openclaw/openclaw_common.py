#!/usr/bin/env python3
"""Shared OpenClaw config helpers for safcontainer images."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from python_header import OpenAIV1Provider


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

    host = os.environ.get("FASTAPI_HOST", "127.0.0.1").strip() or "127.0.0.1"
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
    if not os.environ.get("OPENCLAW_TELEGRAMTOKEN", "").strip():
        return False

    token_ref = env_ref("OPENCLAW_TELEGRAMTOKEN")
    telegram = config.setdefault("channels", {}).setdefault("telegram", {})
    telegram["enabled"] = True
    telegram["dmPolicy"] = "open"
    telegram["allowFrom"] = ["*"]
    telegram["groupPolicy"] = "open"
    telegram["groupAllowFrom"] = ["*"]
    telegram["groups"] = {"*": {"requireMention": False}}
    telegram["network"] = {"autoSelectFamily": False, "dnsResultOrder": "ipv4first"}

    if include_account:
        telegram.pop("botToken", None)
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
    else:
        telegram["botToken"] = token_ref

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


@dataclass(frozen=True)
class OpenAIV1RuntimeProvider:
    config: "OpenAIV1Provider"
    provider_id: str
    key_env: str
    models: tuple[str, ...]


def _indexed_openai_v1_env_name(field: str, index: int) -> str:
    if index == 1:
        return f"OPENAI_V1_{field}"
    for suffix in (f"_{index}", f"_{index:02d}"):
        name = f"OPENAI_V1_{field}{suffix}"
        if name in os.environ:
            return name
    pattern = re.compile(rf"^OPENAI_V1_{re.escape(field)}_(\d+)$")
    for name in sorted(os.environ):
        match = pattern.match(name)
        if match and int(match.group(1)) == index:
            return name
    return f"OPENAI_V1_{field}_{index}"


def _provider_id(provider: "OpenAIV1Provider", used: set[str]) -> str:
    raw = provider.provider or provider.key
    candidate = re.sub(r"[^a-z0-9._-]+", "_", raw.lower()).strip("._-")
    candidate = candidate or provider.key
    if candidate in used:
        candidate = f"{candidate}_{provider.index}"
    used.add(candidate)
    return candidate


def discover_openai_v1_runtime_providers(
    *,
    consumer: str,
    timeout: float = DISCOVERY_TIMEOUT_SECONDS,
) -> list[OpenAIV1RuntimeProvider]:
    from python_header import openai_v1_models, openai_v1_providers

    configured = openai_v1_providers()
    if not configured:
        raise SystemExit("OPENAI_V1_URL, OPENAI_V1_PORT, and OPENAI_V1_KEY must be configured")

    runtime: list[OpenAIV1RuntimeProvider] = []
    used_ids: set[str] = set()
    for provider in configured:
        key_env = _indexed_openai_v1_env_name("KEY", provider.index)
        if not provider.api_key:
            raise SystemExit(f"{key_env} must not be empty")
        provider_id = _provider_id(provider, used_ids)
        try:
            models = tuple(openai_v1_models(provider, timeout=timeout))
        except Exception as exc:
            print(f"{consumer} model discovery skipped for {provider_id}: {exc}")
            models = ()
        runtime.append(
            OpenAIV1RuntimeProvider(
                config=provider,
                provider_id=provider_id,
                key_env=key_env,
                models=models,
            )
        )
    return runtime


def select_openai_v1_model(
    providers: list[OpenAIV1RuntimeProvider],
    configured_model: str,
) -> tuple[OpenAIV1RuntimeProvider, str]:
    model = configured_model.strip()
    if not model:
        raise SystemExit("OpenAI v1 default model must not be empty")

    for provider in providers:
        aliases = {provider.provider_id}
        if provider.config.provider:
            aliases.add(provider.config.provider.strip().lower())
        for alias in aliases:
            prefix = f"{alias}/"
            if model.lower().startswith(prefix):
                selected_model = model[len(prefix):].strip()
                if selected_model:
                    return provider, selected_model

    for provider in providers:
        if model in provider.models:
            return provider, model
    return providers[0], model


def configure_openai_v1_providers(
    config: dict[str, Any],
    *,
    default_model: str,
    default_context_window: int = 128000,
    default_max_tokens: int = 8192,
) -> dict[str, Any]:
    configured_model = os.environ.get("OPENCLAW_OPENAI_V1_DEFAULT_LLM", default_model).strip()
    providers = discover_openai_v1_runtime_providers(consumer="OpenClaw")
    selected_provider, selected_model = select_openai_v1_model(providers, configured_model)

    models_config = config.setdefault("models", {})
    models_config["mode"] = "merge"
    provider_configs = models_config.setdefault("providers", {})
    written_count = 0
    discovered_count = 0

    for runtime in providers:
        provider = provider_configs.setdefault(runtime.provider_id, {})
        provider["baseUrl"] = runtime.config.base_url
        provider["api"] = "openai-completions"
        provider["apiKey"] = env_ref(runtime.key_env)
        provider["request"] = {"allowPrivateNetwork": True}

        merged: dict[str, dict[str, Any]] = {}
        for item in provider.get("models", []):
            if not isinstance(item, dict):
                continue
            model_id = item.get("id")
            if isinstance(model_id, str) and model_id:
                merged[model_id] = item

        model_ids = list(runtime.models)
        discovered_count += len(model_ids)
        if runtime == selected_provider and selected_model not in model_ids:
            model_ids.insert(0, selected_model)

        for model_id in model_ids:
            entry = {
                "id": model_id,
                "name": model_id,
                "reasoning": True,
                "input": ["text"],
                "contextWindow": default_context_window,
                "maxTokens": default_max_tokens,
            }
            entry.update(merged.get(model_id, {}))
            entry["id"] = model_id
            merged[model_id] = entry
        provider["models"] = list(merged.values())
        written_count += len(provider["models"])

    full_model = f"{selected_provider.provider_id}/{selected_model}"
    config.setdefault("agents", {}).setdefault("defaults", {}).setdefault("model", {})["primary"] = full_model
    config.setdefault("agents", {}).setdefault("defaults", {}).pop("models", None)
    return {
        "full_model": full_model,
        "provider_count": len(providers),
        "discovered": discovered_count > 0,
        "discovered_count": discovered_count,
        "written_count": written_count,
    }


def refresh_plugin_registry() -> None:
    subprocess.run(openclaw_cmd("plugins", "registry", "--refresh"), check=True)
