#!/usr/bin/env bash
find /home/openclaw/safcontainer -path /home/openclaw/safcontainer/CONTAINER -prune -o -name .git -prune -print0 |
while IFS= read -r -d '' git_dir; do
  cd "${git_dir%/.git}"
  git add -A && git commit -m "$(date '+%Y-%m-%d %H:%M:%S %z')"
  git push
  [ ! -f tag.sh ] || ./tag.sh
done
