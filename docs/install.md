# Install and uninstall

The scripts handle setup for one Antigravity workspace at a time. This project has been validated on Linux with Antigravity CLI 1.4.7.

## Prerequisites

- Active Codex and Google Antigravity subscriptions.
- Both `codex` and `agy` installed and signed in.
- Your Codex account must have access to the configured reviewer model. The default ChatGPT setup uses `codex-auto-review`.
- Python 3.12+; `curl` for the download-and-run command.

These are the project's supported account prerequisites. The installer checks CLI presence and actual Codex reviewer access; it does not inspect either account's billing or subscription status. Open `agy` and sign in normally; use `codex login` for Codex if needed.

On Ubuntu/Debian, the installer can install missing C/C++ build tools, Git, `pkg-config` and OpenSSL development headers through `apt-get`. It uses `sudo` when necessary. It installs Rust through the official rustup installer and selects the version pinned by this project. Other Linux distributions need those system build prerequisites installed first.

## Install

From the workspace you want to use with agy:

```bash
curl -fsSL https://raw.githubusercontent.com/xu-hao/agy-auto-mode-with-codex-reviewer/main/install.sh | bash
agy
```

You can also name the workspace explicitly:

```bash
curl -fsSL https://raw.githubusercontent.com/xu-hao/agy-auto-mode-with-codex-reviewer/main/install.sh | bash -s -- /absolute/path/to/project
cd /absolute/path/to/project
agy
```

For a local checkout:

```bash
./install.sh /absolute/path/to/project
```

The installer:

1. Places the runtime outside the workspace, by default in `~/.local/share/antigravity-guardian`.
2. Installs missing build prerequisites and builds the pinned Codex reviewer libraries on the first run. Subsequent runs reuse an unchanged build.
3. Creates a private, per-workspace config and enables command-decision logging under `~/.config/antigravity-guardian/workspaces/` without requiring manual JSON editing. The log is created on the first decision.
4. Checks the reviewer with an actual inference request that executes no proposed command.
5. Merges the named `codex-guardian-review` hook into the workspace's `.agents/hooks.json`, preserving other named hooks and Antigravity's permission rules.

A failed reviewer check does not register a new hook or replace an existing operator config. Fix the account/model error and rerun the installer. An existing installation directory without the installer's marker is left untouched; run the installer from that checkout or choose another `--install-dir`.

The generated configuration does not invent filesystem or network grants. It labels unreported permissions as unknown and leaves Antigravity authoritative for execution. An existing config's policies, provider settings and permissions are preserved. A normal existing Guardian hook's config is detected automatically on reinstall; custom hook commands require an explicit `--config` to replace them. If needed, edit the private config path printed by the installer to provide more detailed operator policy.

The default backend reads supported credentials from `CODEX_HOME` or `~/.codex`. See [model and provider configuration](configuration.md) for custom backends.

### Options

```bash
./install.sh [WORKSPACE] [--install-dir PATH] [--config PATH] [--model MODEL]
```

| Option | Behavior |
| --- | --- |
| `WORKSPACE` | Defaults to the current directory. |
| `--install-dir PATH` | Changes the runtime location; it must be outside the workspace. |
| `--config PATH` | Preserves and extends an existing operator config; it must be outside the workspace. |
| `--model MODEL` | Explicitly selects the reviewer model; access is checked before activation. |

`XDG_DATA_HOME` and `XDG_CONFIG_HOME` are honored. The installer prints the actual runtime, config and uninstall paths. It also honors existing Rust/OpenSSL build environment settings.

## Use it with agy

Start `agy` normally from the registered workspace. In the session, type `/hooks` and confirm `codex-guardian-review` is loaded, then give agy your task. The same hook applies to `agy -p "your task"` from that workspace.

The hook starts the reviewer automatically before each tool call. An allow verdict lets Antigravity proceed subject to its explicit permission rules. A denial or reviewer failure blocks that call and returns the reason. Restart/reload an existing Antigravity session after changing hooks.

The installed runtime, config and host transcripts should remain protected from agent writes. If other hooks rewrite arguments, ensure this review gate runs after those rewrites.

## View audit history

From the workspace, run `"$HOME/.local/share/antigravity-guardian/audit.sh"`. Use `--follow` to watch new decisions and `--decision rejected` to filter rejections. The installer prints the actual log/viewer paths and preserves explicitly disabled or customized audit settings. See [auditing](auditing.md) for the fields, privacy controls and distinction between approval and execution.

## Uninstall

From the registered workspace:

```bash
"$HOME/.local/share/antigravity-guardian/uninstall.sh"
```

Or from a local checkout, naming the workspace:

```bash
./uninstall.sh /absolute/path/to/project
```

Use the path printed during installation if you selected another runtime directory. Repeat for every workspace where you enabled it, then reload Antigravity and confirm the bridge is absent from `/hooks`.

Uninstall removes only the `codex-guardian-review` hook. It needs no Rust toolchain, config file, credentials or reviewer access. Other hooks, permission rules, credentials, configs, logs and installed files are preserved. Repeating it is harmless.

After unregistering every workspace, you can delete the installed runtime and generated configs if you want full local-file cleanup. If the checkout/runtime has already been deleted, remove the top-level `codex-guardian-review` entry from each workspace's `.agents/hooks.json`, preserving its other entries and valid JSON.

## Manual setup

For an explicitly managed deployment, the underlying commands remain available:

```bash
python3 scripts/build.py
python3 bridge.py --config /path/to/operator-config.json doctor --live
python3 bridge.py --config /path/to/operator-config.json install --workspace /path/to/project
python3 bridge.py uninstall --workspace /path/to/project
```

Start a manual config from `examples/config.json` and set its actual workspace and execution permissions. The script-based installer is the normal end-user workflow.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| Missing `codex` or `agy` | Install both CLIs and sign in using active subscriptions before rerunning the installer. |
| Reviewer account/model failure | Confirm Codex credentials and reviewer-model access; rerun the installer after resolving them. |
| System dependency installation fails | Install the compiler, Git, `pkg-config` and OpenSSL development headers with your system package manager, then rerun. |
| Existing install directory is refused | Run that checkout's `install.sh`, or select an empty `--install-dir`; unrelated files are preserved. |
| Hook absent in `/hooks` | Confirm you launched agy from the registered workspace and restart/reload the session. |
| Host transcript rejected | Check the config's `app_data_roots` and the host's conversation log path. Canonical `transcript.jsonl` and CLI 1.4.7's `transcript_full.jsonl` are supported. |
| Uninstall encounters malformed hook JSON | Repair `.agents/hooks.json` first; malformed content is left untouched. |

See [architecture](architecture.md) for the upstream implementation and trust boundaries, and [the contributor guide](development.md) for development checks.
