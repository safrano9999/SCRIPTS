#!/usr/bin/env bash
for repo in ./*; do
  [ -d "$repo/.git" ] || continue
  [[ "$repo" == ./3rd-party ]] && continue
  git -C "$repo" add -A && git -C "$repo" commit -m "$(date '+%Y-%m-%d %H:%M:%S %z')"
  git -C "$repo" push
  [[ "$repo" == ./CONTAINER ]] || [ ! -f "$repo/tag.sh" ] || (cd "$repo" && ./tag.sh)
done
