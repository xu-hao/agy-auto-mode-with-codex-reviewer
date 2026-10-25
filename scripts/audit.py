#!/usr/bin/env python3
"""View local Guardian approvals, rejections and review failures. No model access needed."""
from __future__ import annotations
import argparse
from collections import deque
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from guardian_bridge import audit, bridge
from scripts.setup import existing_config


def matches(record, choice):
    if choice == 'approved':
        return record.get('decision') == 'approve' and record.get('status') == 'reviewed'
    if choice == 'rejected':
        return record.get('decision') == 'block' and record.get('status') == 'reviewed'
    if choice == 'errors':
        return record.get('status') == 'error'
    return True

def safe_text(value):
    return json.dumps(str(value), ensure_ascii=True)[1:-1]

def show(record, as_json=False):
    if as_json:
        print(json.dumps(record, ensure_ascii=True, separators=(',', ':')), flush=True)
        return
    status = 'ERROR' if record.get('status') == 'error' else 'APPROVED' if record.get('decision') == 'approve' else 'REJECTED'
    timestamp = record.get('timestamp')
    if not timestamp and isinstance(record.get('time_ns'), int):
        timestamp = datetime.fromtimestamp(record['time_ns']/1e9, timezone.utc).isoformat(timespec='seconds')
    subject = record.get('command') or record.get('terminal_input') or record.get('target') or '<details not recorded>'
    print(f'{safe_text(timestamp or "unknown time")}  {status}  {safe_text(record.get("tool") or "unknown tool")}')
    print(f'  {safe_text(subject)}')
    if record.get('cwd'):
        print(f'  cwd: {safe_text(record["cwd"])}')
    if record.get('reason'):
        print(f'  reason: {safe_text(record["reason"])}')
    print(flush=True)

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('workspace', nargs='?', default=os.getcwd())
    parser.add_argument('--config', help='explicit operator config, including after a custom installation was removed')
    parser.add_argument('--decision', choices=('all','approved','rejected','errors'), default='all')
    parser.add_argument('--last', type=int, default=20, help='number of matching records (default: 20)')
    parser.add_argument('--follow', action='store_true', help='watch for new decisions')
    parser.add_argument('--json', action='store_true', help='emit JSONL records')
    args = parser.parse_args(argv)
    if args.last < 1:
        parser.error('--last must be positive')
    try:
        workspace = Path(args.workspace).expanduser().resolve()
        config_path = Path(args.config).expanduser() if args.config else existing_config(workspace)
        if config_path is None:
            root = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home()/'.config'))).expanduser()/'antigravity-guardian/workspaces'
            config_path = root/(hashlib.sha256(str(workspace).encode()).hexdigest()[:16]+'.json')
        if not config_path.exists():
            raise audit.AuditError('No workspace config found. Run install.sh for this workspace, or pass --config.')
        config = bridge.config_load(config_path)
        path = audit.log_path(config)
        if path is None:
            raise audit.AuditError('Auditing is disabled. Rerun install.sh or set audit_path in the operator config.')
        recent = deque(maxlen=args.last)
        offset, identity = audit.read_log(path, lambda record: recent.append(record) if matches(record,args.decision) else None)
        for record in recent:
            show(record,args.json)
        if not recent and not args.json:
            print('No matching review decisions recorded yet.', flush=True)
        if args.follow:
            if not args.json:
                print(f'Watching {path} (Ctrl-C to stop).', flush=True)
            while True:
                time.sleep(.5)
                offset, identity = audit.read_log(path, lambda record: show(record,args.json) if matches(record,args.decision) else None, offset, identity)
    except KeyboardInterrupt:
        return 0
    except BrokenPipeError:
        return 0
    except Exception as error:
        print(f'Guardian audit: {error}', file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
