#!/usr/bin/env bash
set -euo pipefail

expected="${1:-safrano9999}"
command -v gh >/dev/null || { echo "Missing GitHub CLI: gh" >&2; exit 1; }
account="$(gh api user --jq .login 2>/dev/null || true)"
[[ "${account,,}" == "${expected,,}" ]] && exit 0
if gh auth switch --hostname github.com --user "$expected" >/dev/null 2>&1; then
  account="$(gh api user --jq .login 2>/dev/null || true)"
  [[ "${account,,}" == "${expected,,}" ]] && exit 0
fi

echo "GitHub login required for ${expected}."
gh auth login --hostname github.com --git-protocol https --web
account="$(gh api user --jq .login)"
[[ "${account,,}" == "${expected,,}" ]] || { echo "Active GitHub account is ${account}, expected ${expected}." >&2; exit 1; }
