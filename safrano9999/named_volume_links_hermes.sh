#!/usr/bin/env bash
set -euo pipefail

NAMED_VOLUME_ONLY_MOUNT=/named_volumes/HERMES exec /usr/local/bin/named_volume_links.sh
