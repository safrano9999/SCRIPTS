#!/usr/bin/env bash
set -euo pipefail

IFS=';' read -ra specs <<< "${NAMED_VOLUME_LINKS:-}"
for spec in "${specs[@]}"; do
    IFS='|' read -r _ source target <<< "$spec"
    [ -n "$source" ] && [ -n "$target" ] || continue
    mkdir -p "$(dirname "$target")"
    if [ -f "$source" ]; then
        ln -sfn "$source" "$target"
    elif [ -d "$source" ]; then
        rm -rf "$target"
        ln -s "$source" "$target"
    fi
done
