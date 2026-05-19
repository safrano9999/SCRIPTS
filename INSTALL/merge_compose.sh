#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -d "$SCRIPT_DIR/safrano9999" ]; then
    DIR="$SCRIPT_DIR"
else
    DIR="$(pwd)"
fi

SAFRANO_DIR="$DIR/safrano9999"
OUTPUT="$DIR/compose.example"

declare -a files=()
[ -f "$DIR/compose.fedora43-ai.example" ] && files+=("$DIR/compose.fedora43-ai.example")
if [ -d "$SAFRANO_DIR" ]; then
    for repo_dir in "$SAFRANO_DIR"/*/; do
        [ -f "$repo_dir/compose.example" ] && files+=("$repo_dir/compose.example")
    done
fi

if [ ${#files[@]} -eq 0 ]; then
    echo "  ! Keine compose.example Quellen gefunden"
    : > "$OUTPUT"
    exit 0
fi

awk '
function trim(s) {
    sub(/^[[:space:]]+/, "", s)
    sub(/[[:space:]]+$/, "", s)
    return s
}
function reset_block() {
    comment = ""
    comment_line = ""
    entry = ""
}
function flush_block() {
    if (comment == "" || entry == "") {
        reset_block()
        return
    }
    if (!(comment in seen)) {
        seen[comment] = 1
        print comment_line
        print entry
        print ""
        count++
    }
    reset_block()
}
{
    stripped = trim($0)
    if (stripped == "") {
        flush_block()
        next
    }
    if (substr(stripped, 1, 1) == "#") {
        flush_block()
        comment_line = $0
        comment = trim(substr(stripped, 2))
        next
    }
    if (index(stripped, "=") > 0) {
        entry = stripped
        flush_block()
        next
    }
    flush_block()
}
END {
    flush_block()
}
' "${files[@]}" > "$OUTPUT"

echo "  Merged compose.example (${#files[@]} Quellen) → ${OUTPUT#"$DIR"/}"
