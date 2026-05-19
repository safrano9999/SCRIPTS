#!/usr/bin/env bash
set -euo pipefail

dir="${1:?usage: merge_yaml.sh DIR OUTPUT BASE_CONFIG REPOS_DIR CONFIG_NAME}"
output="${2:?usage: merge_yaml.sh DIR OUTPUT BASE_CONFIG REPOS_DIR CONFIG_NAME}"
base_config="${3:?usage: merge_yaml.sh DIR OUTPUT BASE_CONFIG REPOS_DIR CONFIG_NAME}"
repos_dir="${4:?usage: merge_yaml.sh DIR OUTPUT BASE_CONFIG REPOS_DIR CONFIG_NAME}"
config_name="${5:?usage: merge_yaml.sh DIR OUTPUT BASE_CONFIG REPOS_DIR CONFIG_NAME}"
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
    echo "  ! Keine config.yaml Quellen gefunden"
    exit 0
fi

awk '
function flush_service() {
    if (service == "") return
    if (!(service in seen)) {
        seen[service] = 1
        printf "%s", block
    }
    service = ""
    block = ""
}
FNR == 1 {
    flush_service()
    in_defaults = 0
    in_services = 0
}
/^defaults:/ && !defaults_done {
    defaults_done = 1
    in_defaults = 1
    print
    next
}
in_defaults {
    if ($0 ~ /^[[:space:]]/ || $0 == "") {
        print
        next
    }
    in_defaults = 0
}
/^services:/ {
    if (!services_done) {
        services_done = 1
        print "services:"
    }
    in_services = 1
    next
}
in_services && $0 ~ /^  [A-Za-z0-9_-]+:/ {
    flush_service()
    service = $1
    sub(/:$/, "", service)
    block = $0 "\n"
    next
}
in_services && service != "" {
    if ($0 ~ /^[[:space:]]/ || $0 == "") {
        block = block $0 "\n"
        next
    }
    flush_service()
    in_services = 0
}
END {
    flush_service()
}
' "${files[@]}" > "$output"

echo "  Merged $config_name (${#files[@]} Quellen) -> ${output#"$dir"/}"
