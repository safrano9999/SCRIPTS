#!/usr/bin/env bash
SCRIPT_LOCATION="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [ -d "$SCRIPT_LOCATION/CONTAINER" ]; then
  ROOT="$SCRIPT_LOCATION"
else
  ROOT="$(dirname "$SCRIPT_LOCATION")"
fi
"$ROOT/SCRIPTS/safrano9999/image/check-setup-image-source.sh" \
  "$ROOT/CONTAINER/fedora44-ai-base/setup.sh" \
  "$ROOT/CONTAINER/fedora44-ai-safrano9999/setup.sh" \
  "$ROOT/CONTAINER/safrano9999-openclaw/setup.sh" || exit 1

cd "$ROOT" || exit 1
for repo in ./* ./CONTAINER/*; do
  [ -d "$repo/.git" ] || continue
  [[ "$repo" == ./3rd-party ]] && continue
  git -C "$repo" add -A; git -C "$repo" diff --cached --quiet && { echo "[$(basename "$repo")] unchanged - skipped"; continue; }
  git -C "$repo" commit -m "$(date '+%Y-%m-%d %H:%M:%S %z')" || continue
  git -C "$repo" push || continue
  [[ "$repo" == ./CONTAINER* ]] || [ ! -f "$repo/tag.sh" ] || (cd "$repo" && ./tag.sh)
done
