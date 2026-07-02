#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-$(pwd)}"
if [ -n "${CONFIG_CONTAINER_NAME:-}" ]; then
  ENV_FILE="$ROOT/$CONFIG_CONTAINER_NAME.env"
  CONFIG_FILE="$ROOT/${CONFIG_CONTAINER_NAME}_config.conf"
  CONTAINER_FILE="$ROOT/${CONFIG_CONTAINER_NAME}_container.conf"
else
  ENV_FILE="$ROOT/.env"
  CONFIG_FILE="$ROOT/config.conf"
  CONTAINER_FILE="$ROOT/container.conf"
fi

trim() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}

key_from_line() {
  local line stripped key
  stripped="$(trim "$1")"
  [[ -z "$stripped" || "$stripped" == \#* || "$stripped" != *=* ]] && return 1
  key="$(trim "${stripped%%=*}")"
  key="${key#export }"
  key="$(trim "$key")"
  [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || return 1
  printf '%s\n' "$key"
}

load_expected() {
  local file line key
  EXPECTED=()
  for file in "$@"; do
    [ -f "$file" ] || continue
    while IFS= read -r line || [ -n "$line" ]; do
      key="$(key_from_line "$line" || true)"
      [ -n "$key" ] || continue
      EXPECTED["$key"]=1
    done < "$file"
  done
}

known_key() {
  local key="$1"
  [[ "$key" == *_API_KEY ]] && return 0
  while [ -n "$key" ]; do
    [ -n "${EXPECTED[$key]:-}" ] && return 0
    [[ "$key" == *_* ]] || break
    key="${key%_*}"
  done
  return 1
}

find_legacy() {
  local actual="$1" line key
  shift
  LEGACY=()
  load_expected "$@"
  [ -f "$actual" ] || return 0
  while IFS= read -r line || [ -n "$line" ]; do
    key="$(key_from_line "$line" || true)"
    [ -n "$key" ] || continue
    known_key "$key" || LEGACY["$key"]=1
  done < "$actual"
}

rewrite_file() {
  local file="$1" action="$2" keys="$3" tmp
  tmp="$(mktemp)"
  awk -v action="$action" -v keys="$keys" '
    function trim(s) { sub(/^[[:space:]]+/, "", s); sub(/[[:space:]]+$/, "", s); return s }
    function key_of(line,    s,k) {
      s=trim(line)
      if (s == "" || s ~ /^#/ || index(s, "=") == 0) return ""
      k=trim(substr(s, 1, index(s, "=") - 1))
      sub(/^export[[:space:]]+/, "", k)
      return k ~ /^[A-Za-z_][A-Za-z0-9_]*$/ ? k : ""
    }
    BEGIN {
      n=split(keys, parts, "\034")
      for (i=1; i<=n; i++) if (parts[i] != "") legacy[parts[i]]=1
    }
    {
      k=key_of($0)
      if (k in legacy) {
        if (action == "comment") { print "# " $0; next }
        if (action == "delete") next
      }
      print
    }
  ' "$file" > "$tmp"
  mv "$tmp" "$file"
}

declare -A EXPECTED LEGACY
declare -a all_entries=() keys_env=() keys_conf=() keys_container=()
declare -a env_examples=() config_examples=() container_examples=()

shopt -s nullglob
env_examples=("$ROOT"/env*example)
config_examples=("$ROOT"/config*example)
container_examples=("$ROOT"/container*example "$ROOT"/config*.container)
shopt -u nullglob

find_legacy "$ENV_FILE" "${env_examples[@]}"
for key in "${!LEGACY[@]}"; do keys_env+=("$key"); all_entries+=("$(basename "$ENV_FILE"):$key"); done

find_legacy "$CONFIG_FILE" "${config_examples[@]}"
for key in "${!LEGACY[@]}"; do keys_conf+=("$key"); all_entries+=("$(basename "$CONFIG_FILE"):$key"); done

find_legacy "$CONTAINER_FILE" "${container_examples[@]}"
for key in "${!LEGACY[@]}"; do keys_container+=("$key"); all_entries+=("$(basename "$CONTAINER_FILE"):$key"); done

[ "${#all_entries[@]}" -gt 0 ] || { echo "  Legacy check: skipped."; exit 0; }

printf '  Legacy found:\n'
[ "${#keys_env[@]}" -gt 0 ] && printf '    %s: %s\n' "$(basename "$ENV_FILE")" "${keys_env[*]}"
[ "${#keys_conf[@]}" -gt 0 ] && printf '    %s: %s\n' "$(basename "$CONFIG_FILE")" "${keys_conf[*]}"
[ "${#keys_container[@]}" -gt 0 ] && printf '    %s: %s\n' "$(basename "$CONTAINER_FILE")" "${keys_container[*]}"
printf '    (values hidden)\n'
printf '    (1) ignore / skip [default]\n'
printf '    (2) comment out\n'
printf '    (3) delete\n'

choice="1"
read -r -p "  Choose [1/2/3] (default: 1): " choice || choice="1"
choice="${choice:-1}"

case "$choice" in
  1) echo "  Legacy check: ignored." ;;
  2)
    [ "${#keys_env[@]}" -eq 0 ] || rewrite_file "$ENV_FILE" comment "$(printf '%s\034' "${keys_env[@]}")"
    [ "${#keys_conf[@]}" -eq 0 ] || rewrite_file "$CONFIG_FILE" comment "$(printf '%s\034' "${keys_conf[@]}")"
    [ "${#keys_container[@]}" -eq 0 ] || rewrite_file "$CONTAINER_FILE" comment "$(printf '%s\034' "${keys_container[@]}")"
    echo "  Legacy check: commented."
    ;;
  3)
    [ "${#keys_env[@]}" -eq 0 ] || rewrite_file "$ENV_FILE" delete "$(printf '%s\034' "${keys_env[@]}")"
    [ "${#keys_conf[@]}" -eq 0 ] || rewrite_file "$CONFIG_FILE" delete "$(printf '%s\034' "${keys_conf[@]}")"
    [ "${#keys_container[@]}" -eq 0 ] || rewrite_file "$CONTAINER_FILE" delete "$(printf '%s\034' "${keys_container[@]}")"
    echo "  Legacy check: deleted."
    ;;
  *) echo "Invalid choice: $choice" >&2; exit 2 ;;
esac
