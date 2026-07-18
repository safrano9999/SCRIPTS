#!/usr/bin/env bash
set -euo pipefail

/usr/local/bin/optional_persistence.sh init
NAMED_VOLUME_SKIP_MOUNTS='/named_volumes/HERMES;/named_volumes/OPENCLAW' /usr/local/bin/named_volume_links.sh
/usr/local/bin/named_volume_links_hermes.sh
/usr/local/bin/named_volume_links_openclaw.sh

find /usr/local/share/fedora44-ai/bin -maxdepth 1 -type f \( -name "*.sh" -o -name "*.py" \) -print \
    | sort \
    | while IFS= read -r script; do
        case "$script" in
            *.sh) /bin/bash "$script" ;;
            *.py) /usr/bin/python3 "$script" ;;
        esac
    done
