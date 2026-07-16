#!/usr/bin/env bash
# OpenClaw plugins container entrypoint.
# The official OpenClaw image boots through tini; keep that base flow and do the
# small deterministic setup here before exec'ing the gateway.
set -euo pipefail

log() { printf '[entrypoint] %s\n' "$*"; }

if command -v openclaw >/dev/null 2>&1; then
  OPENCLAW_CMD=(openclaw)
elif [ -f /app/openclaw.mjs ]; then
  OPENCLAW_CMD=(node /app/openclaw.mjs)
else
  log "FATAL: cannot find the openclaw CLI"
  exit 1
fi
export OPENCLAW_BIN="${OPENCLAW_CMD[*]}"

/usr/local/bin/named_volume_links.sh

TS_STATE_DIR="${TS_STATE_DIR:-/var/lib/tailscale}"
if [ -n "${TS_AUTHKEY:-}" ] || [ -s "${TS_STATE_DIR}/tailscaled.state" ]; then
  log "starting tailscaled (state: ${TS_STATE_DIR})"
  mkdir -p "${TS_STATE_DIR}" /run/tailscale
  tailscaled --state="${TS_STATE_DIR}/tailscaled.state" \
             --socket=/run/tailscale/tailscaled.sock >/var/log/tailscaled.log 2>&1 &
  if /usr/local/bin/tailscale-state-up.sh; then
    log "tailscale up: $(tailscale ip -4 2>/dev/null | head -1 || echo '?')"
  else
    log "WARN: 'tailscale up' failed - continuing without tailnet"
  fi
else
  log "Tailscale state and TS_AUTHKEY not set - skipping Tailscale"
fi

log "configuring OpenClaw (plugins only; no OpenClaw LLM provider)"
/usr/local/bin/openclaw-configure

zdir="${OPENCLAW_CONFIG_DIR:-/root/.openclaw}/extensions/zeroinbox"
if [ -f "${zdir}/scripts/gmail-init-labels" ]; then
  log "running ZEROINBOX label init"
  if ( cd "${zdir}" && python3 scripts/gmail-init-labels --account all ); then
    log "ZEROINBOX label init done"
  else
    log "WARN: ZEROINBOX label init failed - continuing"
  fi
fi

kdir="${OPENCLAW_CONFIG_DIR:-/root/.openclaw}/extensions/kachelmann"
if [ -n "${KACHELMANN_PORT:-}" ]; then
  if [ -f "${kdir}/webui.py" ]; then
    log "starting KACHELMANN WebUI on 0.0.0.0:${KACHELMANN_PORT}"
    ( cd "${kdir}" && exec python3 -m uvicorn webui:app --host 0.0.0.0 --port "${KACHELMANN_PORT}" ) \
      >/var/log/kachelmann-webui.log 2>&1 &
    for _ in {1..30}; do
      curl -sS -o /dev/null "http://127.0.0.1:${KACHELMANN_PORT}/" 2>/dev/null && break
      sleep 0.2
    done
  else
    log "WARN: KACHELMANN webui.py missing - WebUI not started"
  fi
fi

if [ -n "${KACHELMANN_MCP_PORT:-}" ]; then
  if [ -f "${kdir}/kachelmann/mcp_server.py" ]; then
    log "starting KACHELMANN MCP HTTP on 0.0.0.0:${KACHELMANN_MCP_PORT}/mcp"
    ( cd "${kdir}" && exec python3 -m kachelmann.mcp_server --transport streamable-http ) \
      >/var/log/kachelmann-mcp-http.log 2>&1 &
  else
    log "WARN: KACHELMANN MCP server missing - HTTP MCP not started"
  fi
fi

cdir="${OPENCLAW_CONFIG_DIR:-/root/.openclaw}/extensions/citadel"
if [ -x "${cdir}/scan.sh" ]; then
  log "scanning services for CITADEL"
  if (cd "$cdir" && ./scan.sh) >/var/log/citadel-scan.log 2>&1; then
    log "CITADEL scan done"
  else
    log "WARN: CITADEL localhost scan failed - continuing"
  fi
fi

gw_args=(gateway run --bind lan --port "${OPENCLAW_GATEWAY_PORT:-18789}")
if [ -n "${OPENCLAW_GATEWAY_TOKEN:-}" ]; then
  gw_args+=(--auth token)
fi

if [ -x /usr/local/bin/openclaw-crontabs ]; then
  ( sleep "${OPENCLAW_CRON_SETUP_DELAY:-20}"; /usr/local/bin/openclaw-crontabs ) &
fi
if [ "${SAFRANO9999_FULLRUN_ON_START:-1}" = "1" ] && [ -x "${SAFRANO9999_FULLRUN_SCRIPT:-/usr/local/bin/safrano9999-fullrun}" ]; then
  ( sleep "${SAFRANO9999_FULLRUN_DELAY:-100}"; "${SAFRANO9999_FULLRUN_SCRIPT:-/usr/local/bin/safrano9999-fullrun}" ) &
fi

log "starting gateway: ${OPENCLAW_CMD[*]} ${gw_args[*]}"
exec "${OPENCLAW_CMD[@]}" "${gw_args[@]}"
