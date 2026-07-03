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
rm -rf /app/dist
tar -xzf "$tmp/$archive" -C /app
node /app/openclaw.mjs --version
openclaw config set agents.defaults.models '{"dummy/dummy":{},"dummy/note":{}}' --strict-json --replace
openclaw config set agents.defaults.model.primary '"dummy/dummy"' --strict-json
