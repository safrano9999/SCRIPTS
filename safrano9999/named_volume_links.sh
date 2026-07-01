#!/usr/bin/env bash
set -euo pipefail

IFS=';' read -ra specs <<< "${NAMED_VOLUME_LINKS:-}"
declare -A package_roots=() package_blocked=() explicit_sources=()

resolve_target() {
    local target="$1" variable
    if [[ "$target" =~ ^@([A-Za-z_][A-Za-z0-9_]*)@(.*)$ ]]; then
        variable="${BASH_REMATCH[1]}"
        [ -n "${!variable:-}" ] || { echo "Missing $variable for named-volume target" >&2; exit 1; }
        target="${!variable}${BASH_REMATCH[2]}"
    fi
    printf '%s\n' "$target"
}

link_path() {
    local source="$1" target="$2"
    case "${source##*/}" in *.db-wal|*.db-shm|*.lock|*.pid) return 0 ;; esac
    mkdir -p "$(dirname "$target")"
    rm -rf "$target"
    ln -s "$source" "$target"
}

has_explicit_descendant() {
    local source="$1" explicit
    for explicit in "${!explicit_sources[@]}"; do [[ "$explicit" == "$source/"* ]] && return 0; done
    return 1
}

link_package_path() {
    local source="$1" target="$2" child
    if [ -d "$source" ] && has_explicit_descendant "$source"; then
        mkdir -p "$target"
        for child in "$source"/*; do [ ! -e "$child" ] || link_package_path "$child" "$target/${child##*/}"; done
    else
        link_path "$source" "$target"
    fi
}

for spec in "${specs[@]}"; do
    IFS='|' read -r mount source target kind <<< "$spec"
    [ -n "$source" ] && [ -n "$target" ] || continue
    target="$(resolve_target "$target")"
    explicit_sources[$source]=1
    if [ "$source" = "$mount" ]; then
        package_blocked[$mount]=1
    elif [[ "$source" == "$mount/"* ]]; then
        relative="${source#"$mount/"}"
        suffix="/$relative"
        if [[ "$target" == *"$suffix" ]]; then
            root="${target%"$suffix"}"
            if [ -n "${package_roots[$mount]:-}" ] && [ "${package_roots[$mount]}" != "$root" ]; then
                package_blocked[$mount]=1
            else
                package_roots[$mount]="$root"
            fi
        else
            package_blocked[$mount]=1
        fi
    fi
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

shopt -s nullglob dotglob
for mount in "${!package_roots[@]}"; do
    [ -z "${package_blocked[$mount]:-}" ] || continue
    for source in "$mount"/*; do
        link_package_path "$source" "${package_roots[$mount]}/${source##*/}"
    done
done
