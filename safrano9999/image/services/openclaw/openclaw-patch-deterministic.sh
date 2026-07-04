#!/usr/bin/env bash
set -euo pipefail

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
releases="$(curl -fsSL --retry 3 'https://api.github.com/repos/safrano9999/openclaw/releases?per_page=100')"
IFS=$'\t' read -r archive_url checksum_url < <(jq -r 'first(.[] | select(.draft == false) | .assets as $assets | ($assets[] | select(.name | test("^openclaw-.*-deterministic-.*\\.tar\\.gz$"))) as $archive | ($assets[] | select(.name == ($archive.name + ".sha256"))) as $checksum | [$archive.browser_download_url, $checksum.browser_download_url] | @tsv)' <<<"$releases")
archive="${archive_url##*/}"
curl -fsSL --retry 3 "$archive_url" -o "$tmp/$archive"
curl -fsSL --retry 3 "$checksum_url" -o "$tmp/$archive.sha256"
(cd "$tmp" && sha256sum -c "$archive.sha256")
openclaw_root="$(dirname "$(readlink -f "$(command -v openclaw)")")"
[ -f "$openclaw_root/openclaw.mjs" ] || { echo "OpenClaw root not found: $openclaw_root" >&2; exit 1; }
rm -rf "$openclaw_root/dist"
tar -xzf "$tmp/$archive" -C "$openclaw_root"
node "$openclaw_root/openclaw.mjs" --version
models="$(openclaw config get agents.defaults.models --json 2>/dev/null || printf '{}\n')"
models="$(jq -c 'if type == "object" then . else {} end | . + {"dummy/dummy": {}, "dummy/note": {}}' <<<"$models")"
openclaw config set agents.defaults.models "$models" --strict-json
if ! openclaw config get agents.defaults.model.primary --json 2>/dev/null \
    | jq -e 'type == "string" and length > 0' >/dev/null; then
    openclaw config set agents.defaults.model.primary '"dummy/dummy"' --strict-json
fi
