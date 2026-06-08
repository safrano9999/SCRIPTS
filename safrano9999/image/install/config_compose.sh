#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/compose.example" ]; then
    DIR="$SCRIPT_DIR"
else
    DIR="$(pwd)"
fi

EXAMPLE="$DIR/compose.example"
CONF="$DIR/compose.conf"
PROJECT_NAME="$(basename "$DIR")"
USE_DEFAULTS=false

for arg in "$@"; do
    case "$arg" in
        --defaults) USE_DEFAULTS=true ;;
    esac
done

[ ! -f "$EXAMPLE" ] && echo "No compose.example" && exit 1

trim() {
    local value="$1"
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"
    printf '%s' "$value"
}

existing_entry() {
    local wanted="$1"
    [ -f "$CONF" ] || return 1
    awk -v wanted="$wanted" '
    function trim(s) {
        sub(/^[[:space:]]+/, "", s)
        sub(/[[:space:]]+$/, "", s)
        return s
    }
    {
        stripped = trim($0)
        if (stripped == "") {
            comment = ""
            next
        }
        if (substr(stripped, 1, 1) == "#") {
            comment = trim(substr(stripped, 2))
            next
        }
        if (index(stripped, "=") > 0 && comment == wanted) {
            print stripped
            found = 1
            exit
        }
        comment = ""
    }
    END {
        exit found ? 0 : 1
    }' "$CONF"
}

echo ""
echo "  Configuring compose for $PROJECT_NAME"
echo ""

touch "$CONF"
prompt=""
comment_line=""

while IFS= read -r line <&3 || [ -n "$line" ]; do
    stripped="$(trim "$line")"
    if [[ -z "$stripped" ]]; then
        prompt=""
        comment_line=""
        continue
    fi
    if [[ "$stripped" == \#* ]]; then
        prompt="$(trim "${stripped#\#}")"
        comment_line="$line"
        continue
    fi
    [[ "$stripped" == *=* ]] || continue

    key="$(trim "${stripped%%=*}")"
    default="$(trim "${stripped#*=}")"
    [ -n "$prompt" ] || prompt="$key"
    [ -n "$comment_line" ] || comment_line="# $prompt"

    if existing_entry "$prompt" >/dev/null; then
        echo "    $prompt exists"
        prompt=""
        comment_line=""
        continue
    fi

    if $USE_DEFAULTS; then
        val="$default"
    else
        used_prefill=false
        if [ -n "$default" ] && [ -t 0 ]; then
            read -e -i "$default" -r -p "    $prompt: " val
            used_prefill=true
        else
            if [ -n "$default" ]; then
                printf "    %s [%s]: " "$prompt" "$default"
            else
                printf "    %s: " "$prompt"
            fi
            read -r val
        fi
        if [ "$used_prefill" != "true" ] && [ -z "$val" ]; then
            val="$default"
        fi
    fi

    if [ -z "$val" ]; then
        echo "    $prompt skipped"
        prompt=""
        comment_line=""
        continue
    fi

    {
        printf '%s\n' "$comment_line"
        printf '%s=%s\n\n' "$key" "$val"
    } >> "$CONF"

    prompt=""
    comment_line=""
done 3< "$EXAMPLE"

echo ""
