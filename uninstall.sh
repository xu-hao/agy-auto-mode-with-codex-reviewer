#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    echo 'Usage: uninstall.sh [WORKSPACE]'
    echo 'Removes this workspace hook. WORKSPACE defaults to the current directory.'
    echo 'Other hooks, permission rules, credentials, and local files are preserved.'
    exit 0
fi
if [[ $# -gt 1 ]]; then
    echo 'Usage: uninstall.sh [WORKSPACE]' >&2
    exit 2
fi
agy_script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$agy_script_dir/bridge.py" uninstall --workspace "${1:-$PWD}"
