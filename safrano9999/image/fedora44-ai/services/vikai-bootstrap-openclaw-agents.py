#!/usr/bin/env python3
"""Provision the three VikAI OpenClaw agents from runtime tokens."""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path


CONFIG_PATH = Path(
    os.environ.get(
        "OPENCLAW_CONFIG",
        os.environ.get("OPENCLAW_CONFIG_PATH", "/root/.openclaw/openclaw.json"),
    )
)
STATE_DIR = Path(os.environ.get("OPENCLAW_STATE_DIR", str(CONFIG_PATH.parent)))
VIKAI_DIR = Path(os.environ.get("VIKAI_DIR", "/opt/safrano9999/VikAI"))
TEMPLATE_DIR = VIKAI_DIR / "openclaw-workspace"
SKILLS_DIR = VIKAI_DIR / "SKILLS"
VIKUNJA_CLIENT = VIKAI_DIR / "vikunja_client.py"
HEARTBEAT_EVERY = os.environ.get("VIKAI_HEARTBEAT_EVERY", "360m").strip() or "360m"


AGENTS = [
    {
        "id": "worker",
        "role": "worker",
        "token_env": "TOKEN_WORKER",
        "template": "worker",
        "skill_dir": "vikunja_worker",
        "role_skills": ["VikAI_Worker.md"],
    },
    {
        "id": "architect",
        "role": "architect",
        "token_env": "TOKEN_ARCHITECT",
        "template": "architect",
        "skill_dir": "vikunja_architect",
        "role_skills": ["VikAI_Architect.md", "VikAI_Architect_Briefing.md"],
    },
    {
        "id": "qc",
        "role": "qc",
        "token_env": "TOKEN_QC",
        "template": "qc",
        "skill_dir": "vikunja_qc",
        "role_skills": ["VikAI_QA.md"],
    },
]


def require_tokens() -> dict[str, str]:
    tokens = {}
    missing = []
    for agent in AGENTS:
        name = agent["token_env"]
        value = os.environ.get(name, "").strip()
        if value:
            tokens[agent["id"]] = value
        else:
            missing.append(name)
    if missing:
        raise SystemExit(f"Missing VikAI token variables: {', '.join(missing)}")
    return tokens


def vikunja_target() -> str:
    explicit = os.environ.get("VIKUNJA_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")
    host = os.environ.get("VIKUNJA_HOST", "localhost").strip() or "localhost"
    return f"{host}:641"


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise SystemExit(f"OpenClaw config not found: {CONFIG_PATH}")
    with CONFIG_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def save_config(config: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CONFIG_PATH.open("w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def ensure_agent_config(config: dict, agent: dict) -> Path:
    agents = config.setdefault("agents", {})
    agents.setdefault("defaults", {}).setdefault("workspace", str(STATE_DIR / "workspace"))
    agent_list = agents.setdefault("list", [])
    agent_id = agent["id"]
    entry = next(
        (item for item in agent_list if isinstance(item, dict) and item.get("id") == agent_id),
        None,
    )
    if entry is None:
        entry = {"id": agent_id, "name": agent_id}
        agent_list.append(entry)

    workspace = Path(entry.get("workspace") or STATE_DIR / f"workspace-{agent_id}")
    agent_dir = Path(entry.get("agentDir") or STATE_DIR / "agents" / agent_id / "agent")
    entry["name"] = entry.get("name") or agent_id
    entry["workspace"] = str(workspace)
    entry["agentDir"] = str(agent_dir)
    entry["heartbeat"] = {
        "every": HEARTBEAT_EVERY,
        "target": "last",
        "directPolicy": "allow",
    }
    agent_dir.mkdir(parents=True, exist_ok=True)
    return workspace


def write_secret(path: Path, value: str) -> None:
    path.write_text(value + "\n", encoding="utf-8")
    path.chmod(0o600)


def replace_symlink(link: Path, target: Path) -> None:
    if link.exists() or link.is_symlink():
        link.unlink()
    link.symlink_to(target)


def copy_workspace_template(agent: dict, workspace: Path) -> None:
    template = TEMPLATE_DIR / agent["template"]
    if not template.is_dir():
        raise SystemExit(f"VikAI workspace template not found: {template}")
    shutil.copytree(template, workspace, dirs_exist_ok=True, symlinks=True)


def write_workspace(agent: dict, token: str, workspace: Path, target: str) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    copy_workspace_template(agent, workspace)
    (workspace / "memory").mkdir(exist_ok=True)
    (workspace / "SKILLS").mkdir(exist_ok=True)
    (workspace / "BOOTSTRAP.md").unlink(missing_ok=True)

    (workspace / ".vikai_role").write_text(agent["role"] + "\n", encoding="utf-8")
    write_secret(workspace / ".vikunjaenv", token)

    state_file = workspace / ".openclaw" / "workspace-state.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    if not state_file.exists():
        now = datetime.now(timezone.utc).isoformat()
        state_file.write_text(
            json.dumps(
                {
                    "version": 1,
                    "bootstrapSeededAt": now,
                    "setupCompletedAt": now,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    skill_dir = workspace / "SKILLS" / agent["skill_dir"]
    skill_dir.mkdir(parents=True, exist_ok=True)
    replace_symlink(skill_dir / "VikAI.md", SKILLS_DIR / "VikAI.md")
    for skill_name in agent["role_skills"]:
        replace_symlink(skill_dir / skill_name, SKILLS_DIR / skill_name)
    write_secret(skill_dir / ".vikunjaenv", token)
    (skill_dir / "TOKEN_INFO.md").write_text(
        f"# VikAI Token Info - {agent['id']}\n\n"
        f"API token: `.vikunjaenv` (this directory)\n"
        f"Vikunja API target: `{target}`\n"
        f"Client: `{VIKUNJA_CLIENT}`\n",
        encoding="utf-8",
    )


def main() -> None:
    tokens = require_tokens()
    config = load_config()
    target = vikunja_target()
    for agent in AGENTS:
        workspace = ensure_agent_config(config, agent)
        write_workspace(agent, tokens[agent["id"]], workspace, target)
    save_config(config)
    print("VikAI OpenClaw agents provisioned: worker, architect, qc")


if __name__ == "__main__":
    main()
