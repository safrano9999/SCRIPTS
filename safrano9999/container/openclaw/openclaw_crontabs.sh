#!/usr/bin/env bash
set -euo pipefail
spec="${OPENCLAW_CRONTABS:-${OPENCLAW_CRONTAB:-$(cat "${OPENCLAW_CRONTAB_FILE:-/etc/safrano9999/openclaw-crontabs.conf}" 2>/dev/null || true)}}"
url="${OPENCLAW_CRON_URL:-ws://127.0.0.1:${OPENCLAW_GATEWAY_PORT:-18789}}"; auth=(--url "$url"); [ -z "${OPENCLAW_GATEWAY_TOKEN:-}" ] || auth+=(--token "$OPENCLAW_GATEWAY_TOKEN")
prefix=safrano9999-routines-europe-vienna-
for _ in $(seq 1 30); do jobs="$(openclaw cron list "${auth[@]}" --json 2>/dev/null)" && break; sleep 2; done; [ -n "${jobs:-}" ]
for id in $(printf '%s' "$jobs" | python3 -c 'import json,sys; print(*[j["id"] for j in json.load(sys.stdin).get("jobs",[]) if j.get("name","").startswith("safrano9999-routines-europe-vienna-")])'); do openclaw cron rm "$id" "${auth[@]}" --json >/dev/null; done
IFS=,; for e in $spec; do t="$(echo "${e#CET }" | xargs)"; h="${t%:*}"; m="${t#*:}"; args=(--cron "$((10#$m)) $((10#$h)) * * *" --name "$prefix$(printf "%02d%02d" "$((10#$h))" "$((10#$m))")" --agent main --session main --session-key agent:main:main --tz Europe/Vienna --exact --system-event "${OPENCLAW_CRON_MESSAGE:-__safrano9999_webhooks__}" "${auth[@]}" --json); openclaw cron add "${args[@]}" >/dev/null 2>&1 || { /usr/local/bin/openclaw-allow-all; openclaw cron add "${args[@]}" >/dev/null; }; done
