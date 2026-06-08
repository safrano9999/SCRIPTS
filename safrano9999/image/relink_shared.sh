#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
SAFRANO_DIR="$(dirname "$DIR")"
SCRIPTS_DIR="$(dirname "$SAFRANO_DIR")"
ROOT="$(dirname "$SCRIPTS_DIR")"
for file; do
    source="$(find "$SAFRANO_DIR" -type f -name "$file" -print -quit)"
    [ -n "$source" ] || { echo "Missing shared file: $file" >&2; exit 1; }
    while IFS= read -r -d '' target; do
        [ "$source" -ef "$target" ] || ln -f "$source" "$target"
    done < <(find "$ROOT" -path "$SCRIPTS_DIR" -prune -o -path '*/.git' -prune -o -type f -name "$file" -print0)
done
