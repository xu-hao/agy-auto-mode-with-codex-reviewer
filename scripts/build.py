#!/usr/bin/env python3
"""Build the standalone adapter against the unmodified pinned vendored source."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
ROOT = Path(__file__).resolve().parents[1]
if not (ROOT/'vendor/codex/codex-rs/Cargo.toml').exists():
    subprocess.run(['python3',str(ROOT/'scripts/vendor.py')],check=True)
for name,expected in json.loads((ROOT/'vendor/guardian.sha256.json').read_text()).items():
    if hashlib.sha256((ROOT/'vendor/codex'/name).read_bytes()).hexdigest()!=expected:
        raise SystemExit(f'Borrowed Guardian source changed: {name}')
lock=ROOT/'native/Cargo.lock'
if not lock.exists():shutil.copyfile(ROOT/'vendor/codex/codex-rs/Cargo.lock',lock)
env=dict(os.environ,CARGO_TARGET_DIR=str(ROOT/'build'),CARGO_PROFILE_DEV_DEBUG='0')
cargo=shutil.which('cargo') or str(Path.home()/'.cargo/bin/cargo')
subprocess.run([cargo,'build','--manifest-path',str(ROOT/'native/Cargo.toml'),'--locked','-j','4'],check=True,env=env)
print(ROOT/'build/debug/guardian-review')
