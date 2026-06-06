#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(dirname "$DIR")"
for file; do
    source="$(find "$DIR" -type f -name "$file" -print -quit)"
    while IFS= read -r -d '' target; do
        [ "$source" -ef "$target" ] || ln -f "$source" "$target"
    done < <(find "$ROOT" -path "$DIR" -prune -o -path '*/.git' -prune -o -type f -name "$file" -print0)
done
