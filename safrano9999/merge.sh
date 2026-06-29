#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -d "$SCRIPT_DIR/safrano9999" ]; then
    DIR="$SCRIPT_DIR"
else
    DIR="$(pwd)"
fi
SAFRANO_DIR="$DIR/safrano9999"
PLUGIN_NAMES=("$@")
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/safrano9999-merge.XXXXXX")"
trap 'rm -rf "$TMP_DIR"' EXIT

collect_base_files() {
    local kind="$1"
    local output="$2"
    local result_name="$3"
    local -n base_result_ref="$result_name"
    local file
    local -a candidates=()

    case "$kind" in
        env) candidates=("$DIR"/env*example) ;;
        config) candidates=("$DIR"/config*example) ;;
        container) candidates=("$DIR"/container*example "$DIR"/config*.container) ;;
        *) return 2 ;;
    esac
    for file in "${candidates[@]}"; do
        [ -f "$file" ] || continue
        [ "$file" = "$output" ] && continue
        base_result_ref+=("$file")
    done
}

collect_plugin_files() {
    local filename="$1"
    local result_name="$2"
    local -n plugin_result_ref="$result_name"
    local name lower source extracted repo_dir zip_path
    local -a repo_dirs=() zip_files=()

    shopt -s nullglob
    repo_dirs=("$SAFRANO_DIR"/*/)
    zip_files=("$SAFRANO_DIR"/*-latest.zip)
    shopt -u nullglob

    if [ "${#repo_dirs[@]}" -gt 0 ]; then
        if [ "${#PLUGIN_NAMES[@]}" -gt 0 ]; then
            for name in "${PLUGIN_NAMES[@]}"; do
                repo_dir="$SAFRANO_DIR/${name%@*}"
                source="$repo_dir/$filename"
                [ -f "$source" ] && plugin_result_ref+=("$source")
            done
        else
            for repo_dir in "${repo_dirs[@]}"; do
                source="$repo_dir$filename"
                [ -f "$source" ] && plugin_result_ref+=("$source")
            done
        fi
        return 0
    fi

    if [ "${#PLUGIN_NAMES[@]}" -eq 0 ]; then
        for zip_path in "${zip_files[@]}"; do
            name="$(basename "$zip_path" -latest.zip)"
            PLUGIN_NAMES+=("${name^^}")
        done
    fi
    for name in "${PLUGIN_NAMES[@]}"; do
        lower="$(printf '%s' "${name%@*}" | tr '[:upper:]' '[:lower:]')"
        zip_path="$SAFRANO_DIR/${lower}-latest.zip"
        [ -f "$zip_path" ] || continue
        unzip -Z1 "$zip_path" | awk -v wanted="$filename" '$0 == wanted { found=1 } END { exit !found }' || continue
        extracted="$TMP_DIR/$lower/$filename"
        mkdir -p "$(dirname "$extracted")"
        unzip -p "$zip_path" "$filename" > "$extracted"
        plugin_result_ref+=("$extracted")
    done
}

merge_keyed() {
    local filename="$1"
    local output="$2"
    local kind="$3"
    local -a files=() plugin_files=()

    collect_base_files "$kind" "$output" files
    collect_plugin_files "$filename" plugin_files
    files+=("${plugin_files[@]}")
    if [ "${#files[@]}" -eq 0 ]; then
        : > "$output"
        echo "  ! No $filename sources found"
        return 0
    fi

    awk '
    function flush_pending() { pending = "" }
    FNR == 1 { flush_pending() }
    /^[[:space:]]*#[[:space:]]*(export[[:space:]]+)?[A-Za-z_][A-Za-z0-9_]*_VOLUMES=/ {
        line = $0
        sub(/^[[:space:]]*#[[:space:]]*/, "", line)
        sub(/^[[:space:]]*export[[:space:]]+/, "", line)
        key = line
        sub(/=.*/, "", key)
        if (!(key in seen)) {
            seen[key] = 1
            if (pending != "") printf "%s", pending
            print "# " line
            print ""
        }
        flush_pending()
        next
    }
    /^[[:space:]]*($|#)/ {
        pending = pending $0 "\n"
        next
    }
    /^[[:space:]]*(export[[:space:]]+)?[A-Za-z_][A-Za-z0-9_]*=/ {
        line = $0
        sub(/^[[:space:]]*export[[:space:]]+/, "", line)
        key = line
        sub(/=.*/, "", key)
        if (!(key in seen)) {
            seen[key] = 1
            if (pending != "") printf "%s", pending
            print line
            print ""
        }
        flush_pending()
        next
    }
    { flush_pending() }
    ' "${files[@]}" > "$output"
    echo "  Merged $filename (${#files[@]} sources) -> ${output#"$DIR"/}"
}

merge_requirements() {
    local output="$DIR/requirements.txt"
    local -a files=()

    collect_plugin_files requirements.txt files
    if [ "${#files[@]}" -eq 0 ]; then
        : > "$output"
        echo "  ! No requirements.txt sources found"
        return 0
    fi
    awk '
    {
        stripped = $0
        sub(/^[[:space:]]+/, "", stripped)
        if (stripped == "" || substr(stripped, 1, 1) == "#") { print; next }
        match(stripped, /^[A-Za-z0-9._-]+/)
        if (RSTART == 0) { print; next }
        key = tolower(substr(stripped, RSTART, RLENGTH))
        if (!(key in seen)) { seen[key] = 1; print }
    }
    ' "${files[@]}" > "$output"
    echo "  Merged requirements.txt (${#files[@]} sources) -> requirements.txt"
}

merge_keyed env.example "$DIR/env.example" env
merge_keyed config.conf_example "$DIR/config.conf_example" config
merge_keyed container.example "$DIR/container.example" container
merge_requirements
