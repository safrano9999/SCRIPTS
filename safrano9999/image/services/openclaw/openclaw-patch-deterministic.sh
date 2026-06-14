#!/usr/bin/env bash
# Build a patched OpenClaw dist from the safrano9999 fork.
#
# Carries upstream PR openclaw/openclaw#91217 (deterministic dummy/dummy
# gateway model + credential-free model check) on top of the stable release
# matching the official gateway base image. Runs in a dedicated build stage;
# the resulting dist is copied over /app in the final image.
set -euo pipefail

REPO="${OPENCLAW_PATCH_REPO:-https://github.com/safrano9999/openclaw.git}"
REF="${OPENCLAW_PATCH_REF:-patch/v2026.6.5-deterministic}"
SRC="${OPENCLAW_PATCH_SRC:-/opt/openclaw-patch-src}"

echo "Cloning ${REPO} (${REF}, depth 1) -> ${SRC}"
git clone --depth 1 --branch "$REF" "$REPO" "$SRC"
cd "$SRC"

corepack enable
# Large optional binary tarballs (codex, copilot, lancedb, ...) exceed pnpm's
# default fetch timeout on slow links; raise limits instead of failing builds.
corepack pnpm install --fetch-timeout 600000 --fetch-retries 5 --network-concurrency 8
corepack pnpm build

# The version probe loads the freshly built dist; it fails if the build is unusable.
node "$SRC/openclaw.mjs" --version
echo "Patched OpenClaw dist ready: ${SRC}/dist"
