#!/usr/bin/env bash
find . -path ./3rd-party -prune -o -name .git -prune -print0 |
while IFS= read -r -d '' git_dir; do
  repo="${git_dir%/.git}"
  git -C "$repo" add -A && git -C "$repo" commit -m "$(date '+%Y-%m-%d %H:%M:%S %z')"
  git -C "$repo" push
  [[ "$repo" == ./CONTAINER* ]] || [ ! -f "$repo/tag.sh" ] || (cd "$repo" && ./tag.sh)
done
