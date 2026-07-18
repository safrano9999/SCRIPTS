#!/usr/bin/env bash
set -euo pipefail

output_dir="${1:?missing normal generator output directory}"
dropin="$output_dir/service.d/90-fedora44-runtime-environment.conf"

mkdir -p "$(dirname "$dropin")"
mapfile -t names < <(compgen -e | LC_ALL=C sort -u)

{
    printf '%s\n' '[Service]'
    line=
    count=0
    for name in "${names[@]}"; do
        if (( count % 20 == 0 )); then
            if [ -n "$line" ]; then
                printf '%s\n' "$line"
            fi
            line="PassEnvironment=$name"
        else
            line+=" $name"
        fi
        ((count += 1))
    done
    if [ -n "$line" ]; then
        printf '%s\n' "$line"
    fi
} > "$dropin"

case "${CLOUDFLARED_START:-0}" in
    1|true|yes|on)
        mkdir -p "$output_dir/multi-user.target.wants"
        ln -sfn /etc/systemd/system/cloudflared.service \
            "$output_dir/multi-user.target.wants/cloudflared.service"
        ;;
esac
