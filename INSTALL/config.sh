#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/env.example" ] || [ -f "$SCRIPT_DIR/config.conf_example" ]; then
    DIR="$SCRIPT_DIR"
else
    DIR="$(pwd)"
fi

PROJECT_NAME="$(basename "$DIR")"
CONTAINER_NAME="${PROJECT_NAME,,}"

trim() {
    local value="$1"
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"
    printf '%s' "$value"
}

read_kv_file() {
    local file="$1"
    local wanted="$2"
    local line stripped entry key value

    [ -f "$file" ] || return 1
    while IFS= read -r line || [ -n "$line" ]; do
        stripped="$(trim "$line")"
        [[ -z "$stripped" || "$stripped" == \#* ]] && continue

        entry="${line%%#*}"
        entry="$(trim "$entry")"
        [[ "$entry" == *=* ]] || continue

        key="$(trim "${entry%%=*}")"
        value="$(trim "${entry#*=}")"
        if [ "$key" = "$wanted" ]; then
            printf '%s\n' "$value"
            return 0
        fi
    done < "$file"
    return 1
}

config_value() {
    local key="$1"
    local file

    for file in "$DIR/config.conf" "$DIR/config.conf_example" "$DIR/.env" "$DIR/env.example"; do
        read_kv_file "$file" "$key" && return 0
    done
    return 1
}

add_unique() {
    local value="$1"
    shift
    local -n target="$1"
    local existing

    [ -n "$value" ] || return 0
    for existing in "${target[@]}"; do
        [ "$existing" = "$value" ] && return 0
    done
    target+=("$value")
}

rewrite_config_with_comments() {
    local example="$1"
    local target="$2"
    local tmp

    [ "$(basename "$target")" = "config.conf" ] || return 0
    [ -f "$example" ] || return 0
    [ -f "$target" ] || return 0

    tmp="$(mktemp)"
    awk -v target="$target" '
    function trim(s) {
        sub(/^[[:space:]]+/, "", s)
        sub(/[[:space:]]+$/, "", s)
        return s
    }
    function parse_env(line, parsed,    entry) {
        entry = line
        sub(/#.*/, "", entry)
        entry = trim(entry)
        if (entry !~ /^[A-Za-z_][A-Za-z0-9_]*[[:space:]]*=/) return 0
        parsed["key"] = entry
        sub(/[[:space:]]*=.*/, "", parsed["key"])
        parsed["key"] = trim(parsed["key"])
        parsed["value"] = entry
        sub(/^[^=]*=/, "", parsed["value"])
        parsed["value"] = trim(parsed["value"])
        return 1
    }
    BEGIN {
        while ((getline line < target) > 0) {
            if (parse_env(line, parsed)) {
                if (!(parsed["key"] in current)) order[++order_count] = parsed["key"]
                current[parsed["key"]] = parsed["value"]
            }
        }
        close(target)
    }
    {
        raw = $0
        stripped = trim(raw)
        if (stripped == "") {
            pending[++pending_count] = raw
            next
        }
        if (substr(stripped, 1, 1) == "#") {
            comment = trim(substr(stripped, 2))
            if (comment ~ /^[A-Za-z_][A-Za-z0-9_]*[[:space:]]*=/) next
            pending[++pending_count] = raw
            next
        }
        if (!parse_env(raw, parsed)) {
            pending_count = 0
            next
        }

        key = parsed["key"]
        value = (key in current) ? current[key] : parsed["value"]
        for (i = 1; i <= pending_count; i++) print pending[i]
        print key "=" value
        written[key] = 1
        pending_count = 0
    }
    END {
        for (i = 1; i <= order_count; i++) {
            key = order[i]
            if (key in written) continue
            if (!printed_extra) {
                print "# Additional local values"
                printed_extra = 1
            }
            print key "=" current[key]
        }
    }' "$example" > "$tmp"
    mv "$tmp" "$target"
}

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

        existing_line="$(grep "^${key}=" "$target" 2>/dev/null | head -1 || true)"
        existing="${existing_line#*=}"
        if [ -n "$existing_line" ] && { [ "$required" != "true" ] || [ -n "$existing" ]; }; then
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

    rewrite_config_with_comments "$example" "$target"
}

existing_image() {
    local quadlet="$DIR/$CONTAINER_NAME.container"
    local compose="$DIR/docker-compose.yml"

    if [ -f "$quadlet" ]; then
        awk -F= '/^Image=/{print $2; exit}' "$quadlet"
        return 0
    fi
    if [ -f "$compose" ]; then
        awk '
        /^[[:space:]]*image:[[:space:]]*/ {
            sub(/^[[:space:]]*image:[[:space:]]*/, "")
            gsub(/^["'\''"]|["'\''"]$/, "")
            print
            exit
        }' "$compose"
        return 0
    fi
}

project_image() {
    local upper_name
    local configured
    upper_name="$(printf '%s' "$PROJECT_NAME" | tr '[:lower:]-' '[:upper:]_')"

    configured="$(config_value "${upper_name}_IMAGE" || true)"
    if [ -n "$configured" ]; then
        printf '%s\n' "$configured"
        return 0
    fi
    configured="$(config_value "IMAGE" || true)"
    if [ -n "$configured" ]; then
        printf '%s\n' "$configured"
        return 0
    fi
    existing_image | grep -m1 . && return 0
    printf 'localhost/%s:latest\n' "$CONTAINER_NAME"
}

config_source_file() {
    if [ -f "$DIR/config.conf" ]; then
        printf '%s\n' "$DIR/config.conf"
    elif [ -f "$DIR/config.conf_example" ]; then
        printf '%s\n' "$DIR/config.conf_example"
    else
        return 1
    fi
}

generate_container_files() {
    local source_file host image compose_file quadlet_file line stripped entry key value
    local prefix internal_key internal_port publish_port publish_host map
    local first_port="" command_host="0.0.0.0"
    local -a ports=()
    local -a volumes=()
    local -a devices=()
    local -a caps=()
    local -a named_volumes=()
    local item source

    source_file="$(config_source_file)" || return 0
    host="$(config_value HOST || true)"
    [ -n "$host" ] || host="127.0.0.1"
    image="$(project_image)"
    compose_file="$DIR/docker-compose.yml"
    quadlet_file="$DIR/$CONTAINER_NAME.container"

    while IFS= read -r line || [ -n "$line" ]; do
        stripped="$(trim "$line")"
        [[ -z "$stripped" || "$stripped" == \#* ]] && continue

        entry="${line%%#*}"
        entry="$(trim "$entry")"
        [[ "$entry" == *=* ]] || continue

        key="$(trim "${entry%%=*}")"
        value="$(config_value "$key" || true)"

        if [[ "$key" == *_PUBLISH_PORT ]]; then
            prefix="${key%_PUBLISH_PORT}"
            internal_key="${prefix}_PORT"
            internal_port="$(config_value "$internal_key" || true)"
            [ -n "$internal_port" ] || internal_port="$value"
            publish_port="$value"
            publish_host="$(config_value "${prefix}_PUBLISH_HOST" || true)"
            [ -n "$publish_host" ] || publish_host="$host"
            map="${publish_host}:${publish_port}:${internal_port}"
            add_unique "$map" ports
            [ -n "$first_port" ] || first_port="$internal_port"
            continue
        fi

        if [[ "$key" == "PORT" || ( "$key" == *_PORT && "$key" != *_PUBLISH_PORT ) ]]; then
            [ -n "$first_port" ] || first_port="$value"
            continue
        fi

        if [[ "$key" == *_CAPABILITIES ]]; then
            IFS=',' read -ra items <<< "$value"
            for item in "${items[@]}"; do add_unique "$(trim "$item")" caps; done
            continue
        fi

        if [[ "$key" == *_DEVICES ]]; then
            IFS=',' read -ra items <<< "$value"
            for item in "${items[@]}"; do add_unique "$(trim "$item")" devices; done
            continue
        fi

        if [[ "$key" == *_VOLUMES ]]; then
            IFS=',' read -ra items <<< "$value"
            for item in "${items[@]}"; do
                item="$(trim "$item")"
                add_unique "$item" volumes
                source="${item%%:*}"
                if [[ "$source" != /* && "$source" != .* && "$source" != *"/"* ]]; then
                    add_unique "$source" named_volumes
                fi
            done
            continue
        fi
    done < "$source_file"

    if [ "${#ports[@]}" -eq 0 ] && [ -n "$first_port" ]; then
        add_unique "${host}:${first_port}:${first_port}" ports
    fi

    if [ -z "$first_port" ] && [ ! -f "$DIR/webui.py" ]; then
        return 0
    fi
    if [ -z "$first_port" ]; then
        echo "  No PORT or *_PORT found; skipping docker-compose.yml and $CONTAINER_NAME.container"
        return 0
    fi

    {
        printf '# Generated by config.sh for %s\n' "$PROJECT_NAME"
        printf '# Edit config.conf, then run ./config.sh again.\n'
        printf '# Usage: docker compose up -d\n\n'
        printf 'services:\n'
        printf '  %s:\n' "$CONTAINER_NAME"
        if [ -f "$DIR/Containerfile" ] || [ -f "$DIR/Dockerfile" ]; then
            printf '    # Local build context detected by config.sh\n'
            printf '    build:\n'
            printf '      context: .\n'
            [ -f "$DIR/Containerfile" ] && printf '      dockerfile: Containerfile\n'
            [ ! -f "$DIR/Containerfile" ] && [ -f "$DIR/Dockerfile" ] && printf '      dockerfile: Dockerfile\n'
        fi
        printf '    # Container image from config or existing generated file\n'
        printf '    image: %s\n' "$image"
        printf '    container_name: %s\n' "$CONTAINER_NAME"
        printf '    hostname: %s\n' "$CONTAINER_NAME"
        if [ "${#ports[@]}" -gt 0 ]; then
            printf '    # Port mappings: HOST:PUBLISH_PORT:PORT from config.conf\n'
            printf '    ports:\n'
            for item in "${ports[@]}"; do printf '      - "%s"\n' "$item"; done
        fi
        if [ -f "$DIR/config.conf" ] || [ -f "$DIR/.env" ]; then
            printf '    # Runtime configuration files generated from *example files\n'
            printf '    env_file:\n'
            [ -f "$DIR/config.conf" ] && printf '      - %s\n' "$DIR/config.conf"
            [ -f "$DIR/.env" ] && printf '      - %s\n' "$DIR/.env"
        fi
        if [ -f "$DIR/webui.py" ]; then
            printf '    # Container-internal bind address; published host is controlled by HOST\n'
            printf '    command: uvicorn webui:app --host %s --port %s\n' "$command_host" "$first_port"
        fi
        if [ "${#volumes[@]}" -gt 0 ]; then
            printf '    # Volume mappings from *_VOLUMES in config.conf\n'
            printf '    volumes:\n'
            for item in "${volumes[@]}"; do printf '      - %s\n' "$item"; done
        fi
        if [ "${#caps[@]}" -gt 0 ]; then
            printf '    # Linux capabilities from *_CAPABILITIES in config.conf\n'
            printf '    cap_add:\n'
            for item in "${caps[@]}"; do printf '      - %s\n' "$item"; done
        fi
        if [ "${#devices[@]}" -gt 0 ]; then
            printf '    # Device mappings from *_DEVICES in config.conf\n'
            printf '    devices:\n'
            for item in "${devices[@]}"; do printf '      - %s\n' "$item"; done
        fi
        printf '    restart: always\n'
        if [ "${#named_volumes[@]}" -gt 0 ]; then
            printf '\n# Named volumes derived from *_VOLUMES sources\n'
            printf '\nvolumes:\n'
            for item in "${named_volumes[@]}"; do printf '  %s: {}\n' "$item"; done
        fi
    } > "$compose_file"
    echo "  Written: $compose_file"

    {
        printf '# Generated by config.sh for %s\n' "$PROJECT_NAME"
        printf '# Edit config.conf, then run ./config.sh again.\n'
        printf '\n'
        printf '[Container]\n'
        printf 'ContainerName=%s\n' "$CONTAINER_NAME"
        printf '# Container image from config or existing generated file\n'
        printf 'Image=%s\n' "$image"
        if [ -f "$DIR/config.conf" ] || [ -f "$DIR/.env" ]; then
            printf '# Runtime configuration files generated from *example files\n'
        fi
        [ -f "$DIR/config.conf" ] && printf 'EnvironmentFile=%s\n' "$DIR/config.conf"
        [ -f "$DIR/.env" ] && printf 'EnvironmentFile=%s\n' "$DIR/.env"
        [ "${#ports[@]}" -gt 0 ] && printf '# Port mappings: HOST:PUBLISH_PORT:PORT from config.conf\n'
        for item in "${ports[@]}"; do printf 'PublishPort=%s\n' "$item"; done
        if [ -f "$DIR/webui.py" ]; then
            printf '# Container-internal bind address; published host is controlled by HOST\n'
            printf 'Exec=uvicorn webui:app --host %s --port %s\n' "$command_host" "$first_port"
        fi
        [ "${#volumes[@]}" -gt 0 ] && printf '# Volume mappings from *_VOLUMES in config.conf\n'
        for item in "${volumes[@]}"; do printf 'Volume=%s\n' "$item"; done
        [ "${#caps[@]}" -gt 0 ] && printf '# Linux capabilities from *_CAPABILITIES in config.conf\n'
        for item in "${caps[@]}"; do printf 'AddCapability=%s\n' "$item"; done
        [ "${#devices[@]}" -gt 0 ] && printf '# Device mappings from *_DEVICES in config.conf\n'
        for item in "${devices[@]}"; do printf 'AddDevice=%s\n' "$item"; done
        printf '#AutoUpdate=registry\n\n'
        printf '[Service]\n'
        printf 'Restart=always\n'
        printf 'TimeoutStartSec=30\n\n'
        printf '[Install]\n'
        printf 'WantedBy=default.target\n'
    } > "$quadlet_file"
    echo "  Written: $quadlet_file"
}

if [ ! -f "$DIR/env.example" ] && [ ! -f "$DIR/config.conf_example" ]; then
    echo "No env.example or config.conf_example"
    exit 1
fi

echo ""
echo "  Configuring $PROJECT_NAME"

configure_from_example "$DIR/env.example" "$DIR/.env" ".env"
configure_from_example "$DIR/config.conf_example" "$DIR/config.conf" "config.conf"
generate_container_files

echo ""
