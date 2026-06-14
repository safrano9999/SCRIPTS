#!/usr/bin/env bash
# Install managed OpenClaw cronjobs and trigger the generated webhook script.
set -euo pipefail

log() { printf '[safrano9999-routines] %s\n' "$*"; }

fullrun_script="${SAFRANO9999_FULLRUN_SCRIPT:-${SAFRANO9999_WEBHOOK_SCRIPT:-/usr/local/bin/safrano9999-fullrun}}"

run_all() {
  [ -x "$fullrun_script" ] || { log "missing fullrun script: $fullrun_script"; return 1; }
  "$fullrun_script"
}

install_crons() {
  /usr/local/bin/openclaw-crontabs
}

init() {
  install_crons "$@" || true
  if [ "${SAFRANO9999_ROUTINES_RUN_ON_START:-1}" = "1" ]; then
    run_all || true
  fi
}

case "${1:-run}" in
  init)
    shift || true
    init "$@"
    ;;
  install-crons)
    shift || true
    install_crons "$@"
    ;;
  run)
    run_all
    ;;
  --crontab)
    install_crons "$@"
    ;;
  *)
    printf 'Usage: %s [init|install-crons|run] [--crontab "CET 23:49,CET 12:00"]\n' "$0" >&2
    exit 2
    ;;
esac
