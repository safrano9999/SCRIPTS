#!/usr/bin/env bash
set -euo pipefail

trim() {
    local value="$1"
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"
    printf '%s' "$value"
}

read_key() {
    local file="$1" wanted="$2" line entry key
    [ -f "$file" ] || return 1
    while IFS= read -r line || [ -n "$line" ]; do
        line="$(trim "$line")"
        [[ -z "$line" || "$line" == \#* ]] && continue
        entry="$(trim "${line%%#*}")"
        [[ "$entry" == *=* ]] || continue
        key="$(trim "${entry%%=*}")"
        [ "$key" = "$wanted" ] || continue
        trim "${entry#*=}"
        printf '\n'
        return 0
    done < "$file"
    return 1
}

configured_value() {
    local config_dir="$1" container_name="$2" key="$3" file value
    value="${!key:-}"
    [ -n "$value" ] && { printf '%s\n' "$value"; return 0; }
    for file in \
        "$config_dir/$container_name.env" \
        "$config_dir/${container_name}_config.conf" \
        "$config_dir/${container_name}_container.conf" \
        "$config_dir/.env" \
        "$config_dir/config.conf" \
        "$config_dir/container.conf"; do
        value="$(read_key "$file" "$key" || true)"
        [ -n "$value" ] && { printf '%s\n' "$value"; return 0; }
    done
    printf 'on_the_fly\n'
}

is_sqlite() {
    case "${1,,}" in sqlite|sqlite3) return 0 ;; *) return 1 ;; esac
}

command="${1:-}"
shift || true
repo=""
config_dir=""
container_name=""
target="/opt/socialmedia-syncher"

while [ "$#" -gt 0 ]; do
    case "$1" in
        --repo) repo="$2"; shift 2 ;;
        --config-dir) config_dir="$2"; shift 2 ;;
        --container) container_name="$2"; shift 2 ;;
        --target) target="$2"; shift 2 ;;
        *) echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
done

[ -n "$repo" ] || { echo "$command requires --repo" >&2; exit 2; }
[ -n "$config_dir" ] || config_dir="$repo"

content_backend="$(configured_value "$config_dir" "$container_name" SOCIALMEDIA_SYNCHER_DB_BACKEND)"
settings_backend="$(configured_value "$config_dir" "$container_name" SOCIALMEDIA_SYNCHER_SETTINGS_DB_BACKEND)"

case "$command" in
    init)
        is_sqlite "$content_backend" && mkdir -p "$repo/sqlite/content"
        is_sqlite "$settings_backend" && mkdir -p "$repo/sqlite/settings"
        ;;
    mounts)
        [ -n "$container_name" ] || { echo "mounts requires --container" >&2; exit 2; }
        if is_sqlite "$content_backend"; then
            printf '%s-content-database:%s/sqlite/content:Z\n' "$container_name" "${target%/}"
        fi
        if is_sqlite "$settings_backend"; then
            printf '%s-database:%s/sqlite/settings:Z\n' "$container_name" "${target%/}"
        fi
        ;;
    *)
        echo "Usage: sqlite_persistence.sh init|mounts --repo PATH [options]" >&2
        exit 2
        ;;
esac
