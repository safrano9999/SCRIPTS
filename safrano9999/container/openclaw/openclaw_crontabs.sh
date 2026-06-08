#!/usr/bin/env bash
set -euo pipefail
spec="${OPENCLAW_CRONTABS:-${OPENCLAW_CRONTAB:-$(cat /opt/safrano9999/.openclaw-crontab /opt/safrano9999-openclaw/.openclaw-crontab 2>/dev/null || true)}}"; token=(); [ -z "${OPENCLAW_GATEWAY_TOKEN:-}" ] || token=(--token "$OPENCLAW_GATEWAY_TOKEN")
prefix=safrano9999-routines-europe-vienna-
for id in $(openclaw cron list "${token[@]}" --json | python3 -c 'import json,sys; print(*[j["id"] for j in json.load(sys.stdin).get("jobs",[]) if j.get("name","").startswith("safrano9999-routines-europe-vienna-")])'); do openclaw cron remove "$id" "${token[@]}" --json >/dev/null; done
IFS=,; for e in $spec; do t="$(echo "${e#CET }" | xargs)"; h="${t%:*}"; m="${t#*:}"; openclaw cron create "$((10#$m)) $((10#$h)) * * *" --name "$prefix$(printf "%02d%02d" "$((10#$h))" "$((10#$m))")" --agent main --session main --tz Europe/Vienna --exact --system-event "${OPENCLAW_CRON_MESSAGE:-__safrano9999_webhooks__}" "${token[@]}" --json >/dev/null; done
