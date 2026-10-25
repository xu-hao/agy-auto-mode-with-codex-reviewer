#!/usr/bin/env python3
"""Build, configure and register Auto mode for agy in one command."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
import urllib.request

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))
from guardian_bridge import bridge

PROJECT = 'xu-hao/agy-auto-mode-with-codex-reviewer'
COPY_FILES = ('bridge.py', 'install.sh', 'uninstall.sh', 'LICENSE', 'UPSTREAM_NOTICE',
              'README.md', 'upstream.lock.json', 'rust-toolchain.toml')
COPY_DIRS = ('guardian_bridge', 'native', 'scripts', 'examples', 'docs')

class SetupError(Exception):
    pass

def ensure_account_tools():
    missing = [name for name in ('codex', 'agy') if not shutil.which(name)]
    if missing:
        raise SetupError('Missing CLI: '+', '.join(missing)+'. Install codex and agy and sign in with active subscriptions before installing Auto mode.')

def say(message):
    print(f'[agy-auto-mode] {message}', flush=True)

def command(args, **kwargs):
    subprocess.run([str(arg) for arg in args], check=True, **kwargs)

def private_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix=f'.{path.name}.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, indent=2)
            stream.write('\n')
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)

def state_path(runtime):
    return runtime / '.local/install-state.json'

def read_state(runtime):
    path = state_path(runtime)
    if not path.exists():
        return {}
    state = bridge.strict_json(bridge.trusted_file(path, bridge.MAX_INPUT))
    if state.get('project') != PROJECT:
        raise SetupError('The installation directory belongs to another project.')
    return state

def prepare_runtime(source, runtime):
    if source == runtime:
        return
    if runtime.exists() and any(runtime.iterdir()) and not state_path(runtime).exists():
        raise SetupError(f'{runtime} already contains files. Run its install.sh, or choose an empty --install-dir.')
    if state_path(runtime).exists():
        read_state(runtime)
    runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name in COPY_FILES:
        shutil.copy2(source / name, runtime / name)
    for name in COPY_DIRS:
        shutil.copytree(source / name, runtime / name, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'target', '.local', 'build'))
    private_json(state_path(runtime), {'project': PROJECT, **read_state(runtime)})

def fingerprint(runtime):
    paths = [runtime/'upstream.lock.json', runtime/'rust-toolchain.toml', runtime/'scripts/build.py']
    paths.extend(sorted(path for path in (runtime/'native/src').rglob('*') if path.is_file()))
    paths.extend([runtime/'native/Cargo.toml', runtime/'native/Cargo.lock'])
    result = hashlib.sha256()
    for path in paths:
        result.update(str(path.relative_to(runtime)).encode())
        result.update(b'\0')
        result.update(path.read_bytes())
    return result.hexdigest()

def ensure_build_environment(runtime):
    # Honor existing local OpenSSL/build configuration before installing packages.
    openssl = subprocess.run(['pkg-config', '--exists', 'openssl'], check=False).returncode == 0 if shutil.which('pkg-config') else False
    for variable in ('OPENSSL_DIR', 'OPENSSL_INCLUDE_DIR'):
        if os.environ.get(variable):
            path = Path(os.environ[variable])
            openssl |= (path/'openssl/ssl.h').is_file() or (path/'include/openssl/ssl.h').is_file()
    missing = not all(shutil.which(tool) for tool in ('cc', 'c++', 'pkg-config', 'git')) or not openssl
    if missing:
        if not sys.platform.startswith('linux') or not shutil.which('apt-get'):
            raise SetupError('Install a C/C++ compiler, Git, pkg-config and OpenSSL development headers, then rerun install.sh.')
        privilege = [] if os.geteuid() == 0 else [shutil.which('sudo') or 'sudo']
        say('Installing missing build prerequisites with apt-get (sudo may ask for your password).')
        command([*privilege, 'apt-get', 'update'])
        command([*privilege, 'apt-get', 'install', '-y', '--no-install-recommends',
                 'build-essential', 'git', 'pkg-config', 'libssl-dev'])
    cargo_home = Path(os.environ.get('CARGO_HOME', str(Path.home()/'.cargo'))).expanduser()
    os.environ['PATH'] = str(cargo_home/'bin') + os.pathsep + os.environ.get('PATH', '')
    rustup = shutil.which('rustup')
    if not rustup:
        say('Installing Rust through the official rustup installer.')
        with tempfile.TemporaryDirectory(prefix='agy-rustup-') as temporary:
            script = Path(temporary)/'rustup.sh'
            request = urllib.request.Request('https://sh.rustup.rs', headers={'User-Agent': 'agy-auto-mode-installer'})
            with urllib.request.urlopen(request, timeout=60) as response:
                script.write_bytes(response.read())
            command(['sh', script, '-y', '--no-modify-path', '--profile', 'minimal', '--default-toolchain', 'none'])
        rustup = shutil.which('rustup')
    if not rustup:
        raise SetupError('Rustup was installed but could not be found on PATH.')
    toolchain = tomllib.loads((runtime/'rust-toolchain.toml').read_text())['toolchain']['channel']
    say(f'Ensuring Rust {toolchain} is installed.')
    command([rustup, 'toolchain', 'install', toolchain, '--profile', 'minimal'])

def build_runtime(runtime):
    ensure_build_environment(runtime)
    say('Building the reviewer. The first build can take several minutes.')
    command([sys.executable, runtime/'scripts/build.py'], cwd=runtime)

def probe_runtime(runtime, config):
    say('Checking Codex reviewer access without executing a proposed command.')
    result = subprocess.run([sys.executable, str(runtime/'bridge.py'), '--config', str(config), 'doctor', '--live'],
                            capture_output=True, text=True, timeout=130, check=False)
    try:
        response = bridge.strict_json(result.stdout)
    except (ValueError, bridge.BridgeError):
        response = {}
    if not isinstance(response, dict):
        response = {}
    if result.returncode != 0 or response.get('live_inference_validated') is not True:
        detail = response.get('error') or response.get('reason') or result.stderr.strip() or 'No valid reviewer assessment was received.'
        raise SetupError(f'Codex access check failed: {detail}\nUse codex login or configure provider credentials, then rerun install.sh.')
    say(f'Reviewer available: {response.get("backend", {}).get("model", "configured model")}')

def existing_config(workspace):
    path = workspace/'.agents/hooks.json'
    if not path.exists():
        return None
    hooks = bridge.strict_json(path.read_bytes())
    if not isinstance(hooks, dict):
        raise SetupError('hooks.json must be an object.')
    definition = hooks.get(bridge.HOOK_NAME)
    if definition is None:
        return None
    import shlex
    configs = set()
    try:
        for group in definition.get('PreToolUse', []):
            for handler in group.get('hooks', []):
                args = shlex.split(handler.get('command', ''))
                if len(args) == 5 and Path(args[1]).name == 'bridge.py' and args[2] == '--config' and args[4] == 'hook':
                    configs.add(args[3])
                else:
                    raise ValueError('custom command')
    except (AttributeError, TypeError, ValueError):
        raise SetupError('The existing Guardian hook has a custom command. Pass --config explicitly to replace it.')
    if len(configs) != 1:
        raise SetupError('The existing Guardian hook has ambiguous configuration. Pass --config explicitly.')
    return Path(configs.pop())

def install(workspace, runtime, config_path=None, model=None):
    workspace = Path(workspace).expanduser().resolve(strict=True)
    runtime = Path(runtime).expanduser().resolve()
    if not workspace.is_dir():
        raise SetupError('WORKSPACE must be a directory.')
    if runtime.is_relative_to(workspace):
        raise SetupError('The installed runtime must be outside the agent workspace. Choose another --install-dir.')
    ensure_account_tools()
    if config_path is None:
        config_path = existing_config(workspace)
    config_root = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home()/'.config'))).expanduser()/'antigravity-guardian'
    workspace_id = hashlib.sha256(str(workspace).encode()).hexdigest()[:16]
    if config_path is None and not config_root.exists():
        config_root.mkdir(parents=True, mode=0o700)
    config_path = Path(config_path).expanduser().absolute() if config_path else config_root/'workspaces'/f'{workspace_id}.json'
    if config_path.resolve().is_relative_to(workspace):
        raise SetupError('The operator config must be outside the agent workspace. Choose another --config path.')
    if config_path.is_symlink():
        raise SetupError('Refusing a symlinked operator config.')
    if config_path.exists():
        config = {key:value for key,value in bridge.config_load(config_path).items() if not key.startswith('_')}
    else:
        config = {
            'app_data_roots': ['~/.gemini/antigravity', '~/.gemini/antigravity-cli', '~/.gemini/antigravity-ide'],
            'workspace_roots': [],
            'permissions': {
                'source': 'installer; Antigravity remains authoritative for execution permissions',
                'filesystem': 'unknown; controlled by Antigravity',
                'network': 'unknown; controlled by Antigravity',
                'note': 'Registering this workspace grants no execution permissions and changes no Antigravity rules.',
            },
            'native': {'timeout_ms': 90000},
        }
    if str(workspace) not in config['workspace_roots']:
        config['workspace_roots'].append(str(workspace))
    if model:
        config.setdefault('native', {})['model'] = model
    prepare_runtime(SOURCE, runtime)
    build_fingerprint = fingerprint(runtime)
    binary = runtime/'build/debug/guardian-review'
    state = read_state(runtime)
    if not binary.is_file() or state.get('build_fingerprint') != build_fingerprint:
        build_runtime(runtime)
        private_json(state_path(runtime), {'project': PROJECT, 'build_fingerprint': build_fingerprint})
    else:
        say('Reusing the existing reviewer build.')
    config['binary'] = str(binary)
    # Verify a temporary config first; a failed probe preserves existing setup.
    config_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=f'.{config_path.name}.install-', dir=config_path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(config, stream, indent=2)
            stream.write('\n')
        probe_runtime(runtime, Path(temporary))
        os.replace(temporary, config_path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    registration = subprocess.run([sys.executable, str(runtime/'bridge.py'), '--config', str(config_path),
        'install', '--workspace', str(workspace)], capture_output=True, text=True, check=False)
    if registration.returncode != 0:
        raise SetupError('Hook registration failed: '+(registration.stderr.strip() or registration.stdout.strip()))
    say(f'Installed for {workspace}')
    say(f'Configuration: {config_path}')
    say(f'Next: cd {shlex_quote(str(workspace))} && agy')
    say('In agy, use /hooks to confirm codex-guardian-review is loaded.')
    say(f'Uninstall: {shlex_quote(str(runtime/"uninstall.sh"))} {shlex_quote(str(workspace))}')
    return {'workspace': str(workspace), 'runtime': str(runtime), 'config': str(config_path)}

def shlex_quote(value):
    import shlex
    return shlex.quote(value)

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, epilog='Requires active Codex and Antigravity subscriptions, both CLIs installed and signed in, and reviewer-model access.')
    parser.add_argument('workspace', nargs='?', default=os.getcwd(), help='workspace directory; defaults to the current directory')
    parser.add_argument('--install-dir', default=str(Path(os.environ.get('XDG_DATA_HOME', str(Path.home()/'.local/share')))/'antigravity-guardian'))
    parser.add_argument('--config', help='optional existing operator config to preserve and extend')
    parser.add_argument('--model', help='explicit reviewer model override')
    args = parser.parse_args(argv)
    try:
        install(args.workspace, args.install_dir, args.config, args.model)
    except (SetupError, OSError, ValueError, bridge.BridgeError, subprocess.SubprocessError) as error:
        print(f'[agy-auto-mode] Installation failed: {error}', file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
