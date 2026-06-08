#!/usr/bin/env bash
set -euo pipefail
spec="${OPENCLAW_CRONTABS:-${OPENCLAW_CRONTAB:-$(cat /opt/safrano9999/.openclaw-crontab /opt/safrano9999-openclaw/.openclaw-crontab 2>/dev/null || true)}}"; token=(); [ -z "${OPENCLAW_GATEWAY_TOKEN:-}" ] || token=(--token "$OPENCLAW_GATEWAY_TOKEN")
IFS=,; for e in $spec; do t="$(echo "${e#CET }" | xargs)"; h="${t%:*}"; m="${t#*:}"; openclaw cron create "$((10#$m)) $((10#$h)) * * *" --name "safrano9999-routines-europe-vienna-$(printf "%02d%02d" "$((10#$h))" "$((10#$m))")" --agent main --session main --tz Europe/Vienna --exact --command "${OPENCLAW_CRON_COMMAND:-/usr/local/bin/safrano9999-fullrun}" --announce --channel "${OPENCLAW_CRON_CHANNEL:-telegram}" --to "${OPENCLAW_CRON_TO:-$OPENCLAW_TELEGRAM_TARGET}" "${token[@]}" --json >/dev/null; done
