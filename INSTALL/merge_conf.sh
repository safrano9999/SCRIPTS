#!/usr/bin/env bash
set -euo pipefail

dir="${1:?usage: merge_conf.sh DIR OUTPUT BASE_CONFIG REPOS_DIR CONFIG_NAME}"
output="${2:?usage: merge_conf.sh DIR OUTPUT BASE_CONFIG REPOS_DIR CONFIG_NAME}"
base_config="${3:?usage: merge_conf.sh DIR OUTPUT BASE_CONFIG REPOS_DIR CONFIG_NAME}"
repos_dir="${4:?usage: merge_conf.sh DIR OUTPUT BASE_CONFIG REPOS_DIR CONFIG_NAME}"
config_name="${5:?usage: merge_conf.sh DIR OUTPUT BASE_CONFIG REPOS_DIR CONFIG_NAME}"
cd "$dir"

declare -a files=()
[ -f "$base_config" ] && files+=("$base_config")
if [ -d "$repos_dir" ]; then
    for repo_dir in "$repos_dir"/*/; do
        [ -f "$repo_dir/$config_name" ] && files+=("$repo_dir/$config_name")
    done
fi

if [ "${#files[@]}" -eq 0 ]; then
    : > "$output"
    echo "  ! No $config_name sources found"
    exit 0
fi

awk '
function flush_pending() {
    pending = ""
}
FNR == 1 {
    flush_pending()
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
{
    flush_pending()
}
' "${files[@]}" > "$output"

echo "  Merged $config_name (${#files[@]} sources) -> ${output#"$dir"/}"
