#!/usr/bin/env python3
"""Configure Hermes from one or more OpenAI-compatible v1 providers."""

import os
import shutil
from pathlib import Path

import yaml

from openclaw_common import (
    discover_openai_v1_runtime_providers,
    select_openai_v1_model,
)


DEFAULT_MODEL = "gemini/gemini-3.5-flash"
DEFAULT_HOME = "/root/.hermes"
DEFAULT_INSTALL_DIR = "/usr/local/lib/hermes-agent"


def _ensure_config(config_path: Path) -> None:
    if config_path.exists():
        return

    example_path = Path(DEFAULT_INSTALL_DIR) / "cli-config.yaml.example"
    if example_path.exists():
        shutil.copyfile(example_path, config_path)
        return

    config_path.write_text("model:\n  provider: openai_v1\n", encoding="utf-8")


def main() -> None:
    hermes_home = Path(DEFAULT_HOME)
    hermes_home.mkdir(parents=True, exist_ok=True)
    config_path = hermes_home / "config.yaml"
    _ensure_config(config_path)

    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(config, dict):
        config = {}

    configured_model = os.environ.get(
        "HERMES_MODEL",
        DEFAULT_MODEL,
    ).strip()
    providers = discover_openai_v1_runtime_providers(consumer="Hermes")
    selected_provider, selected_model = select_openai_v1_model(providers, configured_model)

    model_config = config.setdefault("model", {})
    if not isinstance(model_config, dict):
        model_config = {}
        config["model"] = model_config

    model_config["provider"] = selected_provider.provider_id
    model_config["default"] = selected_model
    model_config["base_url"] = selected_provider.config.base_url
    model_config["ssl_verify"] = True
    selected_models = list(selected_provider.models)
    if selected_model not in selected_models:
        selected_models.insert(0, selected_model)
    model_config["available"] = selected_models
    model_config.pop("api_key", None)

    providers_config = config.setdefault("providers", {})
    if not isinstance(providers_config, dict):
        providers_config = {}
        config["providers"] = providers_config

    for provider in providers:
        model_ids = list(provider.models)
        if provider == selected_provider and selected_model not in model_ids:
            model_ids.insert(0, selected_model)
        provider_config = {
            "name": provider.config.provider or provider.provider_id,
            "base_url": provider.config.base_url,
            "key_env": provider.key_env,
            "api_mode": "chat_completions",
            "models": {name: {} for name in model_ids},
        }
        if model_ids:
            provider_config["default_model"] = (
                selected_model if provider == selected_provider else model_ids[0]
            )
        providers_config[provider.provider_id] = provider_config

    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    os.chmod(config_path, 0o600)
    print(
        "Hermes OpenAI v1 model configured: "
        f"{selected_provider.provider_id}/{selected_model}"
    )
    print(f"Hermes OpenAI v1 providers configured: {len(providers)}")


if __name__ == "__main__":
    main()
