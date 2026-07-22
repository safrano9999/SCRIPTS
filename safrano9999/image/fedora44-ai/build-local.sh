#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VARIANT="${1:-}"
NO_CACHE=false

if [ "$VARIANT" = --help ] || [ "$VARIANT" = -h ]; then
    echo "Usage: ./build-local.sh <base|safrano9999> [--no-cache]"
    exit 0
fi
[ "$VARIANT" = base ] || [ "$VARIANT" = safrano9999 ] || {
    echo "Usage: ./build-local.sh <base|safrano9999> [--no-cache]" >&2
    exit 2
}
case "${2:-}" in
    "") ;;
    --no-cache) NO_CACHE=true ;;
    *) echo "Unknown option: $2" >&2; exit 2 ;;
esac

command -v podman >/dev/null 2>&1 || {
    echo "Missing local build dependency: podman" >&2
    exit 1
}

ensure_ghcr_login() {
    local username

    podman login --get-login ghcr.io >/dev/null 2>&1 && return 0
    command -v gh >/dev/null 2>&1 || {
        echo "gh is required to authenticate to the private Base image" >&2
        return 1
    }
    username="$(gh api user --jq .login)"
    gh auth token | podman login ghcr.io --username "$username" --password-stdin
}

"$ROOT/prepare-build-context.sh"
set -a
# shellcheck source=/dev/null
. "$ROOT/build.conf"
set +a

for name in CERTS HERMES_TAG HERMES_COMMIT HERMES_VERSION ELECTRUM_VERSION LND_VERSION GETH_VERSION GETH_COMMIT WEBHOOK_VERSION; do
    [ -n "${!name:-}" ] || { echo "Missing $name in build.conf" >&2; exit 1; }
done
[ -s "$ROOT/.resolved-build.env" ] || { echo "Missing .resolved-build.env" >&2; exit 1; }

BUILD_ARGS=(
    --build-arg "CERTS=$CERTS"
    --build-arg "HERMES_TAG=$HERMES_TAG"
    --build-arg "HERMES_COMMIT=$HERMES_COMMIT"
    --build-arg "HERMES_VERSION=$HERMES_VERSION"
    --build-arg "ELECTRUM_VERSION=$ELECTRUM_VERSION"
    --build-arg "LND_VERSION=$LND_VERSION"
    --build-arg "GETH_VERSION=$GETH_VERSION"
    --build-arg "GETH_COMMIT=$GETH_COMMIT"
    --build-arg "WEBHOOK_VERSION=$WEBHOOK_VERSION"
)
while IFS='=' read -r key value; do
    [[ "$key" =~ ^[A-Z][A-Z0-9_]*$ ]] || {
        echo "Invalid resolved build argument: $key" >&2
        exit 1
    }
    BUILD_ARGS+=(--build-arg "$key=$value")
done < "$ROOT/.resolved-build.env"
$NO_CACHE && BUILD_ARGS+=(--no-cache)

case "$VARIANT" in
    base)
        TARGET=ai-base
        IMAGE=localhost/fedora44-ai-base:latest
        PULL_POLICY=always
        ;;
    safrano9999)
        TARGET=ai-safrano9999
        IMAGE=localhost/fedora44-ai-safrano9999:latest
        BASE_IMAGE="${AI_BASE_IMAGE:-ghcr.io/safrano9999/fedora44-ai-base:latest}"
        PULL_POLICY=always
        [[ "$BASE_IMAGE" != localhost/* ]] || PULL_POLICY=missing
        [[ "$BASE_IMAGE" != ghcr.io/* ]] || ensure_ghcr_login
        BUILD_ARGS+=(--build-arg "AI_BASE_IMAGE=$BASE_IMAGE")
        ;;
esac

echo "  Building $IMAGE from $ROOT ..."
podman build --pull="$PULL_POLICY" "${BUILD_ARGS[@]}" --target "$TARGET" -t "$IMAGE" -f "$ROOT/Containerfile" "$ROOT"
echo "  Done. Image ready: $IMAGE"
