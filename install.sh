#!/usr/bin/env bash
# Run locally, or: curl -fsSL https://raw.githubusercontent.com/xu-hao/agy-auto-mode-with-codex-reviewer/main/install.sh | bash
set -euo pipefail

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat <<'HELP'
Usage: install.sh [WORKSPACE] [--install-dir PATH] [--config PATH] [--model MODEL]

WORKSPACE defaults to the current directory. Builds the reviewer, creates a
private configuration, checks model access, and registers the Antigravity hook.
Missing Rust and Ubuntu/Debian build prerequisites are installed automatically.
Python 3.12+, codex and agy must already be installed. Active Codex and Antigravity
subscriptions, signed-in CLIs, and access to the reviewer model are required.
HELP
    exit 0
fi

agy_python="$(command -v python3 || true)"
if [[ -z "$agy_python" ]]; then
    echo 'Python 3.12+ is required. Install Python, then rerun this installer.' >&2
    exit 1
fi
"$agy_python" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else "Python 3.12+ is required.")'

agy_source="${BASH_SOURCE[0]:-}"
if [[ -n "$agy_source" && -f "$agy_source" ]]; then
    agy_source_dir="$(cd -- "$(dirname -- "$agy_source")" && pwd)"
    if [[ -f "$agy_source_dir/scripts/setup.py" && -f "$agy_source_dir/upstream.lock.json" ]]; then
        exec "$agy_python" "$agy_source_dir/scripts/setup.py" "$@"
    fi
fi

agy_download_dir="$(mktemp -d)"
trap 'rm -rf -- "$agy_download_dir"' EXIT
printf '%s\n' 'Downloading Auto mode for agy...'
"$agy_python" - "$agy_download_dir" <<'PY'
from pathlib import Path
import sys
import tarfile
import urllib.request

root = Path(sys.argv[1])
archive = root / 'source.tar.gz'
request = urllib.request.Request(
    'https://codeload.github.com/xu-hao/agy-auto-mode-with-codex-reviewer/tar.gz/refs/heads/main',
    headers={'User-Agent': 'agy-auto-mode-installer'},
)
with urllib.request.urlopen(request, timeout=60) as response, archive.open('wb') as target:
    import shutil
    shutil.copyfileobj(response, target)
with tarfile.open(archive, 'r:gz') as source:
    source.extractall(root / 'source', filter='data')
PY
agy_extracted=("$agy_download_dir"/source/*/scripts/setup.py)
if [[ ${#agy_extracted[@]} -ne 1 || ! -f "${agy_extracted[0]}" ]]; then
    echo 'Downloaded archive did not contain the installer.' >&2
    exit 1
fi
"$agy_python" "${agy_extracted[0]}" "$@"
