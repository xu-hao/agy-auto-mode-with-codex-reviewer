"""Trusted host input, freshness binding, and Antigravity PreToolUse enforcement.

No proposed command is executed here. The sole subprocess is the fixed native
Guardian binary selected by the operator's configuration.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import stat
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
MAX_INPUT = 8 * 1024 * 1024
MAX_TRANSCRIPT = 32 * 1024 * 1024
FAILURE = ('Guardian review could not be completed. This is a review failure, '
           'not a determination of unsafe behavior. Resolve the error before retrying; '
           'do not bypass the review gate.')
DENIAL = ('Do not pursue the same outcome through a workaround or indirect execution. '
          'Continue only with a materially safer action, or ask the user for guidance.')

class BridgeError(Exception):
    pass

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()

def digest(value):
    return hashlib.sha256(value).hexdigest()

def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise BridgeError(f'duplicate JSON field: {key}')
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(BridgeError('non-finite JSON')))

def read_input():
    data = sys.stdin.buffer.read(MAX_INPUT + 1)
    if len(data) > MAX_INPUT:
        raise BridgeError('request exceeds byte limit')
    result = strict_json(data)
    if not isinstance(result, dict):
        raise BridgeError('request must be an object')
    return result

def text(value, label):
    if not isinstance(value, str) or not value or '\0' in value:
        raise BridgeError(f'invalid {label}')
    return value

def trusted_file(path, limit):
    """Open without following the final symlink; never accept writable shared logs."""
    path = Path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
            raise BridgeError('host file must be a regular, user-owned file without group/other write access')
        data = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
        if len(data) > limit:
            raise BridgeError('host file exceeds byte limit')
        if (info.st_ino, info.st_size, info.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
            raise BridgeError('host file changed during read')
    return data

def config_load(path):
    path = Path(path).absolute()
    config = strict_json(trusted_file(path, MAX_INPUT))
    if not isinstance(config, dict):
        raise BridgeError('config must be an object')
    for field in ('app_data_roots', 'workspace_roots', 'permissions'):
        if field not in config:
            raise BridgeError(f'missing operator config: {field}')
    if not isinstance(config['permissions'],dict) or not all(isinstance(config[k],list) and all(isinstance(p,str) for p in config[k]) for k in ('app_data_roots','workspace_roots')):
        raise BridgeError('invalid operator policy or roots')
    config['_path'] = str(path)
    config['_digest'] = digest(canonical({k:v for k,v in config.items() if not k.startswith('_')}))
    return config

def transcript_load(config, session_id, supplied_path):
    # Accept only the canonical host log for this exact conversation, never a
    # transcript path supplied by tool arguments or a workspace-created file.
    try:
        if str(uuid.UUID(session_id)) != session_id.lower():
            raise ValueError()
    except (ValueError, AttributeError):
        raise BridgeError('conversationId must be a UUID')
    supplied = Path(supplied_path).expanduser().absolute()
    expected = [Path(p).expanduser().absolute() / 'brain' / session_id / '.system_generated/logs' / filename
                for p in config['app_data_roots'] for filename in ('transcript.jsonl','transcript_full.jsonl')]
    if supplied not in expected:
        raise BridgeError('transcript path does not match the configured host and conversation')
    # All components from the trusted app-data root down must be non-symlink,
    # user-owned and protected against other local users.
    root = next(p.parents[4] for p in expected if p == supplied)
    current = root
    for component in [None, *supplied.relative_to(root).parts[:-1]]:
        if component is not None:
            current /= component
        info = current.lstat()
        if stat.S_ISLNK(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
            raise BridgeError('untrusted transcript directory')
    raw = trusted_file(supplied, MAX_TRANSCRIPT)
    if raw and not raw.endswith(b'\n'):
        raise BridgeError('incomplete transcript record')
    transcript_digest = digest(raw)
    history, original = [], None
    for line_number, line in enumerate(raw.splitlines(), 1):
        record = strict_json(line)
        if not isinstance(record, dict):
            raise BridgeError('invalid transcript record')
        source, kind = record.get('source'), record.get('type')
        # Only this exact host-generated pair can establish authorization.
        # MODEL text saying "the user approved" remains assistant evidence.
        if kind == 'USER_INPUT' and source == 'USER_EXPLICIT' and record.get('status') == 'DONE':
            content = text(record.get('content'), 'user transcript content')
            if record.get('truncated_fields'):
                raise BridgeError('authorization evidence is truncated')
            original = content if original is None else original
            role = 'user'
        elif source == 'MODEL':
            role = 'assistant' if kind == 'PLANNER_RESPONSE' else 'tool'
            # Keep content and proposed calls verbatim inside JSON, with host
            # attribution. Do not relabel nested userMessage fields as users.
            content = json.dumps({k:record[k] for k in ('content','tool_calls','truncated_fields','status') if k in record},ensure_ascii=False)
        else:
            role = 'tool'
            content = json.dumps(record,ensure_ascii=False)
        history.append({'role':role, 'content':content, 'provenance':{
            'origin':'antigravity-host-transcript', 'source':source, 'type':kind,
            'line':line_number, 'step_index':record.get('step_index'),
            'created_at':record.get('created_at'), 'transcript_sha256':transcript_digest}})
    if original is None:
        raise BridgeError('no explicit user authorization source in host transcript')
    return history, original, transcript_digest

def normalize(payload, config, hook):
    if hook:
        session = text(payload.get('conversationId'), 'conversationId')
        transcript = text(payload.get('transcriptPath'), 'transcriptPath')
        tool = payload.get('toolCall')
        if not isinstance(tool, dict) or not isinstance(tool.get('args'), dict):
            raise BridgeError('invalid toolCall')
        action = {'tool':text(tool.get('name'), 'tool name'), 'arguments':tool['args']}
        cwd = tool['args'].get('Cwd')
        cwd_source = 'explicit tool Cwd' if cwd is not None else 'inferred single workspace; actual cwd not provided by hook'
        if cwd is None:
            workspaces = payload.get('workspacePaths', [])
            cwd = workspaces[0] if len(workspaces) == 1 else None
        request_id = str(uuid.uuid4())
        environment = {'shell':'bash', 'platform':sys.platform, 'step_index':payload.get('stepIdx'),
                       'antigravity_model':payload.get('modelName'),
                       'workspace_paths':payload.get('workspacePaths', []),
                       'declared_by':'antigravity-hook-host', 'cwd_source':cwd_source}
        evidence = {}
    else:
        session = text(payload.get('session_id'), 'session_id')
        transcript = text(payload.get('transcript_path'), 'transcript_path')
        request_id = text(payload.get('request_id'), 'request_id')
        action = payload.get('action')
        if not isinstance(action, dict) or not isinstance(action.get('arguments'), dict):
            raise BridgeError('action must contain tool and arguments')
        text(action.get('tool'), 'tool name')
        cwd = payload.get('cwd')
        environment = payload.get('environment', {})
        # Caller evidence is useful but does not establish authorization.
        evidence = payload.get('evidence', {})
        for field in ('history','original_user_request'):
            if field in payload:
                evidence = {'caller_evidence':evidence, 'untrusted_'+field:payload[field]}
    cwd = text(cwd, 'cwd')
    if not Path(cwd).is_absolute():
        raise BridgeError('cwd must be absolute')
    if not any(Path(cwd).resolve().is_relative_to(Path(p).expanduser().resolve()) for p in config['workspace_roots']):
        raise BridgeError('execution cwd is outside configured workspaces')
    # Command text is never split, rewritten, expanded, or submitted to a shell.
    if action['tool'] == 'run_command':
        text(action['arguments'].get('CommandLine'), 'CommandLine')
        if 'Cwd' in action['arguments'] and action['arguments']['Cwd'] != cwd:
            raise BridgeError('command cwd disagrees with request cwd')
    history, original, transcript_digest = transcript_load(config, session, transcript)
    request = {'request_id':request_id, 'session_id':session, 'action':action,'cwd':cwd,
               'environment':environment,'original_user_request':original,'history':history,
               'permissions':config['permissions'],'evidence':evidence}
    request['binding'] = digest(canonical({'request':request,'config_sha256':config['_digest'], 'transcript_sha256':transcript_digest}))
    return request, transcript, transcript_digest

def native_call(config, mode, request=None):
    binary = Path(config.get('binary', ROOT/'build/debug/guardian-review')).expanduser().absolute()
    if not binary.is_file():
        raise BridgeError('native Guardian binary missing; run python3 scripts/build.py')
    native_config = config.get('native', {})
    timeout_ms = native_config.get('timeout_ms',90_000)
    if not isinstance(timeout_ms,int) or not 1 <= timeout_ms <= 120_000:
        raise BridgeError('native timeout_ms must be in 1..120000')
    data = canonical({'config':native_config,'mode':mode,'request':request}) + b'\n'
    # The executable path is operator-controlled. Proposed action data is stdin,
    # never a subprocess argument or environment variable. No shell is involved.
    try:
        result = subprocess.run([str(binary)],input=data,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                timeout=timeout_ms/1000+5,check=False)
    except subprocess.TimeoutExpired:
        raise BridgeError('native reviewer timed out')
    if result.returncode != 0 or len(result.stdout) > MAX_INPUT:
        raise BridgeError('native reviewer exited abnormally')
    response = strict_json(result.stdout)
    if not isinstance(response,dict):
        raise BridgeError('invalid native reviewer response')
    return response

def review(payload, config, hook=False, mode='review'):
    request, transcript, initial_digest = normalize(payload,config,hook)
    response = native_call(config, mode, request)
    if mode == 'prepare':
        return response
    # Approval is consumed inline for this exact action, with no reusable token
    # or allow cache. A transcript/config change invalidates it.
    _, _, current_digest = transcript_load(config,request['session_id'],transcript)
    current_config = config_load(config['_path'])
    if current_digest != initial_digest or current_config['_digest'] != config['_digest']:
        raise BridgeError('authorization or operator policy changed during review')
    if response.get('status')=='error' and response.get('request_id') is None:
        raise BridgeError('native review initialization failed: '+str(response.get('error','unknown error')))
    if response.get('request_id') != request['request_id'] or response.get('binding') != request['binding']:
        raise BridgeError('review response is not bound to this exact request')
    assessment = response.get('assessment',{})
    if response.get('decision') == 'approve':
        if response.get('status') != 'reviewed' or assessment.get('outcome') != 'allow' or response.get('executed') is not False:
            raise BridgeError('inconsistent approval result')
    if config.get('audit_path'):
        audit = {k:response.get(k) for k in ('request_id','binding','status','decision','backend','server_model','attempts')}
        audit['time_ns'] = time.time_ns()
        audit['assessment'] = {k:assessment.get(k) for k in ('outcome','risk_level','user_authorization')}
        fd = os.open(Path(config['audit_path']).expanduser(), os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd,'ab') as log:
            info=os.fstat(log.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode & 0o022:
                raise BridgeError('untrusted audit file')
            log.write(canonical(audit)+b'\n')
    if hook:
        approved = response.get('decision') == 'approve' 
        reason = assessment.get('rationale', FAILURE)
        if not approved and response.get('status') == 'reviewed':
            reason += ' ' + DENIAL
        elif not approved:
            reason = FAILURE
        return {'decision':'auto_approve' if approved else 'deny', 'reason':reason}
    return response

def install(config_path, workspace):
    config = config_load(config_path)
    workspace = Path(workspace).expanduser().resolve()
    if str(workspace) not in [str(Path(p).expanduser().resolve()) for p in config['workspace_roots']]:
        raise BridgeError('workspace must be present in operator config')
    path = workspace/'.agents/hooks.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    hooks = strict_json(path.read_bytes()) if path.exists() else {}
    command = shlex.join([sys.executable,str(ROOT/'bridge.py'),'--config',str(Path(config_path).absolute()),'hook'])
    hooks['codex-guardian-review'] = {'PreToolUse':[{'matcher':'*','hooks':[{'type':'command','command':command,'timeout':130}]}]}
    path.write_text(json.dumps(hooks,indent=2)+'\n')
    return {'installed':str(path),'command':command}

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True,help='trusted operator-owned JSON config')
    sub = parser.add_subparsers(dest='mode',required=True)
    for name in ('hook','review','prepare'):
        sub.add_parser(name)
    doctor = sub.add_parser('doctor')
    doctor.add_argument('--live',action='store_true',help='run a review-only inference connectivity probe')
    command = sub.add_parser('install')
    command.add_argument('--workspace',required=True)
    args = parser.parse_args(argv)
    try:
        if args.mode == 'install':
            result = install(args.config,args.workspace)
        else:
            config = config_load(args.config)
            if args.mode == 'doctor':
                result = native_call(config,'doctor')
                if args.live:
                    request = {'request_id':str(uuid.uuid4()),'session_id':str(uuid.uuid4()),
                        'action':{'tool':'run_command','arguments':{'CommandLine':'printf guardian-connectivity-probe','Cwd':str(ROOT)}},
                        'cwd':str(ROOT),'environment':{'purpose':'review-only connectivity probe'},
                        'original_user_request':'Check reviewer model connectivity without executing any proposed action.',
                        'history':[{'role':'user','content':'Check reviewer model connectivity without executing any action.',
                                    'provenance':{'origin':'operator-invoked doctor --live'}}],
                        'permissions':config['permissions'],'evidence':{},'binding':str(uuid.uuid4())}
                    result=native_call(config,'review',request)
                    result['live_inference_validated']=result.get('status')=='reviewed'
            else:
                result=review(read_input(),config,args.mode=='hook',args.mode if args.mode!='hook' else 'review')
    except Exception as error:
        # A hook error must still print a hard-deny JSON and exit successfully;
        # some hosts ignore a failed command's stdout or fail open on exit != 0.
        sys.stderr.write(f'Guardian bridge: {type(error).__name__}: {error}\n')
        reason = FAILURE + f' ({type(error).__name__}: {str(error)[:300]})'
        result = {'decision':'deny','reason':reason} if args.mode=='hook' else {'decision':'block','status':'error','executed':False,'reason':reason}
    print(json.dumps(result,ensure_ascii=False))
    return 0 if args.mode=='hook' or result.get('status')!='error' else 1
