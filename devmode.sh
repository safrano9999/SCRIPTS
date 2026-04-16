#!/usr/bin/env bash
# devmode.sh — Restore dev-mode symlinks across all sibling repos.
#
# Walks every sibling of SCRIPTS/. For each shared file in SCRIPTS/,
# if that filename also exists (as file or symlink) anywhere in the
# sibling repo, replace it with a relative symlink back to SCRIPTS/.
#
# Run once:
#     bash ~/saf/SCRIPTS/devmode.sh
#
set -euo pipefail

SCRIPTS_DIR="$(cd "$(dirname "$(realpath "${BASH_SOURCE[0]}")")" && pwd)"
WORKSPACE="$(dirname "$SCRIPTS_DIR")"

# Files in SCRIPTS that should be distributed as symlinks into sibling repos
SHARED_FILES=(
    "install.py"
    "python_header.py"
    "provider_example"
)

echo "=== devmode: workspace $WORKSPACE ==="

for repo in "$WORKSPACE"/*/; do
    repo_name="$(basename "$repo")"
    [[ "$repo_name" == "SCRIPTS" ]] && continue
    [[ ! -d "$repo/.git" ]] && continue

    echo
    echo "--- $repo_name ---"

    for shared in "${SHARED_FILES[@]}"; do
        source_file="$SCRIPTS_DIR/$shared"
        [[ ! -f "$source_file" ]] && continue

        # Find every occurrence of this filename in the repo (excl. .git)
        # shellcheck disable=SC2044
        mapfile -t matches < <(find "$repo" -name "$shared" -not -path "*/.git/*" -not -path "*/venv/*" 2>/dev/null)

        if [[ ${#matches[@]} -eq 0 ]]; then
            continue
        fi

        for match in "${matches[@]}"; do
            # Compute relative symlink target from the file's directory to SCRIPTS/<shared>
            parent_dir="$(dirname "$match")"
            rel_from_parent="$(realpath --relative-to="$parent_dir" "$source_file")"

            rm -f "$match"
            ln -s "$rel_from_parent" "$match"
            # Print friendly relative path from workspace
            echo "  [link] ${match#$WORKSPACE/} -> $rel_from_parent"
        done
    done
done

echo
echo "[ok] devmode restored."
