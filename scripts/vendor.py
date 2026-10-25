#!/usr/bin/env python3
"""Vendor a verifiable source snapshot; never patch the borrowed reviewer."""
from pathlib import Path
import hashlib
import json
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PIN = json.loads((ROOT / 'upstream.lock.json').read_text())
source = ROOT / 'upstream/codex'
dest = ROOT / 'vendor/codex'
if not source.exists():
    subprocess.run(['git','clone','--no-checkout','--filter=blob:none',PIN['repository'],str(source)],check=True)
if not subprocess.run(['git','-C',str(source),'cat-file','-e',PIN['commit']],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode == 0:
    subprocess.run(['git','-C',str(source),'fetch','--depth=1','origin',PIN['commit']],check=True)
dest.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryFile() as archive:
    subprocess.run(['git','-C',str(source),'archive',PIN['commit']],stdout=archive,check=True)
    archive.seek(0)
    with tarfile.open(fileobj=archive) as tar:
        tar.extractall(dest,filter='data')
checksums = {}
for base in ['codex-rs/ext/guardian-reviewer','codex-rs/guardian-context','codex-rs/prompts','codex-rs/core/src/guardian']:
    for path in sorted((dest/base).rglob('*')):
        if path.is_file():
            checksums[str(path.relative_to(dest))] = hashlib.sha256(path.read_bytes()).hexdigest()
(ROOT/'vendor/guardian.sha256.json').write_text(json.dumps(checksums,indent=2)+'\n')
print(f'Vendored unmodified {PIN["repository"]} @ {PIN["commit"]}')
