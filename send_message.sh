#!/bin/bash
# send_message.sh — Send a Telegram message to Rafael via OpenClaw Gateway
# Usage: ./send_message.sh --message "Your message" [--agent italy | --account triggershotbot]

CHAT_ID="5475045993"
MESSAGE=""
ACCOUNT=""
AGENT=""
CONFIG="/home/openclaw/.openclaw/openclaw.json"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -m|--message)
      MESSAGE="$2"
      shift 2
      ;;
    --account)
      ACCOUNT="$2"
      shift 2
      ;;
    --agent)
      AGENT="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1"
      echo "Usage: $0 --message \"Your message\" [--agent <region> | --account <bot>]"
      exit 1
      ;;
  esac
done

if [ -z "$MESSAGE" ]; then
  echo "Usage: $0 --message \"Your message\" [--agent <region> | --account <bot>]"
  exit 1
fi

# Resolve --agent to --account via openclaw.json
if [ -n "$AGENT" ]; then
  ACCOUNT=$(jq -r --arg name "$AGENT" '
    .channels.telegram.accounts
    | to_entries[]
    | select(.value.name == $name)
    | .key
  ' "$CONFIG")

  if [ -z "$ACCOUNT" ]; then
    echo "✗ Unknown agent: $AGENT (no matching account found in openclaw.json)"
    exit 1
  fi
fi

# Default fallback
if [ -z "$ACCOUNT" ]; then
  ACCOUNT="magabuttlerbot"
fi

openclaw message send \
  --channel telegram \
  --account "${ACCOUNT}" \
  --target "${CHAT_ID}" \
  --message "${MESSAGE}"
