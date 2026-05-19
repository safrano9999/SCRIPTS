#!/usr/bin/env python3
"""Merge local project config.yaml files and render Fedora compose/quadlet files."""

from __future__ import annotations

import argparse
import os
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


CONFIG_NAME = "config.yaml"
FEDORA_CONFIG_NAME = "config.fedora43-ai.yaml"
MERGED_CONFIG_NAME = "merged_config.yaml"
LOCAL_CONFIG_NAME = "config.local.yaml"
MERGED_COMPOSE_NAME = "merged_compose.yaml"
SERVICE_NAME = "fedora43-ai"


class IndentDumper(yaml.SafeDumper):
    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise SystemExit(f"{path} must contain a YAML mapping")
    return data


def dump_yaml(path: Path, data: dict[str, Any]) -> None:
    path.write_text(
        yaml.dump(data, Dumper=IndentDumper, sort_keys=False),
        encoding="utf-8",
    )


def deep_merge(base: Any, extra: Any, *, overwrite: bool = False) -> Any:
    if isinstance(base, dict) and isinstance(extra, dict):
        result = deepcopy(base)
        for key, value in extra.items():
            if key in result:
                result[key] = deep_merge(result[key], value, overwrite=overwrite)
            else:
                result[key] = deepcopy(value)
        return result
    if isinstance(base, list) and isinstance(extra, list):
        result = deepcopy(base)
        for value in extra:
            if value not in result:
                result.append(deepcopy(value))
        return result
    return deepcopy(extra if overwrite else base)


def config_sources(project_dir: Path) -> list[Path]:
    sources: list[Path] = []
    fedora_config = project_dir / FEDORA_CONFIG_NAME
    if fedora_config.exists():
        sources.append(fedora_config)

    repos_dir = project_dir / "safrano9999"
    if repos_dir.exists():
        for repo_dir in sorted(path for path in repos_dir.iterdir() if path.is_dir()):
            config_path = repo_dir / CONFIG_NAME
            if config_path.exists():
                sources.append(config_path)
    return sources


def merge(project_dir: Path) -> None:
    sources = config_sources(project_dir)
    if not sources:
        dump_yaml(project_dir / MERGED_CONFIG_NAME, {})
        print("  ! Keine config.yaml Quellen gefunden")
        return

    merged: dict[str, Any] = {}
    for source in sources:
        merged = deep_merge(merged, load_yaml(source), overwrite=False)

    dump_yaml(project_dir / MERGED_CONFIG_NAME, merged)
    print(f"  Merged config.yaml ({len(sources)} Quellen) -> {MERGED_CONFIG_NAME}")


def prompt_value(label: str, default: Any, *, use_defaults: bool) -> Any:
    if use_defaults or not sys.stdin.isatty():
        return default

    default_text = "" if default is None else str(default)
    try:
        if default_text:
            value = input(f"    {label} [{default_text}]: ").strip()
        else:
            value = input(f"    {label}: ").strip()
    except EOFError:
        return default
    return default if value == "" else value


def coerce_like(value: Any, default: Any) -> Any:
    if isinstance(default, bool):
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(default, int):
        return int(value)
    return value


def configure_service(service_key: str, service: dict[str, Any], *, use_defaults: bool) -> dict[str, Any]:
    result = deepcopy(service)
    title = service.get("title", service_key)
    webui = result.get("webui")
    if isinstance(webui, dict):
        for key in ("host", "port", "publish_host", "publish_port"):
            if key not in webui:
                continue
            label = f"{title} {key.replace('_', ' ')}"
            webui[key] = coerce_like(
                prompt_value(label, webui[key], use_defaults=use_defaults),
                webui[key],
            )
    return result


def configure(project_dir: Path, *, use_defaults: bool) -> None:
    merged_path = project_dir / MERGED_CONFIG_NAME
    local_path = project_dir / LOCAL_CONFIG_NAME
    merged = load_yaml(merged_path)

    if local_path.exists():
        local = load_yaml(local_path)
        updated = deep_merge(local, merged, overwrite=False)
        if updated != local:
            dump_yaml(local_path, updated)
        print(f"  {LOCAL_CONFIG_NAME} exists")
        return

    print("")
    print(f"  Configuring {LOCAL_CONFIG_NAME}")
    print("")

    local = deepcopy(merged)
    services = local.get("services", {})
    if isinstance(services, dict):
        for service_key, service in list(services.items()):
            if isinstance(service, dict):
                services[service_key] = configure_service(
                    service_key, service, use_defaults=use_defaults
                )

    dump_yaml(local_path, local)
    print("")


def value_as_str(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def add_unique(target: list[Any], value: Any) -> None:
    if value not in target:
        target.append(value)


def render_volume(volume: Any) -> str:
    if isinstance(volume, str):
        return volume
    if isinstance(volume, dict):
        source = volume.get("source")
        target = volume.get("target")
        if not source or not target:
            raise SystemExit(f"Invalid volume entry: {volume}")
        options = volume.get("options")
        if options:
            return f"{source}:{target}:{options}"
        return f"{source}:{target}"
    raise SystemExit(f"Invalid volume entry: {volume}")


def volume_target(volume: str) -> str:
    parts = volume.split(":")
    return parts[1] if len(parts) > 1 else parts[0]


def named_volume_source(volume: str) -> str | None:
    if ":" not in volume:
        return None
    source = volume.split(":", 1)[0]
    if not source or source.startswith(("/", ".", "$", "~")) or "/" in source:
        return None
    return source


def render(project_dir: Path) -> None:
    merged = load_yaml(project_dir / MERGED_CONFIG_NAME)
    local = load_yaml(project_dir / LOCAL_CONFIG_NAME)
    config = deep_merge(merged, local, overwrite=True)

    defaults = config.get("defaults", {}) if isinstance(config.get("defaults"), dict) else {}
    default_publish_host = str(defaults.get("publish_host", "127.0.0.1"))
    services = config.get("services", {})
    if not isinstance(services, dict):
        services = {}

    ports: list[str] = []
    volumes: list[str] = []
    cap_add: list[str] = []
    devices: list[str] = []
    env: dict[str, str] = {}

    for service_key, service in services.items():
        if not isinstance(service, dict):
            continue
        webui = service.get("webui", {})
        if isinstance(webui, dict) and webui.get("port"):
            target = int(webui.get("target_port", webui["port"]))
            published = int(webui.get("publish_port", webui["port"]))
            publish_host = str(webui.get("publish_host", default_publish_host))
            add_unique(ports, f"{publish_host}:{published}:{target}")

            env_port = webui.get("env_port")
            if env_port:
                env[str(env_port)] = str(target)
            if service_key == "openclaw_gateway":
                env["OPENCLAW_GATEWAY_PUBLISH_HOST"] = publish_host
                env["OPENCLAW_GATEWAY_PUBLISH_PORT"] = str(published)

        service_env = service.get("env", {})
        if isinstance(service_env, dict):
            for key, value in service_env.items():
                env[str(key)] = value_as_str(value)

        container = service.get("container", {})
        if not isinstance(container, dict):
            continue
        for capability in container.get("capabilities", []) or []:
            add_unique(cap_add, str(capability))
        for device in container.get("devices", []) or []:
            add_unique(devices, str(device))
        for volume in container.get("volumes", []) or []:
            rendered = render_volume(volume)
            target = volume_target(rendered)
            if all(volume_target(existing) != target for existing in volumes):
                volumes.append(rendered)

    merged_compose = {
        "environment": env,
        "ports": ports,
        "volumes": volumes,
        "cap_add": cap_add,
        "devices": devices,
    }
    dump_yaml(project_dir / MERGED_COMPOSE_NAME, merged_compose)

    compose: dict[str, Any] = {
        "services": {
            SERVICE_NAME: {
                "build": {"context": ".", "dockerfile": "Containerfile"},
                "image": "localhost/fedora43-ai:latest",
                "container_name": "${INSTANCE:-fedora43-ai}",
                "ports": ports,
                "env_file": [".env"],
                "environment": [
                    "PATH=/usr/local/bin:/root/.local/bin:/root/.cargo/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                    "DISPLAY=${DISPLAY:-:0}",
                    "NO_AT_BRIDGE=1",
                    "XDG_RUNTIME_DIR=/tmp/runtime-root",
                    "HERMES_HOME=/root/hermes-home",
                    "HERMES_INSTALL_DIR=/usr/local/lib/hermes-agent",
                    "OPENCLAW_START=1",
                    "HERMES_START=1",
                ],
                "volumes": [
                    "${HOST_HOME_DIR:-home}:/home",
                    "${HOST_SRV_DIR}:/srv",
                    "${HOST_ROOT_DIR:-root}:/root",
                    "/tmp/.X11-unix:/tmp/.X11-unix",
                ],
            }
        },
        "volumes": {"home": {}, "root": {}},
    }

    compose_service = compose["services"][SERVICE_NAME]
    for key, value in env.items():
        compose_service["environment"].append(f"{key}={value}")
    compose_service["volumes"].extend(volumes)
    if cap_add:
        compose_service["cap_add"] = cap_add
    if devices:
        compose_service["devices"] = devices
    for volume in volumes:
        source = named_volume_source(volume)
        if source:
            compose["volumes"].setdefault(source, {})

    dump_yaml(project_dir / "compose.yml", compose)

    env_file = project_dir / ".env"
    container_lines = [
        "[Container]",
        "ContainerName=fedora43-ai",
        "Image=localhost/fedora43-ai:latest",
        f"EnvironmentFile={env_file}",
        "Environment=OPENCLAW_START=1",
        "Environment=HERMES_START=1",
    ]
    for key, value in env.items():
        container_lines.append(f"Environment={key}={value}")
    for port in ports:
        container_lines.append(f"PublishPort={port}")
    container_lines.append(f"Volume={Path.home()}/fedora43-ai/srv:/srv")
    for volume in volumes:
        container_lines.append(f"Volume={volume}")
    for capability in cap_add:
        container_lines.append(f"AddCapability={capability}")
    for device in devices:
        container_lines.append(f"AddDevice={device}")
    container_lines.extend(
        [
            "",
            "[Service]",
            "Restart=always",
            "TimeoutStartSec=60",
            "",
            "[Install]",
            "WantedBy=default.target",
            "",
        ]
    )
    (project_dir / "fedora43-ai.container").write_text(
        "\n".join(container_lines),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("merge", "configure", "render"))
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--defaults", action="store_true")
    args = parser.parse_args()

    project_dir = args.project_dir.resolve()
    if args.command == "merge":
        merge(project_dir)
    elif args.command == "configure":
        configure(project_dir, use_defaults=args.defaults)
    else:
        render(project_dir)


if __name__ == "__main__":
    main()
