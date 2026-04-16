#!/usr/bin/env bash
# devmode.sh — Restore dev-mode symlinks in the current repo.
#
# Use case: after `git clone` or `git pull` the shared files (install.py,
# python_header.py, provider_example) may exist as real files or dangling
# symlinks. This script deletes them and recreates proper symlinks to
# ../SCRIPTS/ (relative), assuming SCRIPTS is a sibling of the repo.
#
# Run from inside any repo:
#     bash ../SCRIPTS/devmode.sh
# or
#     ~/saf/SCRIPTS/devmode.sh
#
set -euo pipefail

# Resolve repo root = CWD (user runs from inside the repo)
REPO_DIR="$(pwd)"
REPO_NAME="$(basename "$REPO_DIR")"

# Find SCRIPTS sibling
SCRIPTS_DIR="$(cd "$(dirname "$(realpath "${BASH_SOURCE[0]}")")" && pwd)"
WORKSPACE="$(dirname "$SCRIPTS_DIR")"

if [[ "$(dirname "$REPO_DIR")" != "$WORKSPACE" ]]; then
    echo "[error] Repo must be a sibling of SCRIPTS."
    echo "  repo:    $REPO_DIR"
    echo "  scripts: $SCRIPTS_DIR"
    echo "  expected parent: $WORKSPACE"
    exit 1
fi

echo "=== devmode: $REPO_NAME ==="

# (path_in_repo, target_in_SCRIPTS)
declare -a LINKS=(
    "provider_example|provider_example"
    "functions/install.py|install.py"
    "functions/python_header.py|python_header.py"
)

for entry in "${LINKS[@]}"; do
    rel_path="${entry%|*}"
    target_name="${entry##*|}"
    full_path="$REPO_DIR/$rel_path"
    target_file="$SCRIPTS_DIR/$target_name"

    # Skip if target doesn't exist in SCRIPTS
    if [[ ! -f "$target_file" ]]; then
        echo "  [skip] $rel_path (no $target_name in SCRIPTS)"
        continue
    fi

    # Skip if the path isn't expected in this repo (e.g. no functions/ dir)
    parent_dir="$(dirname "$full_path")"
    if [[ ! -d "$parent_dir" ]]; then
        echo "  [skip] $rel_path (no $(dirname "$rel_path")/ in repo)"
        continue
    fi

    # Compute relative path from $parent_dir to $target_file
    # e.g. from functions/ → ../../SCRIPTS/install.py
    # e.g. from repo root → ../SCRIPTS/provider_example
    depth="$(echo "$rel_path" | tr -cd '/' | wc -c)"
    prefix=""
    for ((i=0; i<=depth; i++)); do prefix="../$prefix"; done
    rel_target="${prefix}SCRIPTS/$target_name"

    # Remove whatever is there
    if [[ -e "$full_path" ]] || [[ -L "$full_path" ]]; then
        rm -f "$full_path"
    fi

    ln -s "$rel_target" "$full_path"
    echo "  [link] $rel_path -> $rel_target"
done

echo "[ok] devmode restored."
