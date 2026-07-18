#!/usr/bin/env python3
"""Patch OpenClaw /models browse to avoid blocking on slow read-only catalog loads."""

from __future__ import annotations

import os
import re
from pathlib import Path


DIST_DIR = Path(
    os.environ.get("OPENCLAW_DIST_DIR", "/usr/local/lib/node_modules/openclaw/dist")
)
TIMEOUT_MS = 750


def _commands_models_file() -> Path:
    candidates = sorted(DIST_DIR.glob("commands-models-*.js"))
    for path in candidates:
        text = path.read_text(encoding="utf-8")
        if "async function buildModelsProviderData" in text:
            return path
    raise SystemExit(f"OpenClaw commands-models dist file not found in {DIST_DIR}")


def _patch_model_selection_shared_import(text: str) -> str:
    pattern = re.compile(
        r'import \{ (?P<members>[^}]*resolveBareModelDefaultProvider[^}]*) \} '
        r'from "(?P<module>\./model-selection-shared-[^"]+\.js)";'
    )
    match = pattern.search(text)
    if not match:
        raise SystemExit("OpenClaw patch failed: model-selection-shared import not found")
    members = match.group("members")
    if "parseConfiguredModelVisibilityEntries" in members:
        return text
    members = members.replace(
        "resolveBareModelDefaultProvider,",
        "resolveBareModelDefaultProvider, f as parseConfiguredModelVisibilityEntries,",
        1,
    )
    replacement = f'import {{ {members} }} from "{match.group("module")}";'
    return text[: match.start()] + replacement + text[match.end() :]


def _patch_timeout_const(text: str) -> str:
    if "MODELS_COMMAND_CATALOG_TIMEOUT_MS" in text:
        return text
    marker = "const PAGE_SIZE_MAX = 100;\n"
    if marker not in text:
        raise SystemExit("OpenClaw patch failed: PAGE_SIZE_MAX marker not found")
    return text.replace(
        marker,
        f"{marker}const MODELS_COMMAND_CATALOG_TIMEOUT_MS = {TIMEOUT_MS};\n",
        1,
    )


def _patch_catalog_helper(text: str) -> str:
    if "async function loadModelsCommandCatalog" in text:
        return text
    marker = (
        "function addRuntimeChoice(choices, choice) {\n"
        "\tif (!choices.some((existing) => existing.id === choice.id)) choices.push(choice);\n"
        "\treturn choices;\n"
        "}\n"
    )
    if marker not in text:
        raise SystemExit("OpenClaw patch failed: addRuntimeChoice marker not found")
    helper = (
        "async function loadModelsCommandCatalog(cfg, view) {\n"
        '\tif (view === "all") return await loadModelCatalog({ config: cfg, readOnly: false });\n'
        "\tif (parseConfiguredModelVisibilityEntries({ cfg }).providerWildcards.size > 0) "
        "return await loadModelCatalog({ config: cfg, readOnly: false });\n"
        "\tlet timeout;\n"
        '\tconst timedOut = Symbol("models-command-catalog-timeout");\n'
        "\tconst catalogPromise = loadModelCatalog({ config: cfg, readOnly: true });\n"
        "\tconst timeoutPromise = new Promise((resolve) => {\n"
        "\t\ttimeout = setTimeout(() => resolve(timedOut), MODELS_COMMAND_CATALOG_TIMEOUT_MS);\n"
        "\t\ttimeout.unref?.();\n"
        "\t});\n"
        "\ttry {\n"
        "\t\tconst result = await Promise.race([catalogPromise, timeoutPromise]);\n"
        "\t\tif (result === timedOut) {\n"
        "\t\t\tcatalogPromise.catch(() => void 0);\n"
        "\t\t\treturn [];\n"
        "\t\t}\n"
        "\t\treturn result;\n"
        "\t} finally {\n"
        "\t\tif (timeout) clearTimeout(timeout);\n"
        "\t}\n"
        "}\n"
    )
    return text.replace(marker, marker + helper, 1)


def _patch_catalog_load(text: str) -> str:
    replacement = (
        'const catalog = await loadModelsCommandCatalog(cfg, options.view ?? "default");'
    )
    if replacement in text:
        return text
    patterns = [
        "const catalog = await loadModelCatalog({ config: cfg });",
        (
            "const catalog = await loadModelCatalog({\n"
            "\t\tconfig: cfg,\n"
            '\t\treadOnly: options.view !== "all"\n'
            "\t});"
        ),
    ]
    for pattern in patterns:
        if pattern in text:
            return text.replace(pattern, replacement, 1)
    raise SystemExit("OpenClaw patch failed: catalog load marker not found")


def _patch_runtime_discovery(text: str) -> str:
    if "runtimeAuthDiscovery: false" in text:
        return text
    marker = "\t\tview: options.view\n\t});"
    if marker not in text:
        raise SystemExit("OpenClaw patch failed: visible catalog marker not found")
    return text.replace(marker, "\t\tview: options.view,\n\t\truntimeAuthDiscovery: false\n\t});", 1)


def main() -> None:
    path = _commands_models_file()
    original = path.read_text(encoding="utf-8")
    patched = original
    patched = _patch_model_selection_shared_import(patched)
    patched = _patch_timeout_const(patched)
    patched = _patch_catalog_helper(patched)
    patched = _patch_catalog_load(patched)
    patched = _patch_runtime_discovery(patched)
    if patched == original:
        print(f"OpenClaw /models command patch already applied: {path.name}")
        return
    path.write_text(patched, encoding="utf-8")
    print(f"OpenClaw /models command patch applied: {path.name}")


if __name__ == "__main__":
    main()
