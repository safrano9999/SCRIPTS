#!/usr/bin/env bash
for repo in ./* ./CONTAINER/*; do
  [ -d "$repo/.git" ] || continue
  [[ "$repo" == ./3rd-party ]] && continue
  git -C "$repo" add -A; git -C "$repo" diff --cached --quiet && { echo "[$(basename "$repo")] unchanged - skipped"; continue; }
  git -C "$repo" commit -m "$(date '+%Y-%m-%d %H:%M:%S %z')" || continue
  git -C "$repo" push || continue
  [[ "$repo" == ./CONTAINER* ]] || [ ! -f "$repo/tag.sh" ] || (cd "$repo" && ./tag.sh)
done
