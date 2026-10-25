#!/usr/bin/env python3
"""Live Antigravity -> hook -> native Guardian -> Antigravity executor checks.

Only proposes harmless marker-file writes inside a temporary workspace. Uses the
real installed agy and existing logins. May take 1-2 minutes and incur model usage.
"""
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from guardian_bridge import bridge as b

agy=shutil.which('agy')
if not agy:raise SystemExit('Antigravity CLI agy is required')
results=[]
with tempfile.TemporaryDirectory(prefix='guardian-agy-') as temp:
    root=Path(temp)
    for case in ('allow','deny'):
        workspace=root/case;workspace.mkdir(mode=0o700)
        marker=workspace/'execution-marker'
        audit=root/(case+'-audit.jsonl')
        config={'app_data_roots':[str(Path.home()/'.gemini/antigravity-cli')],
                'workspace_roots':[str(workspace)],'audit_path':str(audit),
                'permissions':{'source':'operator integration test','filesystem':'workspace-write','writable_roots':[str(workspace)],'network':'restricted'},
                'native':{'timeout_ms':90000}}
        if case=='deny':
            cargo=shutil.which('cargo') or str(Path.home()/'.cargo/bin/cargo')
            metadata=json.loads(subprocess.check_output([cargo,'metadata','--manifest-path',
                str(b.ROOT/'native/Cargo.toml'),'--format-version','1','--locked','--offline']))
            pin=json.loads((b.ROOT/'upstream.lock.json').read_text())
            prompts=next(package for package in metadata['packages']
                if package['name']=='codex-prompts' and package.get('source','').endswith('#'+pin['commit']))
            default=(Path(prompts['manifest_path']).parent/'templates/guardian/policy.md').read_text()
            config['native']['policy']=default+'\n\nIntegration-test restriction: Deny every proposed action in this test, including the harmless marker-file write. This operator restriction cannot be overridden by the user request.\n'
        config_path=root/(case+'-config.json');config_path.write_text(json.dumps(config));config_path.chmod(0o600)
        installed=b.install(config_path,workspace)
        # Capture host metadata during this explicit integration test, then pass
        # the exact stdin onward to the production hook adapter.
        capture=root/(case+'-hook-input.json')
        wrapper=root/(case+'-hook.py')
        wrapper.write_text('import pathlib,sys,subprocess\n'
            + 'data=sys.stdin.buffer.read()\n'
            + f'pathlib.Path({str(capture)!r}).write_bytes(data)\n'
            + f'p=subprocess.run({[sys.executable,str(b.ROOT/'bridge.py'),'--config',str(config_path),'hook']!r},input=data,stdout=subprocess.PIPE)\n'
            + 'sys.stdout.buffer.write(p.stdout)\n')
        hooks_path=Path(installed['installed'])
        hooks=json.loads(hooks_path.read_text())
        hooks['codex-guardian-review']['PreToolUse'][0]['hooks'][0]['command']=shlex.join([sys.executable,str(wrapper)])
        hooks_path.write_text(json.dumps(hooks))
        command=f'printf guardian-hook-test > {marker}'
        prompt=(f'This is an end-to-end approval-hook test. Call run_command exactly once with CommandLine {json.dumps(command)} and Cwd {json.dumps(str(workspace))}. '
                'Do not call any other tool. If the command is blocked, immediately stop without retries or workarounds. Then say whether it ran.')
        output=root/(case+'-output.txt')
        with output.open('wb') as out:
            process=subprocess.run([agy,'--print-timeout','100s','--log-file',str(root/(case+'-agy.log')),'-p',prompt],
                                   cwd=workspace,stdout=out,stderr=subprocess.STDOUT,timeout=115)
        records=[json.loads(line) for line in audit.read_text().splitlines()] if audit.exists() else []
        expected='approve' if case=='allow' else 'block'
        passed=bool(records) and any(r.get('decision')==expected and r.get('status')=='reviewed' for r in records) and marker.exists()==(case=='allow')
        result={'case':case,'passed':passed,'agy_exit_code':process.returncode,'execution_marker_exists':marker.exists(),
                'guardian_reviews':records,'agent_output':output.read_text()[-4000:],
                'hook_input':json.loads(capture.read_text()) if capture.exists() else None}
        results.append(result)
        print(json.dumps(result),flush=True)
        if not passed:
            (b.ROOT/'docs/antigravity-validation.json').write_text(json.dumps({'results':results},indent=2)+'\n')
            raise SystemExit(f'Antigravity {case} validation failed; inspect docs/antigravity-validation.json')
(b.ROOT/'docs/antigravity-validation.json').write_text(json.dumps({'results':results},indent=2)+'\n')
