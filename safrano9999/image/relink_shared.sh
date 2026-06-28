#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
SAFRANO_DIR="$(dirname "$DIR")"
SCRIPTS_DIR="$(dirname "$SAFRANO_DIR")"
ROOT="$(dirname "$SCRIPTS_DIR")"
declare -a EXTRA_ROOTS=()

while [ "$#" -gt 0 ]; do
    case "$1" in
        --extra-root)
            [ "$#" -ge 2 ] || { echo "--extra-root requires a path" >&2; exit 2; }
            EXTRA_ROOTS+=("$2")
            shift 2
            ;;
        --)
            shift
            break
            ;;
        *)
            break
            ;;
    esac
done

for file; do
    source="$(find "$SAFRANO_DIR" -type f -name "$file" -print -quit)"
    [ -n "$source" ] || { echo "Missing shared file: $file" >&2; exit 1; }
    while IFS= read -r -d '' target; do
        [ "$source" -ef "$target" ] || ln -f "$source" "$target" || exit 1
    done < <(find "$ROOT" -path "$SCRIPTS_DIR" -prune -o -path '*/.git' -prune -o -type f -name "$file" -print0)
    for extra_root in "${EXTRA_ROOTS[@]}"; do
        [ -d "$extra_root" ] || continue
        while IFS= read -r -d '' target; do
            [ "$source" -ef "$target" ] || ln -f "$source" "$target" || exit 1
        done < <(find "$extra_root" -type f -name "$file" -print0)
    done
done
