#!/usr/bin/env bash
set -euo pipefail

[ "$#" -gt 0 ] || { echo "No setup.sh paths supplied" >&2; exit 2; }

for setup in "$@"; do
    [ -f "$setup" ] || { echo "Missing setup script: $setup" >&2; exit 1; }
    # shellcheck disable=SC2016
    for marker in \
        'Image source:' \
        'Build locally' \
        'read -rp "  Choose [1/2] (default: 2): " IMG_CHOICE' \
        'IMG_CHOICE="${IMG_CHOICE:-2}"'; do
        grep -Fq "$marker" "$setup" || {
            echo "Missing persistent image-source prompt in $setup: $marker" >&2
            exit 1
        }
    done
    if grep -Eq '^[[:space:]]*IMG_CHOICE=1[[:space:]]*$' "$setup"; then
        echo "Automatic pull bypass found in $setup" >&2
        exit 1
    fi
done

echo "Image-source setup prompts verified."
