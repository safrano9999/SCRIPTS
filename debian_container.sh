#!/bin/bash
# Start openclaw node container with persistent named volumes

if [ -z "$1" ]; then
  echo "Usage: $0 <container-name>"
  echo "Example: $0 openclaw_node_debian"
  exit 1
fi

CONTAINER_NAME="$1"
IMAGE="localhost/openclaw-node:latest"

# Display-Forwarding: Wayland bevorzugt, Fallback auf X11
DISPLAY_ARGS=()
HOST_UID=$(id -u)
WAYLAND_SOCK="/run/user/${HOST_UID}/wayland-0"
CURRENT_DISPLAY="${DISPLAY:-:0}"
XAUTH_FILE="${XAUTHORITY:-$HOME/.Xauthority}"

if [ -S "$WAYLAND_SOCK" ]; then
  echo "Wayland erkannt — Wayland-Socket wird durchgereicht."
  DISPLAY_ARGS+=(-e "WAYLAND_DISPLAY=wayland-0")
  DISPLAY_ARGS+=(-e "XDG_RUNTIME_DIR=/run/user/${HOST_UID}")
  DISPLAY_ARGS+=(-v "/run/user/${HOST_UID}:/run/user/${HOST_UID}:ro")
elif [ -d "/tmp/.X11-unix" ]; then
  echo "X11 erkannt — X11-Socket wird durchgereicht."
  DISPLAY_ARGS+=(-e "DISPLAY=$CURRENT_DISPLAY")
  DISPLAY_ARGS+=(-v "/tmp/.X11-unix:/tmp/.X11-unix:ro")
  if [ -f "$XAUTH_FILE" ]; then
    DISPLAY_ARGS+=(-e "XAUTHORITY=/tmp/.host_Xauthority")
    DISPLAY_ARGS+=(-v "$XAUTH_FILE:/tmp/.host_Xauthority:ro")
  fi
else
  echo "Hinweis: Weder Wayland noch X11 gefunden — Display-Forwarding deaktiviert."
fi

# Persistente Daten-Volumes (System-Dirs kommen aus dem Image)
podman run -d \
  --replace \
  --name "$CONTAINER_NAME" \
  --hostname "$CONTAINER_NAME" \
  --network host \
  -v "${CONTAINER_NAME}_etc:/etc" \
  -v "${CONTAINER_NAME}_home:/home" \
  -v "${CONTAINER_NAME}_media:/media" \
  -v "${CONTAINER_NAME}_mnt:/mnt" \
  -v "${CONTAINER_NAME}_opt:/opt" \
  -v "${CONTAINER_NAME}_root:/root" \
  -v "${CONTAINER_NAME}_srv:/srv" \
  -v "${CONTAINER_NAME}_var:/var" \
  "${DISPLAY_ARGS[@]}" \
  "$IMAGE" \
  bash -c 'sleep infinity'

echo "Container '$CONTAINER_NAME' gestartet."
echo "Attach: podman exec -it $CONTAINER_NAME bash"
