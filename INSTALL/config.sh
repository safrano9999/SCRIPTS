#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/env.example" ] || [ -f "$SCRIPT_DIR/config.conf_example" ]; then
    DIR="$SCRIPT_DIR"
else
    DIR="$(pwd)"
fi

PROJECT_NAME="$(basename "$DIR")"

configure_from_example() {
    local example="$1"
    local target="$2"
    local label="$3"

    [ -f "$example" ] || return 0

    echo ""
    echo "  Configuring $label"
    echo ""

    touch "$target"
    declare -A seen_keys=()
    local required_next=false

    while IFS= read -r line <&3; do
        stripped="${line#"${line%%[![:space:]]*}"}"
        if [[ "$stripped" == \#required:* ]]; then
            required_next=true
            continue
        fi
        if [[ -z "$stripped" || "$stripped" == \#* ]]; then
            required_next=false
            continue
        fi
        required="$required_next"
        required_next=false

        entry="${line%%#*}"
        entry="${entry#"${entry%%[![:space:]]*}"}"
        entry="${entry%"${entry##*[![:space:]]}"}"
        [[ "$entry" != *=* ]] && continue

        key="${entry%%=*}"
        default="${entry#*=}"
        key="${key#"${key%%[![:space:]]*}"}"
        key="${key%"${key##*[![:space:]]}"}"
        default="${default#"${default%%[![:space:]]*}"}"
        default="${default%"${default##*[![:space:]]}"}"

        [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
        if [[ -n "${seen_keys[$key]+x}" ]]; then
            echo "    duplicate $key in $(basename "$example")" >&2
            continue
        fi
        seen_keys[$key]=1

        existing="$(grep "^${key}=" "$target" 2>/dev/null | head -1 | cut -d= -f2- || true)"
        if [ -n "$existing" ]; then
            echo "    $key= exists"
            continue
        fi
        sed -i "/^${key}=$/d" "$target" 2>/dev/null || true

        while :; do
            used_prefill=false
            read_status=0
            if [ -n "$default" ] && [ -t 0 ]; then
                read -e -i "$default" -r -p "    $key: " val || read_status=$?
                used_prefill=true
            else
                if [ -n "$default" ]; then
                    printf "    %s [%s]: " "$key" "$default"
                else
                    printf "    %s: " "$key"
                fi
                read -r val || read_status=$?
            fi
            if [ "$used_prefill" != "true" ] && [ -z "$val" ]; then
                val="$default"
            fi
            if [ "$required" != "true" ] || [ -n "$val" ]; then
                break
            fi
            if [ "$read_status" -ne 0 ] && [ ! -t 0 ]; then
                echo "    $key required" >&2
                exit 1
            fi
            echo "    $key required"
        done

        if [ -z "$val" ]; then
            if [ "$used_prefill" = "true" ] && [ -n "$default" ]; then
                echo "$key=" >> "$target"
                echo "    $key= set empty"
                continue
            else
                echo "    $key= skipped"
                continue
            fi
        fi
        echo "$key=$val" >> "$target"
    done 3< "$example"
}

if [ ! -f "$DIR/env.example" ] && [ ! -f "$DIR/config.conf_example" ]; then
    echo "No env.example or config.conf_example"
    exit 1
fi

echo ""
echo "  Configuring $PROJECT_NAME"

configure_from_example "$DIR/env.example" "$DIR/.env" ".env"
configure_from_example "$DIR/config.conf_example" "$DIR/config.conf" "config.conf"

echo ""
