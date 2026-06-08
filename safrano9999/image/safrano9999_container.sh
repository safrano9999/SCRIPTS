#!/usr/bin/env bash
# Containerfile helpers for safcontainer repos.
set -euo pipefail

_safrano9999_repo_name() {
  printf '%s' "${1%@*}"
}

_safrano9999_repo_ref() {
  if [ "$1" != "${1%@*}" ]; then
    printf '%s' "${1#*@}"
  fi
}

_safrano9999_clone() {
  local spec="$1" root="$2" repo ref url stage lower zip
  repo="$(_safrano9999_repo_name "$spec")"
  ref="$(_safrano9999_repo_ref "$spec")"
  stage="${SAFRANO9999_STAGE_DIR:-}"
  mkdir -p "$root"
  rm -rf "$root/$repo"
  if [ -n "$stage" ] && [ -d "$stage/$repo" ]; then
    cp -a "$stage/$repo" "$root/$repo"
    rm -rf "$root/$repo/.git"
    return
  fi
  lower="$(printf '%s' "$repo" | tr '[:upper:]' '[:lower:]')"
  zip="${stage}/${lower}-latest.zip"
  if [ -n "$stage" ] && [ -f "$zip" ]; then
    mkdir -p "$root/$repo"
    unzip -q "$zip" -d "$root/$repo"
    rm -rf "$root/$repo/.git"
    return
  fi
  if [ -n "${GH_TOKEN:-}" ]; then
    url="https://x-access-token:${GH_TOKEN}@github.com/safrano9999/${repo}.git"
  else
    url="https://github.com/safrano9999/${repo}.git"
  fi
  if [ -n "$ref" ]; then
    git clone --depth 1 --branch "$ref" "$url" "$root/$repo"
  else
    git clone --depth 1 "$url" "$root/$repo"
  fi
  rm -rf "$root/$repo/.git"
}

_safrano9999_webhook_curl() {
  local repo_dir="$1" readme="$1/README.md" manifest="$1/openclaw.plugin.json" index="$1/index.js" curl_cmd path
  if [ -f "$readme" ]; then
    curl_cmd="$(_safrano9999_readme_curl "$repo_dir" || true)"
    [ -n "$curl_cmd" ] && { printf '%s\n' "$curl_cmd"; return; }
  fi
  if [ -f "$manifest" ]; then
    path="$(python3 - "$manifest" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
props = data.get("configSchema", {}).get("properties", {})
print(props.get("webhook", {}).get("properties", {}).get("path", {}).get("default", ""))
PY
)"
  fi
  if [ -z "${path:-}" ] && [ -f "$index" ]; then
    path="$(python3 - "$index" <<'PY'
import re, sys
text = open(sys.argv[1], encoding="utf-8").read()
match = re.search(r"registerHttpRoute\s*\(\s*\{.*?path:\s*[\"']([^\"']+)[\"']", text, re.S)
print(match.group(1) if match else "")
PY
)"
  fi
  [ -n "${path:-}" ] && printf 'curl -sS -X POST -H "Authorization: Bearer ${OPENCLAW_GATEWAY_TOKEN}" "http://127.0.0.1:${OPENCLAW_GATEWAY_PORT:-18789}%s"\n' "$path"
}

_safrano9999_readme_curl() {
  local readme="$1/README.md"
  [ -f "$readme" ] || return 1
  awk '
    tolower($0) ~ /enter this to trigger webhook from inside container/ { want=1; next }
    want && /^[[:space:]]*curl[[:space:]]/ { sub(/^[[:space:]]*/, ""); print; exit }
  ' "$readme"
}

_safrano9999_write_webhooks() {
  local root="$1" script="${SAFRANO9999_WEBHOOK_SCRIPT:-/usr/local/bin/safrano9999-webhooks}" cmd repo
  shift
  mkdir -p "$(dirname "$script")"
  {
    printf '%s\n' '#!/usr/bin/env bash'
    printf '%s\n' 'set -euo pipefail'
    for repo in "$@"; do
      cmd="$(_safrano9999_webhook_curl "$root/$repo" || true)"
      [ -n "$cmd" ] && printf '%s\n' "$cmd"
    done
  } > "$script"
  chmod +x "$script"
}

_safrano9999_write_fullrun() {
  local root="$1" script="${SAFRANO9999_FULLRUN_SCRIPT:-/usr/local/bin/safrano9999-fullrun}" cmd repo
  shift
  mkdir -p "$(dirname "$script")"
  {
    printf '%s\n' '#!/usr/bin/env bash'
    printf '%s\n' 'set -euo pipefail'
    for repo in "$@"; do
      cmd="$(_safrano9999_readme_curl "$root/$repo")"
      [ -n "$cmd" ] || { echo "missing README webhook curl: $repo" >&2; return 1; }
      printf '%s\n' "$cmd"
    done
  } > "$script"
  chmod +x "$script"
}

_safrano9999_write_webhook_runner() {
  local root="$1"
  local runner="$root/WEBHOOK-RUNNER"
  mkdir -p "$runner"
  cat > "$runner/package.json" <<'JSON'
{"name":"safrano9999-webhooks","version":"0.1.0","private":true,"type":"module","dependencies":{},"openclaw":{"extensions":["./index.js"]}}
JSON
  cat > "$runner/openclaw.plugin.json" <<'JSON'
{"id":"safrano9999-webhooks","name":"safrano9999 webhooks","description":"Runs deterministic safcontainer webhooks for managed cron events.","activation":{"onStartup":true},"configSchema":{"type":"object","additionalProperties":false}}
JSON
  cat > "$runner/index.js" <<'JS'
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

const execFileAsync = promisify(execFile);
const cronToken = "__safrano9999_webhooks__";
const script = process.env.SAFRANO9999_FULLRUN_SCRIPT || process.env.SAFRANO9999_WEBHOOK_SCRIPT || "/usr/local/bin/safrano9999-fullrun";

export default definePluginEntry({
  id: "safrano9999-webhooks",
  name: "safrano9999 webhooks",
  description: "Runs deterministic safcontainer webhooks for managed cron events.",
  register(api) {
    api.on("before_agent_reply", async (event) => {
      if (!event.cleanedBody?.includes(cronToken)) return undefined;
      await execFileAsync(script);
      return { handled: true, reason: "safrano9999 webhooks completed" };
    });
  },
});
JS
}

safrano9999_standalone() {
  local root="${SAFRANO9999_DIR:-/opt/safrano9999}" spec
  [ "$#" -gt 0 ] || { echo "safrano9999_standalone: repo name required" >&2; return 2; }
  for spec in "$@"; do _safrano9999_clone "$spec" "$root"; done
}

safrano9999_OC_plugins() {
  local root="${OPENCLAW_PLUGINS_DIR:-${SAFRANO9999_DIR:-/opt/safrano9999}}" link=false fullrun=false crontab="" spec
  local -a specs=() repos=() install_args setup_args
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --link) link=true; shift ;;
      --fullrun) fullrun=true; shift ;;
      --crontab) crontab="${2:-}"; shift 2 ;;
      --) shift; break ;;
      *) specs+=("$1"); shift ;;
    esac
  done
  specs+=("$@")
  [ "${#specs[@]}" -gt 0 ] || { echo "safrano9999_OC_plugins: repo name required" >&2; return 2; }
  for spec in "${specs[@]}"; do
    _safrano9999_clone "$spec" "$root"
    repos+=("$(_safrano9999_repo_name "$spec")")
  done
  _safrano9999_write_webhooks "$root" "${repos[@]}"
  [ "$fullrun" = false ] || _safrano9999_write_fullrun "$root" "${repos[@]}"
  _safrano9999_write_webhook_runner "$root"
  [ -z "$crontab" ] || printf '%s\n' "$crontab" > "$root/.openclaw-crontab"

  if [ -f /usr/local/bin/safrano9999_plugins.py ]; then
    setup_args=(setup-python --plugins-dir "$root" --fallback-venv --plugins "${repos[@]}")
    python3 /usr/local/bin/safrano9999_plugins.py "${setup_args[@]}"
    install_args=(install --plugins-dir "$root")
    [ "$link" = true ] && install_args+=(--links)
    install_args+=(--plugins "${repos[@]}")
    python3 /usr/local/bin/safrano9999_plugins.py "${install_args[@]}"
  fi
}
