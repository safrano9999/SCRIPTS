#!/bin/bash
# push_all.sh — Commit & Push aller Git-Repos im übergeordneten Verzeichnis
#
# Erkennt den GitHub-Account aus dem Ordnernamen von `cd ..`
# Iteriert über alle Unterordner mit .git, committed mit Timestamp und pusht.
#
# Usage: bash push_all.sh

set -euo pipefail

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
ACCOUNT="$(basename "$BASE_DIR")"
TIMESTAMP="$(date '+%Y-%m-%d %H:%M')"

echo "Account:    $ACCOUNT"
echo "Base:       $BASE_DIR"
echo "Timestamp:  $TIMESTAMP"
echo "========================================="
echo

pushed=0
skipped=0
failed=0

while IFS= read -r gitdir; do
  repo="$(dirname "$gitdir")"
  name="$(basename "$repo")"

  if [ "$repo" = "$BASE_DIR" ]; then
    echo "── (root) ── übersprungen (nur Unterordner werden gepusht)"
    echo
    continue
  fi

  echo "── $name ──"
  cd "$repo"

  # Prüfe ob origin auf den richtigen Account zeigt
  origin=$(git remote get-url origin 2>/dev/null || echo "")
  if [ -z "$origin" ]; then
    echo "   Kein remote 'origin' — übersprungen"
    ((skipped++)) || true
    echo
    continue
  fi

  if ! echo "$origin" | grep -qi "$ACCOUNT"; then
    echo "   Origin gehört nicht zu $ACCOUNT — übersprungen"
    ((skipped++)) || true
    echo
    continue
  fi

  # Status prüfen
  changes=$(git status --porcelain 2>/dev/null)
  if [ -z "$changes" ]; then
    echo "   Keine Änderungen"
    ((skipped++)) || true
    echo
    continue
  fi

  total=$(echo "$changes" | wc -l)
  echo "   $total geänderte Datei(en)"

  # Sicherheitscheck: Abbruch wenn sensible Dateien staged würden
  FORBIDDEN_PATTERNS=("*env" "*.env" "venv/" ".venv/" "__pycache__/" "node_modules/" "*.pyc" ".env.*")
  blocked=""
  for pat in "${FORBIDDEN_PATTERNS[@]}"; do
    matches=$(echo "$changes" | grep -E "$(echo "$pat" | sed 's/\*/.*/')" || true)
    if [ -n "$matches" ]; then
      blocked+="$matches"$'\n'
    fi
  done
  if [ -n "$blocked" ]; then
    echo "   ⚠ ABBRUCH — sensible Dateien erkannt (nicht in .gitignore?):"
    echo "$blocked" | head -5 | sed 's/^/      /'
    echo "   → .gitignore prüfen! Übersprungen."
    ((failed++)) || true
    echo
    continue
  fi

  # Commit & Push
  if ! git add -A 2>&1 | sed 's/^/   /'; then
    echo "   → git add fehlgeschlagen (Submodul-Problem?)"
    ((failed++)) || true
    echo
    continue
  fi
  git commit -m "sync $TIMESTAMP" 2>&1 | tail -1 | sed 's/^/   /'
  if git push origin HEAD 2>&1 | sed 's/^/   /'; then
    echo "   → OK"
    ((pushed++)) || true
  else
    echo "   → Push fehlgeschlagen"
    ((failed++)) || true
  fi
  echo

done < <(find "$BASE_DIR" -maxdepth 3 -name ".git" -type d 2>/dev/null | sort)

echo "========================================="
echo "Gepusht: $pushed  Übersprungen: $skipped  Fehler: $failed"
