#!/usr/bin/env python3
"""Shared installer/registration helpers for safrano9999 OpenClaw plugins."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Callable, Iterable


def _repo_name(spec: str) -> str:
    return spec.split("@", 1)[0]


def _load_plugin_manifest(repo_path: Path) -> dict[str, Any]:
    manifest_path = repo_path / "openclaw.plugin.json"
    if not manifest_path.exists():
        raise SystemExit(f"Missing OpenClaw plugin manifest: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SystemExit(f"Invalid OpenClaw plugin manifest {manifest_path}: {error}") from error
    if not isinstance(manifest, dict):
        raise SystemExit(f"Invalid OpenClaw plugin manifest {manifest_path}: expected object")
    return manifest


def _manifest_plugin_id(repo_path: Path, manifest: dict[str, Any]) -> str:
    plugin_id = manifest.get("id")
    if not isinstance(plugin_id, str) or not plugin_id.strip():
        raise SystemExit(f"OpenClaw plugin manifest has no id: {repo_path / 'openclaw.plugin.json'}")
    return plugin_id.strip()


def _manifest_config_properties(manifest: dict[str, Any]) -> dict[str, Any]:
    schema = manifest.get("configSchema")
    if not isinstance(schema, dict):
        return {}
    properties = schema.get("properties")
    return properties if isinstance(properties, dict) else {}


def plugin_dirs(
    plugins_dir: Path,
    plugin_names: Iterable[str] | None = None,
) -> Iterable[tuple[str, str, Path]]:
    if plugin_names:
        candidates = [plugins_dir / _repo_name(name) for name in plugin_names]
    else:
        candidates = sorted(
            path for path in plugins_dir.iterdir()
            if path.is_dir() and (path / "openclaw.plugin.json").exists()
        )
    for repo_path in candidates:
        manifest = _load_plugin_manifest(repo_path)
        yield repo_path.name, _manifest_plugin_id(repo_path, manifest), repo_path


def install_openclaw_plugins(
    plugins_dir: Path,
    openclaw_cmd: Callable[..., list[str]],
    *,
    links: bool = False,
    plugin_names: Iterable[str] | None = None,
) -> list[str]:
    """Install staged plugin directories."""

    installed: list[str] = []
    for repo, plugin_id, repo_path in plugin_dirs(plugins_dir, plugin_names):
        if not (repo_path / "openclaw.plugin.json").exists():
            raise SystemExit(f"Missing OpenClaw plugin repo: {repo_path}")

        command = openclaw_cmd("plugins", "install")
        if links:
            command.append("--link")
        command.extend(("--dangerously-force-unsafe-install", str(repo_path)))
        subprocess.run(command, check=True)
        installed.append(plugin_id)
    return installed


def setup_plugin_python(
    plugins_dir: Path,
    *,
    fallback_venv: bool = False,
    plugin_names: Iterable[str] | None = None,
) -> list[str]:
    """Build plugin .venv directories for staged plugins."""

    prepared: list[str] = []
    for repo, plugin_id, repo_path in plugin_dirs(plugins_dir, plugin_names):
        setup_script = repo_path / "scripts" / "setup-python.sh"
        if setup_script.exists():
            setup_script.chmod(setup_script.stat().st_mode | 0o111)
            subprocess.run([str(setup_script)], cwd=repo_path, check=True)
            prepared.append(plugin_id)
            continue

        requirements = repo_path / "requirements.txt"
        if not fallback_venv or not requirements.exists():
            continue
        venv_python = repo_path / ".venv" / "bin" / "python"
        subprocess.run(["python3", "-m", "venv", str(repo_path / ".venv")], check=True)
        subprocess.run([str(venv_python), "-m", "pip", "install", "--no-cache-dir", "--upgrade", "pip", "wheel"], check=True)
        subprocess.run([str(venv_python), "-m", "pip", "install", "--no-cache-dir", "-r", str(requirements), "python-dotenv"], check=True)
        prepared.append(plugin_id)
    return prepared


def disable_plugin_command_auth(plugins_dir: Path, *, log_prefix: str) -> None:
    for repo, _plugin_id, repo_path in plugin_dirs(plugins_dir):
        plugin_file = repo_path / "index.js"
        if not plugin_file.exists():
            continue
        source = plugin_file.read_text(encoding="utf-8")
        patched = source.replace("      requireAuth: true,", "      requireAuth: false,")
        if patched != source:
            plugin_file.write_text(patched, encoding="utf-8")
            print(f"{log_prefix}: {repo}")


def merge_plugin_config(entry: dict[str, Any], values: dict[str, Any]) -> None:
    config = entry.setdefault("config", {})
    for key, value in values.items():
        if isinstance(value, dict) and isinstance(config.get(key), dict):
            config[key].update(value)
        else:
            config[key] = value


def register_openclaw_plugins(
    config: dict[str, Any],
    plugins_dir: Path,
    *,
    telegram_target: str = "",
) -> list[str]:
    plugins = config.setdefault("plugins", {})
    paths = plugins.setdefault("load", {}).setdefault("paths", [])
    entries = plugins.setdefault("entries", {})
    registered: list[str] = []

    for _repo, plugin_id, repo_path in plugin_dirs(plugins_dir):
        manifest = _load_plugin_manifest(repo_path)
        repo_path_text = str(repo_path)
        if repo_path_text not in paths:
            paths.append(repo_path_text)
        entry = entries.setdefault(plugin_id, {})
        entry["enabled"] = True
        registered.append(plugin_id)

        target = telegram_target.strip()
        if target:
            delivery = {"channel": "telegram", "target": target}
            properties = _manifest_config_properties(manifest)
            if "delivery" in properties:
                merge_plugin_config(entry, {"delivery": dict(delivery)})
            if "statusDelivery" in properties:
                merge_plugin_config(entry, {"statusDelivery": dict(delivery)})
    webhook_runner = plugins_dir / "WEBHOOK-RUNNER"
    if (webhook_runner / "openclaw.plugin.json").exists():
        runner_path = str(webhook_runner)
        if runner_path not in paths:
            paths.append(runner_path)
        runner_entry = entries.setdefault("safrano9999-webhooks", {})
        runner_entry["enabled"] = True
        runner_entry["hooks"] = {"allowConversationAccess": True}
    return registered


def _openclaw_cmd(*args: str) -> list[str]:
    return ["openclaw", *args]


def main() -> None:
    parser = argparse.ArgumentParser(description="Install or prepare the four safrano9999 OpenClaw plugins.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    install_parser = subparsers.add_parser("install")
    install_parser.add_argument("--plugins-dir", required=True)
    install_parser.add_argument("--links", action="store_true", help="Install staged repo directories with OpenClaw --link.")
    install_parser.add_argument("--plugins", nargs="+")

    python_parser = subparsers.add_parser("setup-python")
    python_parser.add_argument("--plugins-dir", required=True)
    python_parser.add_argument("--fallback-venv", action="store_true")
    python_parser.add_argument("--plugins", nargs="+")

    args = parser.parse_args()

    if args.command == "install":
        plugins_dir = Path(args.plugins_dir)
        installed = install_openclaw_plugins(
            plugins_dir,
            _openclaw_cmd,
            links=args.links,
            plugin_names=args.plugins,
        )
        print(f"OpenClaw safrano9999 plugins installed: {', '.join(installed)}")
    elif args.command == "setup-python":
        plugins_dir = Path(args.plugins_dir)
        prepared = setup_plugin_python(
            plugins_dir,
            fallback_venv=args.fallback_venv,
            plugin_names=args.plugins,
        )
        print(f"OpenClaw safrano9999 plugin Python prepared: {', '.join(prepared)}")


if __name__ == "__main__":
    main()
