#!/usr/bin/env bash
set -euo pipefail

# === Configuration ==========================================================
OPENCLAW_HOME="${OPENCLAW_HOME:-/home/openclaw/.openclaw}"
BACKUP_REPO="${BACKUP_REPO:-/home/openclaw/openclaw-agent-backups}"
TARGET_CHAT="${TARGET_CHAT:-5475045993}"
AGENT_LABEL="${AGENT_LABEL:-america}"  # Used in the notification text
JSON_DIRS=(logs sessions memory completions)
TAR_CMD=${TAR_CMD:-tar}
GIT_NAME=${GIT_NAME:-openclaw-backup}
GIT_EMAIL=${GIT_EMAIL:-openclaw-backup@localhost}
# ===========================================================================

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

require() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

require jq
require "$TAR_CMD"
require git
require openclaw

TIMESTAMP="$(date -u '+%Y%m%d-%H%M%S')"
BACKUP_DIR="$BACKUP_REPO/$TIMESTAMP"
MANIFEST="$BACKUP_DIR/manifest.json"
mkdir -p "$BACKUP_DIR" "$BACKUP_DIR/workspaces" "$BACKUP_DIR/json"

if [ ! -f "$OPENCLAW_HOME/openclaw.json" ]; then
  echo "openclaw.json not found in $OPENCLAW_HOME" >&2
  exit 1
fi

log "Copying openclaw.json"
cp "$OPENCLAW_HOME/openclaw.json" "$BACKUP_DIR/openclaw.json"

log "Collecting session/log JSON files"
declare -a COPIED_JSON=()
for dir in "${JSON_DIRS[@]}"; do
  SRC="$OPENCLAW_HOME/$dir"
  DEST="$BACKUP_DIR/json/$dir"
  if [ -d "$SRC" ]; then
    mkdir -p "$DEST"
    while IFS= read -r -d '' file; do
      rel="${file#"$SRC/"}"
      mkdir -p "$DEST/$(dirname "$rel")"
      cp "$file" "$DEST/$rel"
      COPIED_JSON+=("$dir/$rel")
    done < <(find "$SRC" -type f \( -name '*.json' -o -name '*.jsonl' \) -print0)
  fi
done

log "Archiving agent workspaces"
AGENT_COUNT=0
WORKSPACE_ERRORS=0
declare -a ARCHIVED_AGENTS=()
mapfile -t AGENT_LINES < <(jq -r '.agents.list[] | select(.workspace != null) | [.id, .workspace] | @tsv' "$OPENCLAW_HOME/openclaw.json")
for line in "${AGENT_LINES[@]}"; do
  agent_id=${line%%$'\t'*}
  workspace_path=${line#*$'\t'}
  [ -z "$workspace_path" ] && continue
  agent_key=${agent_id:-unknown}
  safe_name=$(echo "$agent_key" | tr '/ ' '__')
  archive="$BACKUP_DIR/workspaces/${safe_name}.tar.zst"
  if [ ! -d "$workspace_path" ]; then
    log "[warn] Workspace missing for agent $agent_key: $workspace_path"
    WORKSPACE_ERRORS=$((WORKSPACE_ERRORS + 1))
    continue
  fi
  log "  → $agent_key ($workspace_path)"
  "$TAR_CMD" --zstd -cf "$archive" -C "$workspace_path" .
  AGENT_COUNT=$((AGENT_COUNT + 1))
  ARCHIVED_AGENTS+=("$agent_key")
done

if [ ${#COPIED_JSON[@]} -gt 0 ]; then
  JSON_LIST=$(printf '%s\n' "${COPIED_JSON[@]}" | jq -R . | jq -s -c .)
else
  JSON_LIST='[]'
fi

if [ ${#ARCHIVED_AGENTS[@]} -gt 0 ]; then
  AGENT_LIST_JSON=$(printf '%s\n' "${ARCHIVED_AGENTS[@]}" | jq -R . | jq -s -c .)
  AGENT_LIST_STRING=$(printf '%s\n' "${ARCHIVED_AGENTS[@]}" | paste -sd ', ' -)
else
  AGENT_LIST_JSON='[]'
  AGENT_LIST_STRING='(none)'
fi

log "Writing manifest"
cat >"$MANIFEST" <<MANIFEST
{
  "timestamp": "$TIMESTAMP",
  "agent_label": "$AGENT_LABEL",
  "openclaw_home": "$OPENCLAW_HOME",
  "agents_archived": $AGENT_COUNT,
  "workspace_errors": $WORKSPACE_ERRORS,
  "json_files": $JSON_LIST,
  "agent_names": $AGENT_LIST_JSON
}
MANIFEST

log "Checkpointing backup repo"
mkdir -p "$BACKUP_REPO"
if [ ! -d "$BACKUP_REPO/.git" ]; then
  (cd "$BACKUP_REPO" && git init >/dev/null)
fi
git -C "$BACKUP_REPO" config user.name "$GIT_NAME"
git -C "$BACKUP_REPO" config user.email "$GIT_EMAIL"
git -C "$BACKUP_REPO" add "$TIMESTAMP"
CHANGES=1
if git -C "$BACKUP_REPO" diff --cached --quiet; then
  CHANGES=0
else
  git -C "$BACKUP_REPO" commit -m "Agent backup $AGENT_LABEL $TIMESTAMP" >/dev/null
fi

if git -C "$BACKUP_REPO" rev-parse --verify HEAD >/dev/null 2>&1; then
  BACKUP_ID=$(git -C "$BACKUP_REPO" rev-parse --short HEAD)
else
  BACKUP_ID="no-commit"
fi

if [ $CHANGES -eq 0 ]; then
  STATUS_MSG="no changes (last id $BACKUP_ID)"
else
  STATUS_MSG="with id $BACKUP_ID"
fi

MESSAGE="backup finished, all those agents were backuped for agent $AGENT_LABEL $STATUS_MSG (agents: $AGENT_LIST_STRING)"
# log "Sending notification"
# openclaw message send --target "$TARGET_CHAT" --message "$MESSAGE"
log "All done"
