#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C

OUTPUT="${1:-.resolved-build.env}"
NODE_REQUESTED="${2:-stable}"
PATCH_DIR="${3:-openclaw-deterministic-patch}"
SOURCE_TAG_MANIFEST="${4:-.safrano9999-source-tags.tsv}"
BASE_SOURCE_TAG_MANIFEST="${5:-.fedora44-ai-base-source-tags.tsv}"

for command in curl git jq sha256sum; do
    command -v "$command" >/dev/null 2>&1 || {
        echo "Missing build resolver dependency: $command" >&2
        exit 1
    }
done

GH_AUTH_TOKEN="${GH_TOKEN:-${GITHUB_TOKEN:-}}"
if [ -z "$GH_AUTH_TOKEN" ] && command -v gh >/dev/null 2>&1 \
    && gh auth status --hostname github.com >/dev/null 2>&1; then
    GH_AUTH_TOKEN="$(gh auth token)"
fi

github_api() {
    local endpoint="$1"
    local -a headers=()
    [ -z "$GH_AUTH_TOKEN" ] || headers=(-H "Authorization: Bearer $GH_AUTH_TOKEN")
    curl -fsSL --retry 3 --connect-timeout 15 \
        -H 'Accept: application/vnd.github+json' \
        -H 'X-GitHub-Api-Version: 2022-11-28' \
        "${headers[@]}" "https://api.github.com${endpoint}"
}

npm_latest() {
    local package="$1" encoded
    encoded="$(jq -nr --arg package "$package" '$package | @uri')"
    curl -fsSL --retry 3 --connect-timeout 15 \
        "https://registry.npmjs.org/${encoded}/latest" | jq -er '.version'
}

fedora_repomd_hash() {
    local repo="$1"
    curl -fsSL --retry 3 --connect-timeout 15 \
        "https://mirrors.fedoraproject.org/metalink?repo=${repo}&arch=x86_64" \
        | sed -n 's#.*<hash type="sha256">\([^<]*\)</hash>.*#\1#p' \
        | head -n 1
}

require_match() {
    local name="$1" value="$2" pattern="$3"
    [[ "$value" =~ $pattern ]] || {
        echo "Invalid resolved value for $name: $value" >&2
        exit 1
    }
}

[ -s "$PATCH_DIR/openclaw.version" ] || {
    echo "Missing staged OpenClaw version: $PATCH_DIR/openclaw.version" >&2
    exit 1
}
[ -s "$SOURCE_TAG_MANIFEST" ] || {
    echo "Missing source tag manifest: $SOURCE_TAG_MANIFEST" >&2
    exit 1
}
[ -s "$BASE_SOURCE_TAG_MANIFEST" ] || {
    echo "Missing base source tag manifest: $BASE_SOURCE_TAG_MANIFEST" >&2
    exit 1
}
OPENCLAW_VERSION="$(tr -d '[:space:]' < "$PATCH_DIR/openclaw.version")"
SAFRANO9999_SOURCE_KEY="$(sha256sum "$SOURCE_TAG_MANIFEST" | cut -d' ' -f1)"
FEDORA44_AI_BASE_SOURCE_KEY="$(sha256sum "$BASE_SOURCE_TAG_MANIFEST" | cut -d' ' -f1)"

case "$NODE_REQUESTED" in
    stable|latest)
        NODE_VERSION="$(curl -fsSL --retry 3 --connect-timeout 15 \
            https://nodejs.org/dist/index.json | jq -er '.[0].version | ltrimstr("v")')"
        ;;
    *) NODE_VERSION="${NODE_REQUESTED#v}" ;;
esac

UV_RELEASE="$(github_api /repos/astral-sh/uv/releases/latest)"
UV_VERSION="$(jq -er '.tag_name | ltrimstr("v")' <<<"$UV_RELEASE")"
UV_INSTALLER_SHA256="$(curl -fsSL --retry 3 --connect-timeout 15 \
    "https://astral.sh/uv/${UV_VERSION}/install.sh" | sha256sum | cut -d' ' -f1)"

FEDORA_BASE_REPOMD="$(fedora_repomd_hash fedora-44)"
FEDORA_UPDATES_REPOMD="$(fedora_repomd_hash updates-released-f44)"
require_match FEDORA_BASE_REPOMD "$FEDORA_BASE_REPOMD" '^[0-9a-f]{64}$'
require_match FEDORA_UPDATES_REPOMD "$FEDORA_UPDATES_REPOMD" '^[0-9a-f]{64}$'
FEDORA_REPOMD_KEY="$(printf '%s\n%s\n' "$FEDORA_BASE_REPOMD" "$FEDORA_UPDATES_REPOMD" \
    | sha256sum | cut -d' ' -f1)"

SOLANA_INSTALLER_URL='https://release.anza.xyz/stable/agave-install-init-x86_64-unknown-linux-gnu'
SOLANA_INSTALLER_MD5="$(curl -fsSI --retry 3 --connect-timeout 15 "$SOLANA_INSTALLER_URL" \
    | awk -F': *' 'tolower($1) == "etag" {gsub(/"/, "", $2); sub(/\r$/, "", $2); print $2; exit}')"

FUGU_COMMIT="$(git ls-remote https://github.com/SakanaAI/fugu.git HEAD | awk 'NR == 1 {print $1}')"
ELECTRUM_KEYS_COMMIT="$(git ls-remote https://github.com/spesmilo/electrum.git refs/heads/master | awk 'NR == 1 {print $1}')"

CLOUDFLARED_RELEASE="$(github_api /repos/cloudflare/cloudflared/releases/latest)"
CLOUDFLARED_VERSION="$(jq -er '.tag_name' <<<"$CLOUDFLARED_RELEASE")"
CLOUDFLARED_SHA256="$(jq -er '.assets[] | select(.name == "cloudflared-linux-amd64") | .digest | sub("^sha256:"; "")' <<<"$CLOUDFLARED_RELEASE")"

NEXTCLOUD_PLUGIN_SHA256="$(curl -fsSL --retry 3 --connect-timeout 15 \
    https://github.com/safrano9999/NEXTCLOUD/releases/download/latest/nextcloud-fedora64-plugin-latest.zip.sha256 \
    | awk 'NR == 1 {print $1}')"

CODEX_VERSION="$(npm_latest @openai/codex)"
CLAUDE_CODE_VERSION="$(npm_latest @anthropic-ai/claude-code)"
OPENCLAW_BRAVE_PLUGIN_VERSION="$(npm_latest @openclaw/brave-plugin)"
OPENCLAW_CODEX_PLUGIN_VERSION="$(npm_latest @openclaw/codex)"

encoded_openclaw="$(jq -nr --arg package openclaw '$package | @uri')"
registry_openclaw="$(curl -fsSL --retry 3 --connect-timeout 15 \
    "https://registry.npmjs.org/${encoded_openclaw}/${OPENCLAW_VERSION}" | jq -er '.version')"
[ "$registry_openclaw" = "$OPENCLAW_VERSION" ] || {
    echo "Patch requires OpenClaw $OPENCLAW_VERSION, npm returned $registry_openclaw" >&2
    exit 1
}

require_match FEDORA_REPOMD_KEY "$FEDORA_REPOMD_KEY" '^[0-9a-f]{64}$'
require_match SAFRANO9999_SOURCE_KEY "$SAFRANO9999_SOURCE_KEY" '^[0-9a-f]{64}$'
require_match FEDORA44_AI_BASE_SOURCE_KEY "$FEDORA44_AI_BASE_SOURCE_KEY" '^[0-9a-f]{64}$'
require_match NODE_VERSION "$NODE_VERSION" '^[0-9]+([.][0-9]+){2}([._+-][A-Za-z0-9.-]+)?$'
require_match UV_VERSION "$UV_VERSION" '^[0-9]+([.][0-9]+){2}([._+-][A-Za-z0-9.-]+)?$'
require_match UV_INSTALLER_SHA256 "$UV_INSTALLER_SHA256" '^[0-9a-f]{64}$'
require_match SOLANA_INSTALLER_MD5 "$SOLANA_INSTALLER_MD5" '^[0-9a-f]{32}$'
require_match FUGU_COMMIT "$FUGU_COMMIT" '^[0-9a-f]{40}$'
require_match ELECTRUM_KEYS_COMMIT "$ELECTRUM_KEYS_COMMIT" '^[0-9a-f]{40}$'
require_match CLOUDFLARED_VERSION "$CLOUDFLARED_VERSION" '^[A-Za-z0-9._+-]+$'
require_match CLOUDFLARED_SHA256 "$CLOUDFLARED_SHA256" '^[0-9a-f]{64}$'
require_match NEXTCLOUD_PLUGIN_SHA256 "$NEXTCLOUD_PLUGIN_SHA256" '^[0-9a-f]{64}$'
require_match OPENCLAW_VERSION "$OPENCLAW_VERSION" '^[A-Za-z0-9._+-]+$'
require_match CODEX_VERSION "$CODEX_VERSION" '^[A-Za-z0-9._+-]+$'
require_match CLAUDE_CODE_VERSION "$CLAUDE_CODE_VERSION" '^[A-Za-z0-9._+-]+$'
require_match OPENCLAW_BRAVE_PLUGIN_VERSION "$OPENCLAW_BRAVE_PLUGIN_VERSION" '^[A-Za-z0-9._+-]+$'
require_match OPENCLAW_CODEX_PLUGIN_VERSION "$OPENCLAW_CODEX_PLUGIN_VERSION" '^[A-Za-z0-9._+-]+$'

temporary="${OUTPUT}.tmp"
{
    printf 'FEDORA_REPOMD_KEY=%s\n' "$FEDORA_REPOMD_KEY"
    printf 'SAFRANO9999_SOURCE_KEY=%s\n' "$SAFRANO9999_SOURCE_KEY"
    printf 'FEDORA44_AI_BASE_SOURCE_KEY=%s\n' "$FEDORA44_AI_BASE_SOURCE_KEY"
    printf 'NODE_VERSION=%s\n' "$NODE_VERSION"
    printf 'UV_VERSION=%s\n' "$UV_VERSION"
    printf 'UV_INSTALLER_SHA256=%s\n' "$UV_INSTALLER_SHA256"
    printf 'SOLANA_INSTALLER_MD5=%s\n' "$SOLANA_INSTALLER_MD5"
    printf 'FUGU_COMMIT=%s\n' "$FUGU_COMMIT"
    printf 'ELECTRUM_KEYS_COMMIT=%s\n' "$ELECTRUM_KEYS_COMMIT"
    printf 'CLOUDFLARED_VERSION=%s\n' "$CLOUDFLARED_VERSION"
    printf 'CLOUDFLARED_SHA256=%s\n' "$CLOUDFLARED_SHA256"
    printf 'NEXTCLOUD_PLUGIN_SHA256=%s\n' "$NEXTCLOUD_PLUGIN_SHA256"
    printf 'OPENCLAW_VERSION=%s\n' "$OPENCLAW_VERSION"
    printf 'CODEX_VERSION=%s\n' "$CODEX_VERSION"
    printf 'CLAUDE_CODE_VERSION=%s\n' "$CLAUDE_CODE_VERSION"
    printf 'OPENCLAW_BRAVE_PLUGIN_VERSION=%s\n' "$OPENCLAW_BRAVE_PLUGIN_VERSION"
    printf 'OPENCLAW_CODEX_PLUGIN_VERSION=%s\n' "$OPENCLAW_CODEX_PLUGIN_VERSION"
} > "$temporary"
mv -f "$temporary" "$OUTPUT"
printf 'Resolved immutable build inputs -> %s\n' "$OUTPUT"
