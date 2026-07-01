#!/usr/bin/env bash
set -euo pipefail

IFS=';' read -ra specs <<< "${NAMED_VOLUME_LINKS:-}"
for spec in "${specs[@]}"; do
    IFS='|' read -r _ source target kind <<< "$spec"
    [ -n "$source" ] && [ -n "$target" ] || continue
    if [ -z "$kind" ]; then
        if [ -f "$source" ] || [ -f "$target" ]; then kind=file; else kind=dir; fi
    fi
    mkdir -p "$(dirname "$source")"
    mkdir -p "$(dirname "$target")"
    if [ "$kind" = file ]; then
        if [ ! -e "$source" ]; then
            if [ -f "$target" ] && [ ! -L "$target" ]; then mv "$target" "$source"; else install -m 0600 /dev/null "$source"; fi
        fi
        rm -rf "$target"
        ln -sfn "$source" "$target"
    else
        mkdir -p "$source"
        if [ -d "$target" ] && [ ! -L "$target" ] && [ -z "$(find "$source" -mindepth 1 -print -quit)" ]; then
            cp -a "$target"/. "$source"/
        fi
        rm -rf "$target"
        ln -s "$source" "$target"
    fi
done
