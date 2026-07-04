#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
requirements="$root/requirements.txt"
venv_python="$root/.venv/bin/python"
python="$(command -v python3 || true)"

requirements_satisfied() {
    local candidate="$1" report
    [ -f "$requirements" ] || return 0
    "$candidate" -m pip --version >/dev/null 2>&1 || return 1
    report="$(mktemp)"
    "$candidate" -m pip install --dry-run --report "$report" -r "$requirements" >/dev/null 2>&1 \
        && "$candidate" -c 'import json,sys; raise SystemExit(bool(json.load(open(sys.argv[1]))["install"]))' "$report"
    local status=$?
    rm -f "$report"
    return "$status"
}

if [ -x "$venv_python" ]; then
    requirements_satisfied "$venv_python" && { printf '%s\n' "$venv_python"; exit 0; }
elif [ -n "$python" ]; then
    if requirements_satisfied "$python"; then
        printf '%s\n' "$python"
        exit 0
    fi
    if "$python" -m pip install -r "$requirements" >&2 && requirements_satisfied "$python"; then
        printf '%s\n' "$python"
        exit 0
    fi
fi

uv="$root/.uv/bin/uv"
if [ ! -x "$uv" ]; then
    mkdir -p "$(dirname "$uv")"
    if command -v curl >/dev/null 2>&1; then
        UV_UNMANAGED_INSTALL="$(dirname "$uv")" UV_NO_MODIFY_PATH=1 sh -c "$(curl -LsSf https://astral.sh/uv/install.sh)" >&2
    elif command -v wget >/dev/null 2>&1; then
        UV_UNMANAGED_INSTALL="$(dirname "$uv")" UV_NO_MODIFY_PATH=1 sh -c "$(wget -qO- https://astral.sh/uv/install.sh)" >&2
    else
        echo "curl or wget is required to install uv" >&2
        exit 1
    fi
fi

if [ -n "$python" ]; then
    "$uv" venv --clear --seed --python "$python" "$root/.venv" >&2
else
    "$uv" python install "${SAFRANO9999_PYTHON_VERSION:-3.12}" >&2
    "$uv" venv --clear --seed --python "${SAFRANO9999_PYTHON_VERSION:-3.12}" "$root/.venv" >&2
fi
[ ! -f "$requirements" ] || "$uv" pip install --python "$venv_python" -r "$requirements" >&2
printf '%s\n' "$venv_python"
