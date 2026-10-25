#!/usr/bin/env python3
"""Build the adapter with Codex crates pinned directly to the upstream commit."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tomllib

ROOT = Path(__file__).resolve().parents[1]
pin = json.loads((ROOT/'upstream.lock.json').read_text())
manifest = tomllib.loads((ROOT/'native/Cargo.toml').read_text())
for name, spec in manifest['dependencies'].items():
    if name.startswith('codex-') and (
        not isinstance(spec,dict)
        or spec.get('git') != pin['repository']
        or spec.get('rev') != pin['commit']
        or 'path' in spec
    ):
        raise SystemExit(f'{name} must use the pinned upstream Codex Git dependency')

env = dict(os.environ,CARGO_TARGET_DIR=str(ROOT/'build'),CARGO_PROFILE_DEV_DEBUG='0')
cargo = shutil.which('cargo') or str(Path.home()/'.cargo/bin/cargo')
subprocess.run([cargo,'build','--manifest-path',str(ROOT/'native/Cargo.toml'),'--locked','-j','4'],check=True,env=env)
print(ROOT/'build/debug/guardian-review')
