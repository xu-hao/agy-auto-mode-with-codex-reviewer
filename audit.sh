#!/usr/bin/env bash
set -euo pipefail
agy_script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$agy_script_dir/scripts/audit.py" "$@"
