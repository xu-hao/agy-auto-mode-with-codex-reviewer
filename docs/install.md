# Install and uninstall

These steps install the bridge for one Antigravity workspace. Repeat the hook registration for each workspace you want reviewed. The bridge was tested on Linux with Antigravity CLI 1.4.7.

## Prerequisites

- Python 3.12 or later and Git.
- Rust 1.99.1, installed through rustup. The repository's `rust-toolchain.toml` selects that version.
- A C/C++ build toolchain, `pkg-config`, and OpenSSL development headers. On Ubuntu: `sudo apt install build-essential pkg-config libssl-dev`.
- Antigravity with `PreToolUse` hooks.
- A supported Codex login/provider credential. The tested backend uses an existing ChatGPT login and the `codex-auto-review` model. Model access is account-specific; the live check below verifies it.

## Install

1. Clone and build outside the workspaces your generating agent can modify:

   ```bash
   git clone https://github.com/xu-hao/agy-auto-mode-with-codex-reviewer.git "$HOME/.local/share/antigravity-guardian"
   cd "$HOME/.local/share/antigravity-guardian"
   python3 scripts/build.py
   ```

   The first build downloads dependencies and takes several minutes. The output binary is `build/debug/guardian-review`. No model credentials are required to build it.

2. Create a protected operator configuration:

   ```bash
   install -d -m 700 "$HOME/.config/antigravity-guardian"
   install -m 600 examples/config.json "$HOME/.config/antigravity-guardian/config.json"
   ```

   Edit that JSON file. Replace `/absolute/path/to/your/workspace` in `workspace_roots` and `permissions.writable_roots` with your actual workspace path. Set the permission context to match Antigravity's real filesystem/network restrictions. The default `app_data_roots` cover Antigravity App, CLI and IDE host-log locations. Add every workspace you intend to register.

   The default backend reads supported login state from `CODEX_HOME` or `~/.codex`. Authenticate through your normal Codex login mechanism if needed. See [models and providers](../README.md#models-and-providers) for explicit model/provider configuration.

3. Verify configuration and actual model access:

   ```bash
   python3 bridge.py --config "$HOME/.config/antigravity-guardian/config.json" doctor
   python3 bridge.py --config "$HOME/.config/antigravity-guardian/config.json" doctor --live
   ```

   `doctor --live` must report `live_inference_validated: true`. Either an allow or deny assessment can validate connectivity; the connectivity probe never executes its proposed command. Resolve authentication, model-access or provider errors before registering the hook.

4. Register the hook:

   ```bash
   python3 bridge.py --config "$HOME/.config/antigravity-guardian/config.json" install --workspace /absolute/path/to/your/workspace
   ```

   This merges the named `codex-guardian-review` hook into the workspace's `.agents/hooks.json`. Existing named hooks are preserved. The registered command uses absolute paths to this checkout, its configuration and your Python interpreter, so keep those paths stable or rerun the installer after moving them.

5. Reload Antigravity. In the CLI, use `/hooks` to check that `codex-guardian-review` is loaded. App and IDE users can inspect their Hooks customization settings. All proposed tool calls now pass through Guardian. An allow assessment returns `auto_approve`, subject to Antigravity's explicit permission rules; a denial or review failure returns `deny`.

The installed hook requires no background daemon. Keep the checkout, binary, configuration and host transcripts protected from agent writes. If other hooks rewrite tool arguments, ensure this review gate runs after those rewrites.

## Uninstall

Run this from the checkout for **each registered workspace**:

```bash
python3 bridge.py uninstall --workspace /absolute/path/to/your/workspace
```

Uninstall does not require the config file, credentials or a working native binary. It removes only the `codex-guardian-review` entry and preserves other hooks. Repeating it is harmless; if the hook is absent, the result reports `uninstalled: false`. An otherwise empty `hooks.json` remains as `{}`.

Reload Antigravity and check `/hooks` to confirm the bridge is absent. Antigravity then uses its normal permission flow for that workspace. Its allow/deny lists, other hooks and Codex login remain intact. The operator config, audit logs and checkout are retained.

After unregistering the bridge from every workspace, you can optionally remove its local configuration and checkout:

```bash
rm -f -- "$HOME/.config/antigravity-guardian/config.json"
rm -rf -- "$HOME/.local/share/antigravity-guardian"
```

These paths match the installation commands above. Audit logs at a custom `audit_path` can be retained or removed separately.

If the checkout has already been deleted, edit each workspace's `.agents/hooks.json` and remove the top-level `codex-guardian-review` entry, then reload Antigravity. Preserve the other entries and valid JSON.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| Hook absent in `/hooks` | Check the workspace registration, restart/reload Antigravity, and inspect `.agents/hooks.json`. |
| Native binary missing | Run `python3 scripts/build.py` from the checkout. |
| Config rejected as shared-writable | Run `chmod 600` on the operator config and protect its parent directory. |
| Model/authentication failure | Run `doctor --live` using the intended Codex/provider credentials. A catalog listing alone does not validate inference. |
| Host transcript rejected | Check `app_data_roots`, conversation ID and the host's actual transcript path. The adapter accepts canonical `transcript.jsonl` and CLI 1.4.7's `transcript_full.jsonl`. |
| Review fails after moving the checkout/config | Rerun the installer with the new absolute paths. |
| Uninstall reports malformed JSON | Repair `hooks.json` first. The uninstaller leaves malformed content untouched. |

See [architecture and trust boundaries](architecture.md) for the exact upstream components and runtime differences, and [validation](validation.md) for the tests performed.
