#!/usr/bin/env python3
"""Shared installer/registration helpers for safrano9999 OpenClaw plugins."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Iterable


DEFAULT_CRONTAB_SPEC = "CET 07:00,CET 12:00,CET 15:30,CET 19:00"
DEFAULT_CRON_MESSAGE = "__safrano9999_webhooks__"
CRON_JOB_PREFIX = "safrano9999-routines-"
OPENCLAW_CRON_STORE_JS = r"""
import fs from "node:fs";
import { pathToFileURL } from "node:url";

const storePath = process.argv[1];
const prefix = process.argv[2];
const requested = JSON.parse(fs.readFileSync(0, "utf8"));
const distDirs = [
  process.env.OPENCLAW_DIST_DIR,
  "/usr/local/lib/node_modules/openclaw/dist",
  "/app/dist",
].filter(Boolean);

let loadStore;
let saveStore;
for (const distDir of distDirs) {
  if (!fs.existsSync(distDir)) continue;
  for (const file of fs.readdirSync(distDir).filter((name) => /^store-.*\.js$/.test(name))) {
    const module = await import(pathToFileURL(`${distDir}/${file}`));
    for (const value of Object.values(module)) {
      if (typeof value !== "function") continue;
      if (value.name === "loadCronJobsStore") loadStore = value;
      if (value.name === "saveCronJobsStore") saveStore = value;
    }
    if (loadStore && saveStore) break;
  }
  if (loadStore && saveStore) break;
}
if (!loadStore || !saveStore) {
  throw new Error("OpenClaw cron store API not found");
}

const current = await loadStore(storePath);
const jobs = current.jobs.filter((job) => !String(job.id || "").startsWith(prefix));
const ids = new Set(jobs.map((job) => String(job.id || "")));
for (const job of requested.legacy) {
  const id = String(job.id || "");
  if (id && !ids.has(id)) {
    jobs.push(job);
    ids.add(id);
  }
}
jobs.push(...requested.managed);
await saveStore(storePath, { version: 1, jobs });
"""
TZ_ALIASES = {
    "CET": "Europe/Vienna",
    "CEST": "Europe/Vienna",
    "VIENNA": "Europe/Vienna",
    "EUROPE/VIENNA": "Europe/Vienna",
}

PLUGIN_IDS = {
    "DAILYNEWS": "dailynews",
    "CALENDAR": "calendar",
    "ZEROINBOX": "zeroinbox",
    "KACHELMANN": "kachelmann",
}


def _plugin_selection(plugin_names: Iterable[str] | None = None) -> Iterable[tuple[str, str]]:
    if not plugin_names:
        yield from PLUGIN_IDS.items()
        return
    for name in plugin_names:
        repo = name.split("@", 1)[0].upper()
        if repo not in PLUGIN_IDS:
            raise SystemExit(f"Unknown safrano9999 OpenClaw plugin repo: {name}")
        yield repo, PLUGIN_IDS[repo]


def plugin_dirs(
    plugins_dir: Path,
    plugin_names: Iterable[str] | None = None,
) -> Iterable[tuple[str, str, Path]]:
    for repo, plugin_id in _plugin_selection(plugin_names):
        yield repo, plugin_id, plugins_dir / repo


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
    runtime_env_path: Path | None = None,
    runtime_conf_path: Path | None = None,
    telegram_target: str = "",
) -> list[str]:
    plugins = config.setdefault("plugins", {})
    paths = plugins.setdefault("load", {}).setdefault("paths", [])
    entries = plugins.setdefault("entries", {})
    registered: list[str] = []

    for _repo, plugin_id, repo_path in plugin_dirs(plugins_dir):
        repo_path_text = str(repo_path)
        if repo_path_text not in paths:
            paths.append(repo_path_text)
        entries.setdefault(plugin_id, {})["enabled"] = True
        registered.append(plugin_id)

    if runtime_env_path:
        merge_plugin_config(entries.setdefault("calendar", {}), {
            "calenvPath": str(runtime_env_path),
            "envFile": str(runtime_env_path),
            "logDir": "/var/log/safrano9999/calendar",
        })
        merge_plugin_config(entries.setdefault("kachelmann", {}), {
            "envFile": str(runtime_env_path),
        })
    if runtime_conf_path:
        merge_plugin_config(entries.setdefault("zeroinbox", {}), {
            "configPath": str(runtime_conf_path),
            "envFile": str(runtime_env_path or runtime_conf_path),
        })

    telegram_target = telegram_target.strip()
    if telegram_target:
        merge_plugin_config(entries.setdefault("dailynews", {}), {
            "delivery": {"channel": "telegram", "target": telegram_target},
        })
        merge_plugin_config(entries.setdefault("calendar", {}), {
            "delivery": {"channel": "telegram", "target": telegram_target},
        })
        merge_plugin_config(entries.setdefault("zeroinbox", {}), {
            "delivery": {"channel": "telegram", "target": telegram_target},
        })
        merge_plugin_config(entries.setdefault("kachelmann", {}), {
            "statusDelivery": {"channel": "telegram", "target": telegram_target},
        })
    webhook_runner = plugins_dir / "WEBHOOK-RUNNER"
    if (webhook_runner / "openclaw.plugin.json").exists():
        runner_path = str(webhook_runner)
        if runner_path not in paths:
            paths.append(runner_path)
        runner_entry = entries.setdefault("safrano9999-webhooks", {})
        runner_entry["enabled"] = True
        runner_entry["hooks"] = {"allowConversationAccess": True}
    return registered


def normalize_timezone(value: str, default_tz: str) -> str:
    value = value.strip() or default_tz
    return TZ_ALIASES.get(value.upper(), value)


def parse_crontab_spec(spec: str, *, default_tz: str) -> list[tuple[str, int, int]]:
    entries: list[tuple[str, int, int]] = []
    current_tz = normalize_timezone(default_tz, default_tz)

    for raw_item in spec.split(","):
        item = raw_item.strip()
        if not item:
            continue
        parts = item.split()
        if len(parts) == 1:
            tz = current_tz
            time_text = parts[0]
        elif len(parts) == 2:
            tz = normalize_timezone(parts[0], default_tz)
            current_tz = tz
            time_text = parts[1]
        else:
            raise SystemExit(f"Invalid crontab item: {item!r}; use e.g. 'CET 23:49'")

        match = re.fullmatch(r"(\d{1,2}):(\d{2})", time_text)
        if not match:
            raise SystemExit(f"Invalid crontab time: {time_text!r}; use HH:MM")
        hour = int(match.group(1))
        minute = int(match.group(2))
        if hour > 23 or minute > 59:
            raise SystemExit(f"Invalid crontab time: {time_text!r}; use 00:00 through 23:59")
        entries.append((tz, hour, minute))

    if not entries:
        raise SystemExit("No crontab entries configured")
    return entries


def _cron_slug(tz: str, hour: int, minute: int) -> str:
    tz_slug = re.sub(r"[^A-Za-z0-9]+", "-", tz).strip("-").lower() or "local"
    return f"{tz_slug}-{hour:02d}{minute:02d}"


def install_openclaw_crontab(
    config_dir: Path,
    crontab_spec: str,
    *,
    default_tz: str = "Europe/Vienna",
    message: str = DEFAULT_CRON_MESSAGE,
) -> list[str]:
    cron_dir = config_dir / "cron"
    cron_jobs = cron_dir / "jobs.json"
    cron_state = cron_dir / "jobs-state.json"
    entries = parse_crontab_spec(crontab_spec, default_tz=default_tz)
    now_ms = int(time.time() * 1000)

    legacy_jobs: list[dict[str, Any]] = []
    if cron_jobs.exists() and cron_jobs.stat().st_size > 0:
        try:
            payload = json.loads(cron_jobs.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {"version": 1, "jobs": []}
    else:
        payload = {"version": 1, "jobs": []}
    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        payload = {"version": 1, "jobs": []}

    legacy_jobs = [
        job
        for job in payload.get("jobs", [])
        if isinstance(job, dict) and not str(job.get("id", "")).startswith(CRON_JOB_PREFIX)
    ]
    managed_jobs: list[dict[str, Any]] = []
    labels: list[str] = []
    for tz, hour, minute in entries:
        label = f"{hour:02d}:{minute:02d} {tz}"
        labels.append(label)
        managed_jobs.append({
            "id": CRON_JOB_PREFIX + _cron_slug(tz, hour, minute),
            "name": CRON_JOB_PREFIX + _cron_slug(tz, hour, minute),
            "enabled": True,
            "createdAtMs": now_ms,
            "updatedAtMs": now_ms,
            "schedule": {
                "kind": "cron",
                "expr": f"{minute} {hour} * * *",
                "tz": tz,
                "staggerMs": 0,
            },
            "sessionTarget": "main",
            "wakeMode": "now",
            "payload": {"kind": "systemEvent", "text": message},
            "state": {},
        })

    cron_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["node", "--input-type=module", "-e", OPENCLAW_CRON_STORE_JS, str(cron_jobs), CRON_JOB_PREFIX],
        input=json.dumps({"legacy": legacy_jobs, "managed": managed_jobs}),
        text=True,
        check=True,
    )
    cron_jobs.unlink(missing_ok=True)
    cron_state.unlink(missing_ok=True)
    return labels


def _openclaw_cmd(*args: str) -> list[str]:
    return ["openclaw", *args]


def _crontab_spec_from_values(values: list[str] | None) -> str:
    if values:
        return " ".join(values)
    return (
        os.environ.get("OPENCLAW_CRONTAB")
        or os.environ.get("SAFRANO9999_ROUTINES_CRONTAB")
        or DEFAULT_CRONTAB_SPEC
    )


def _run_crontab(args: argparse.Namespace) -> None:
    labels = install_openclaw_crontab(
        Path(args.config_dir),
        _crontab_spec_from_values(args.crontab),
        default_tz=args.tz,
        message=args.message,
    )
    print(f"OpenClaw safrano9999 cronjobs written: {', '.join(labels)}")


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--crontab":
        compat_parser = argparse.ArgumentParser(description="Install safrano9999 OpenClaw crontab jobs.")
        compat_parser.add_argument("--config-dir", default=os.environ.get("OPENCLAW_CONFIG_DIR", "/root/.openclaw"))
        compat_parser.add_argument("--tz", default=os.environ.get("SAFRANO9999_ROUTINES_TZ", "Europe/Vienna"))
        compat_parser.add_argument("--message", default=DEFAULT_CRON_MESSAGE)
        compat_parser.add_argument("crontab", nargs="*")
        args = compat_parser.parse_args(sys.argv[2:])
        _run_crontab(args)
        return

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

    cron_parser = subparsers.add_parser("crontab")
    cron_parser.add_argument("--config-dir", default=os.environ.get("OPENCLAW_CONFIG_DIR", "/root/.openclaw"))
    cron_parser.add_argument("--tz", default=os.environ.get("SAFRANO9999_ROUTINES_TZ", "Europe/Vienna"))
    cron_parser.add_argument("--crontab", nargs="+")
    cron_parser.add_argument("--message", default=DEFAULT_CRON_MESSAGE)

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
    elif args.command == "crontab":
        _run_crontab(args)


if __name__ == "__main__":
    main()
