#!/usr/bin/env bash
set -euo pipefail

out="${1:?usage: systemd_pass_environment.sh OUTPUT FILE...}"
shift

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

for file in "$@"; do
    [ -f "$file" ] || continue
    sed -nE 's/^[[:space:]]*(export[[:space:]]+)?([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*=.*/\2/p' "$file"
done | sort -u > "$tmp"

{
    printf '%s\n' '[Service]'
    awk '
        NF {
            if (count % 20 == 0) {
                if (count > 0) print line
                line = "PassEnvironment=" $1
            } else {
                line = line " " $1
            }
            count++
        }
        END {
            if (count > 0) print line
        }
    ' "$tmp"
} > "$out"
