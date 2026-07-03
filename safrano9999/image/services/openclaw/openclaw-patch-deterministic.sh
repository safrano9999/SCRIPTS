#!/usr/bin/env bash
set -euo pipefail

tag="${OPENCLAW_PATCH_TAG:-2026.6.11-deterministic.1}"
asset="${OPENCLAW_PATCH_ASSET:-openclaw-2026.6.11-deterministic-d0c7c00a.tar.gz}"
url="${OPENCLAW_PATCH_URL:-https://github.com/safrano9999/openclaw/releases/download/$tag}"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

curl -fsSL --retry 3 "$url/$asset" -o "$tmp/$asset"
curl -fsSL --retry 3 "$url/$asset.sha256" -o "$tmp/$asset.sha256"
(cd "$tmp" && sha256sum -c "$asset.sha256")
rm -rf /app/dist
tar -xzf "$tmp/$asset" -C /app
node /app/openclaw.mjs --version
