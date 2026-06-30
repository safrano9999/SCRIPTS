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

path_keys() {
    local config_dir="$1" file
    for file in \
        "$config_dir"/config*.conf_example \
        "$config_dir/config.conf" \
        "$config_dir"/*build.conf_example \
        "$config_dir/build.conf" \
        "$config_dir/container.conf"; do
        [ -f "$file" ] || continue
        awk '
        /^[[:space:]]*#/ { next }
        /^[[:space:]]*[A-Za-z_][A-Za-z0-9_]*_(PERSISTENT|VOLUME)_PATH[[:space:]]*=/ {
            key=$0
            sub(/[[:space:]]*=.*/, "", key)
            sub(/^[[:space:]]*/, "", key)
            if (!seen[key]++) print key
        }' "$file"
    done | awk '!seen[$0]++'
}

configured_path() {
    local config_dir="$1" key="$2" file value
    value="${!key:-}"
    [ -n "$value" ] && { printf '%s\n' "$value"; return 0; }
    for file in \
        "$config_dir/container.conf" \
        "$config_dir/config.conf" \
        "$config_dir/build.conf" \
        "$config_dir"/config*.conf_example \
        "$config_dir"/*build.conf_example; do
        value="$(read_key "$file" "$key" || true)"
        [ -n "$value" ] && { printf '%s\n' "$value"; return 0; }
    done
}

valid_path() {
    local path="$1"
    [[ "$path" == /* && "$path" != *:* && "$path" != *$'\n'* && "$path" != *$'\r'* ]]
}

safe_name() {
    printf '%s' "$1" | tr '[:upper:]_' '[:lower:]-' | sed 's/[^a-z0-9_.-]/-/g'
}

emit_entries() {
    local config_dir="$1" key path
    while IFS= read -r key || [ -n "$key" ]; do
        [ -n "$key" ] || continue
        path="$(configured_path "$config_dir" "$key")"
        case "${path,,}" in ""|blank|null) continue ;; esac
        valid_path "$path" || { echo "Invalid $key: $path" >&2; return 1; }
        printf '%s\t%s\n' "$key" "$path"
    done < <(path_keys "$config_dir")
}

command="${1:-}"
shift || true
config_dir="."
container_name=""
while [ "$#" -gt 0 ]; do
    case "$1" in
        --config-dir) config_dir="$2"; shift 2 ;;
        --container) container_name="$2"; shift 2 ;;
        *) echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
done

case "$command" in
    entries)
        emit_entries "$config_dir"
        ;;
    mounts)
        [ -n "$container_name" ] || { echo "mounts requires --container" >&2; exit 2; }
        while IFS=$'\t' read -r key path; do
            case "$key" in
                *_PERSISTENT_PATH) prefix="${key%_PERSISTENT_PATH}" ;;
                *_VOLUME_PATH) prefix="${key%_VOLUME_PATH}" ;;
            esac
            printf '%s-%s-persistent:%s:Z\n' "$(safe_name "$container_name")" "$(safe_name "$prefix")" "$path"
        done < <(emit_entries "$config_dir")
        ;;
    init)
        while IFS= read -r key; do
            [[ "$key" == *_PERSISTENT_PATH || "$key" == *_VOLUME_PATH ]] || continue
            path="${!key:-}"
            case "${path,,}" in ""|blank|null) continue ;; esac
            valid_path "$path" || { echo "Invalid $key: $path" >&2; exit 1; }
            mkdir -p "$path"
            if [[ "$key" == *_AUTH_VOLUME_PATH ]]; then
                app="${key%_AUTH_VOLUME_PATH}"
                app_home_key="${app}_HOME"
                app_home="${!app_home_key:-${HOME:-/root}/.${app,,}}"
                auth_file="$app_home/auth.json"
                target="$path/auth.json"
                mkdir -p "$app_home"
                if [ -f "$auth_file" ] && [ ! -e "$target" ]; then
                    mv "$auth_file" "$target"
                elif [ -e "$auth_file" ] || [ -L "$auth_file" ]; then
                    rm -f "$auth_file"
                fi
                ln -sfn "$target" "$auth_file"
                if [ "$app" = "CODEX" ]; then
                    config_file="$app_home/config.toml"
                    if grep -q '^[[:space:]]*cli_auth_credentials_store[[:space:]]*=' "$config_file" 2>/dev/null; then
                        sed -i 's/^[[:space:]]*cli_auth_credentials_store[[:space:]]*=.*/cli_auth_credentials_store = "file"/' "$config_file"
                    else
                        printf '\ncli_auth_credentials_store = "file"\n' >> "$config_file"
                    fi
                fi
            fi
        done < <(compgen -e | LC_ALL=C sort -u)
        ;;
    *)
        echo "Usage: optional_persistence.sh entries|mounts|init [options]" >&2
        exit 2
        ;;
esac
