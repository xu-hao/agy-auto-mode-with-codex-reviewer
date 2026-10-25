"""Private, append-only review decision records. Never executes logged actions."""
from __future__ import annotations
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import time
import uuid

class AuditError(RuntimeError):
    pass

def encoded(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()

def log_path(config):
    value = config.get('audit_path')
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise AuditError('audit_path must be absolute')
    return path

def validate_file(fd):
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise AuditError('audit log must be a private, user-owned regular file (chmod 600)')
    return info

def append(config, record):
    path = log_path(config)
    if path is None:
        return
    flags = os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, 'ab', buffering=0) as stream:
        validate_file(stream.fileno())
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        size = os.fstat(stream.fileno()).st_size
        if size and os.pread(stream.fileno(), 1, size-1) != b'\n':
            raise AuditError('audit log has an incomplete final record; repair or archive it before retrying')
        remaining = memoryview(encoded(record)+b'\n')
        while remaining:
            written = stream.write(remaining)
            if not written:
                raise AuditError('audit write did not complete')
            remaining = remaining[written:]


def base(request, details):
    request = request or {}
    action = request.get('action') or {}
    args = action.get('arguments') or {}
    if not isinstance(args, dict):
        args = {}
    environment = request.get('environment') or {}
    record = {
        'schema_version': 1,
        'timestamp': datetime.now(timezone.utc).isoformat(timespec='milliseconds'),
        'time_ns': time.time_ns(),
        'request_id': request.get('request_id') or str(uuid.uuid4()),
        'binding': request.get('binding'),
        'session_id': request.get('session_id'),
        'step_index': environment.get('step_index') if isinstance(environment, dict) else None,
        'cwd': request.get('cwd'),
        'tool': action.get('tool'),
        'action_sha256': hashlib.sha256(encoded(action)).hexdigest(),
        'execution_status': 'not_observed',
    }
    if details:
        for key in ('CommandLine', 'cmd', 'command'):
            if isinstance(args.get(key), str):
                record['command'] = args[key]
                break
        if action.get('tool') == 'manage_task' and args.get('Action') == 'send_input':
            record['terminal_input'] = args.get('Input')
        for key in ('TargetFile', 'AbsolutePath', 'DirectoryPath', 'SearchPath', 'Url', 'TaskId'):
            if isinstance(args.get(key), str):
                record['target'] = args[key]
                break
    return record

def decision(config, request, response):
    if not config.get('audit_path'):
        return
    details = config.get('audit_details') is True
    record = base(request, details)
    record.update({key:response.get(key) for key in ('status','decision','backend','server_model','attempts')})
    assessment = response.get('assessment') or {}
    record['assessment'] = {key:assessment.get(key) for key in ('outcome','risk_level','user_authorization')}
    if details:
        record['reason'] = assessment.get('rationale') or response.get('error') or 'Review did not return an assessment.'
        if response.get('error'):
            record['error'] = response['error']
    append(config, record)

def failure(config, request, payload, hook, error):
    if not config.get('audit_path'):
        return
    if request is None:
        payload = payload if isinstance(payload, dict) else {}
        tool = payload.get('toolCall') if hook else payload.get('action')
        tool = tool if isinstance(tool, dict) else {}
        args = tool.get('args' if hook else 'arguments') or {}
        args = args if isinstance(args, dict) else {}
        request = {
            'request_id': payload.get('request_id'),
            'session_id': payload.get('conversationId' if hook else 'session_id'),
            'action': {'tool':tool.get('name' if hook else 'tool'), 'arguments':args},
            'cwd': args.get('Cwd') or payload.get('cwd'),
            'environment': {'step_index':payload.get('stepIdx')},
        }
    details = config.get('audit_details') is True
    record = base(request, details)
    record.update(status='error', decision='block', error_type=type(error).__name__)
    if details:
        record['reason'] = str(error)
    append(config, record)

def read_log(path, callback, offset=0, identity=None):
    """Read complete JSONL records; retain an incomplete tail for a later follow pass."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return 0, None
    with os.fdopen(fd, 'rb') as stream:
        info = validate_file(stream.fileno())
        current = (info.st_dev, info.st_ino)
        if identity != current or info.st_size < offset:
            offset = 0
        stream.seek(offset)
        while True:
            start = stream.tell()
            line = stream.readline(64*1024*1024+1)
            if not line:
                return stream.tell(), current
            if len(line) > 64*1024*1024:
                raise AuditError('audit record exceeds the reader limit')
            if not line.endswith(b'\n'):
                return start, current
            record = json.loads(line)
            if not isinstance(record, dict):
                raise AuditError('audit record must be an object')
            callback(record)
