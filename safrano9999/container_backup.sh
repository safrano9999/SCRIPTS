#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
INSTANCES="$ROOT/CONTAINER"
[ "$#" -eq 0 ] || { echo "container_backup.sh accepts no arguments; edit container_backup.env." >&2; exit 2; }
CONFIG="${CONTAINER_BACKUP_CONFIG:-$ROOT/container_backup.env}"
[ -f "$CONFIG" ] || cp "$ROOT/container_backup.env_example" "$CONFIG"
set -a
. "$CONFIG"
set +a
TARGET="${CONTAINER_BACKUP_TARGET:-}"
SECRET_FILE="${CONTAINER_BACKUP_SECRET_FILE:-}"
CIPHER="${CONTAINER_BACKUP_CIPHER:-AES256}"

[ -n "$TARGET" ] || { echo "Set CONTAINER_BACKUP_TARGET in $CONFIG." >&2; exit 2; }
[ -d "$TARGET" ] || { echo "Backup target does not exist: $TARGET" >&2; exit 2; }
[ "$(findmnt -n -o TARGET -T "$TARGET")" != "/" ] || { echo "Backup target is not a mounted external filesystem: $TARGET" >&2; exit 2; }
[ -s "$SECRET_FILE" ] || { echo "Missing CONTAINER_BACKUP_SECRET_FILE: $SECRET_FILE" >&2; exit 2; }
MODE="$(stat -c '%a' "$SECRET_FILE")"
[ $((8#$MODE & 8#077)) -eq 0 ] || { echo "Secret file must have mode 0600: $SECRET_FILE" >&2; exit 2; }
mapfile -t INSTANCE_DIRS < <(find "$INSTANCES" -mindepth 1 -maxdepth 1 -type d | sort)
[ "${#INSTANCE_DIRS[@]}" -gt 0 ] || { echo "No instances found in $INSTANCES" >&2; exit 2; }

TMP="$(mktemp -d)"
PAUSED=""
cleanup() { [ -z "$PAUSED" ] || podman unpause "$PAUSED" >/dev/null 2>&1 || true; rm -rf "$TMP"; }
trap cleanup EXIT
mkdir -p "$TMP/payload/volumes"
mkdir -p "$TMP/payload/CONTAINER"
declare -A EXPORTED=()

for instance in "${INSTANCE_DIRS[@]}"; do
    name="$(basename "$instance")"
    mkdir -p "$TMP/payload/CONTAINER/$name"
    for file in "$name.env" "${name}_config.conf" "${name}_container.conf"; do
        [ ! -f "$instance/$file" ] || cp -a "$instance/$file" "$TMP/payload/CONTAINER/$name/"
    done
    quadlet="$instance/$name.container"
    [ -f "$quadlet" ] || continue
    if [ "$(podman inspect -f '{{.State.Status}}' "$name" 2>/dev/null || true)" = running ]; then
        podman pause "$name" >/dev/null
        PAUSED="$name"
    fi
    while IFS= read -r volume; do
        [ -n "$volume" ] && [ -z "${EXPORTED[$volume]:-}" ] || continue
        podman volume exists "$volume" || { echo "Missing volume: $volume" >&2; exit 2; }
        echo "Exporting $volume"
        podman volume export -o "$TMP/payload/volumes/$volume.tar" "$volume"
        EXPORTED[$volume]=1
    done < <(awk -F'[=:]' '/^Volume=/ && $2 !~ /^\// && $2 !~ /^\./ && $2 !~ /\// {print $2}' "$quadlet" | sort -u)
    [ -z "$PAUSED" ] || podman unpause "$PAUSED" >/dev/null
    PAUSED=""
done

STAMP="$(date +%Y%m%d-%H%M%S)"
ARCHIVE="$TMP/$(basename "$ROOT")-$STAMP.tar.gz.gpg"
tar -C "$TMP/payload" -czf - . | gpg --batch --yes --pinentry-mode loopback --passphrase-fd 3 \
    --symmetric --cipher-algo "$CIPHER" --output "$ARCHIVE" 3<"$SECRET_FILE"
sha256sum "$ARCHIVE" > "$ARCHIVE.sha256"
rsync -ah --info=progress2 "$ARCHIVE" "$ARCHIVE.sha256" "$TARGET/"
echo "Backup written: $TARGET/$(basename "$ARCHIVE")"
