#!/bin/bash

# Whitelist = Images der aktuell laufenden Container
KEEP_IDS=()
while IFS= read -r id; do
  KEEP_IDS+=("$id")
done < <(podman ps -q | xargs -r podman inspect --format "{{.Image}}")

# Alle Images durchgehen
while IFS= read -r line; do
  ID=$(echo "$line" | awk '{print $1}')
  NAME=$(echo "$line" | awk '{print $2}')

  if [[ " ${KEEP_IDS[@]} " =~ " ${ID} " ]]; then
    echo "✓ Behalte: $NAME (läuft)"
  else
    echo "✗ Lösche:  $NAME"
    podman rmi -f "$ID" 2>/dev/null
  fi
done < <(podman images --format "{{.Id}} {{.Repository}}:{{.Tag}}")

podman system prune -f
