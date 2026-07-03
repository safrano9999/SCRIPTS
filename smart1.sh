#!/usr/bin/env bash
set -euo pipefail
SMART_STORAGE="${SMART_STORAGE:-/var/lib/shared-containers/storage}"

if [[ " $* " == *" --help "* ]]; then
  printf '%s\n' \
    '--init    Create a skeletal images.json; fail if it exists.' \
    '--user    Clean only the current user Podman store.' \
    '--prune   Protect running old layers of JSON-listed images.' \
    '--update  Pull JSON-listed images after cleanup.' \
    '--help    Show this help.'
  exit 0
fi

if [[ " $* " == *" --init "* ]]; then
  [[ ! -e images.json ]] || { echo "ERROR: images.json already exists" >&2; exit 1; }
  cat >images.json <<'EOF'
{
  "schemaVersion": 1,
  "images": [
    "docker.io/foo/bar:latest"
  ]
}
EOF
  exit 0
fi

if [[ " $* " == *" --user "* ]]; then
  c="$HOME/.config/containers/storage.conf"
  tomlq -t -i '.storage.options.additionalimagestores = []' "$c"
  podman pod rm -af
  podman rm -af
  podman image rm -af; podman system prune -af --build
  tomlq -t -i ".storage.options.additionalimagestores = [\"$SMART_STORAGE\"]" "$c"
  exit 0
fi

STORE="$SMART_STORAGE"
SOT="$(cd -- "$(dirname -- "$0")" && pwd)/images.json"
AUTH=/run/user/${SUDO_UID:-$(id -u)}/containers/auth.json
SKOPEO=(skopeo inspect)
PULL_AUTH=(); [[ -r "$AUTH" ]] && SKOPEO+=(--authfile "$AUTH") && PULL_AUTH=(--authfile "$AUTH")
tmp=$(mktemp); trap 'rm -f "$tmp"*; chmod -R a+rX "$STORE"' EXIT

registry_login() {
  local registry="$1" uid="${SUDO_UID:-$(id -u)}" user home
  if (( EUID == 0 )) && [[ -n ${SUDO_UID:-} ]]; then
    IFS=: read -r user _ _ _ _ home _ < <(getent passwd "$uid")
    runuser -u "$user" -- env HOME="$home" XDG_RUNTIME_DIR="/run/user/$uid" podman login "$registry"
  else
    podman login "$registry"
  fi
  SKOPEO=(skopeo inspect --authfile "$AUTH"); PULL_AUTH=(--authfile "$AUTH")
}

while read -r ref; do
  echo "FETCH metadata $ref"
  if ! data=$("${SKOPEO[@]}" "docker://$ref" 2>"$tmp.auth"); then
    cat "$tmp.auth" >&2
    grep -Eqi 'unauthorized|authentication required|requested access .* denied' "$tmp.auth" || exit 1
    registry_login "${ref%%/*}"
    data=$("${SKOPEO[@]}" "docker://$ref")
  fi
  echo "ONLINE $ref $(jq -r '.Digest' <<<"$data") ($(jq '.Layers | length' <<<"$data") layers)"
  jq --arg ref "$ref" '{ref:$ref,digest:.Digest,layers:.Layers}' <<<"$data" >>"$tmp"
done < <(jq -r '.images[]' "$SOT")

jq -s '[.[].layers[]] | unique' "$tmp" >"$tmp.layers"
jq -s '[.[] | {ref,digest}]' "$tmp" >"$tmp.images"
jq --slurpfile keep "$tmp.layers" '[.[] | select(."compressed-diff-digest" as $d | $keep[0] | index($d))]' "$STORE/overlay-layers/layers.json" >"$STORE/overlay-layers/layers.json.new"
jq --slurpfile keep "$tmp.images" '[.[] as $image | select($keep[0] | any(.digest == $image.digest and (.ref as $ref | ($image.names // []) | index($ref)))) | $image]' "$STORE/overlay-images/images.json" >"$STORE/overlay-images/images.json.new"

if [[ " $* " == *" --prune "* ]]; then : >"$tmp.protected-images"; : >"$tmp.protected-layers"
  for runtime in /run/user/[0-9]*; do
    uid=${runtime##*/}; [[ $uid != 0 ]] || continue
    entry=$(getent passwd "$uid") || continue; IFS=: read -r user _ _ _ _ home _ <<<"$entry"
    user_env=(runuser -u "$user" -- env HOME="$home" USER="$user" XDG_RUNTIME_DIR="$runtime")
    while IFS='|' read -r name image; do
      jq -e --arg name "$name" '.images | any(. == $name or sub("^docker.io/"; "") == $name)' "$SOT" >/dev/null || continue
      image=${image#sha256:}; echo "PROTECT running $user $name $image"; printf '%s\n' "$image" >>"$tmp.protected-images"
      "${user_env[@]}" podman image inspect --format '{{json .RootFS.Layers}}' "$image" | jq -r '.[]' >>"$tmp.protected-layers"
    done < <("${user_env[@]}" podman ps -q | while read -r cid; do "${user_env[@]}" podman inspect --format '{{.ImageName}}|{{.Image}}' "$cid"; done)
  done
  sort -u "$tmp.protected-images" | jq -Rsc 'split("\n") | map(select(length > 0))' >"$tmp.pi"; sort -u "$tmp.protected-layers" | jq -Rsc 'split("\n") | map(select(length > 0))' >"$tmp.pl"
  jq --slurpfile ids "$tmp.pi" --slurpfile old "$STORE/overlay-images/images.json" '. + [$old[0][] | select(.id as $id | $ids[0] | index($id))] | unique_by(.id)' "$STORE/overlay-images/images.json.new" >"$tmp.in"; mv "$tmp.in" "$STORE/overlay-images/images.json.new"
  jq --slurpfile ids "$tmp.pl" --slurpfile old "$STORE/overlay-layers/layers.json" '. + [$old[0][] | select(."diff-digest" as $id | $ids[0] | index($id))] | unique_by(.id)' "$STORE/overlay-layers/layers.json.new" >"$tmp.ln"; mv "$tmp.ln" "$STORE/overlay-layers/layers.json.new"; fi

while jq -e '. as $all | any(.[]; (.parent // "") as $p | $p != "" and ($all | any(.id == $p) | not))' "$STORE/overlay-layers/layers.json.new" >/dev/null; do
  jq '. as $all | [.[] | select((.parent // "") as $p | $p == "" or ($all | any(.id == $p)))]' "$STORE/overlay-layers/layers.json.new" >"$tmp.chain"; mv "$tmp.chain" "$STORE/overlay-layers/layers.json.new"
done
jq --slurpfile layers "$STORE/overlay-layers/layers.json.new" '[.[] | select(.layer as $id | $layers[0] | any(.id == $id))]' "$STORE/overlay-images/images.json.new" >"$tmp.valid-images"; mv "$tmp.valid-images" "$STORE/overlay-images/images.json.new"

mapfile -t layers < <(jq -r '.[].id' "$STORE/overlay-layers/layers.json.new")
mapfile -t images < <(jq -r '.[].id' "$STORE/overlay-images/images.json.new")
for path in "$STORE"/overlay/[0-9a-f]*; do id=${path##*/}; if [[ " ${layers[*]} " == *" $id "* ]]; then echo "KEEP layer $id"; else echo "REMOVE layer $id"; rm -rf -- "$path"; fi; done
for path in "$STORE"/overlay-images/[0-9a-f]*; do id=${path##*/}; if [[ " ${images[*]} " == *" $id "* ]]; then echo "KEEP image $id"; else echo "REMOVE image $id"; rm -rf -- "$path"; fi; done
for path in "$STORE"/overlay-layers/*.tar-split.gz; do id=${path##*/}; id=${id%.tar-split.gz}; [[ " ${layers[*]} " == *" $id "* ]] || { echo "REMOVE metadata $id"; rm -f -- "$path"; }; done
find "$STORE/overlay/l" -xtype l -printf 'REMOVE link %p\n' -delete
chmod --reference="$STORE/overlay-layers/layers.json" "$STORE/overlay-layers/layers.json.new"; chown --reference="$STORE/overlay-layers/layers.json" "$STORE/overlay-layers/layers.json.new"
chmod --reference="$STORE/overlay-images/images.json" "$STORE/overlay-images/images.json.new"; chown --reference="$STORE/overlay-images/images.json" "$STORE/overlay-images/images.json.new"
mv -f "$STORE/overlay-layers/layers.json.new" "$STORE/overlay-layers/layers.json"; mv -f "$STORE/overlay-images/images.json.new" "$STORE/overlay-images/images.json"
echo "DONE images=${#images[@]} layers=${#layers[@]}"; du -sh "$STORE"
if [[ " $* " == *" --update "* ]]; then
  mkdir -p "$STORE"
  while read -r image; do
    echo "UPDATE $image"
    podman --root "$STORE" --runroot /run/containers/storage --storage-opt overlay.force_mask=shared --storage-opt overlay.mount_program=/usr/bin/fuse-overlayfs pull "${PULL_AUTH[@]}" "$image"
  done < <(jq -r '.images[]' "$SOT")
  echo "PERMISSIONS chmod -R a+rX $STORE"; chmod -R a+rX "$STORE"
fi
