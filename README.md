# Antigravity → Codex Guardian

Run `agy` normally, with Codex Guardian reviewing proposed tool calls before Antigravity executes them.

## Install and use with agy

### 1. Install prerequisites

You need Python 3.12+, Git, Rust through [rustup](https://rustup.rs/), a C/C++ build toolchain, `pkg-config`, and OpenSSL development headers. The bridge currently has a Linux setup guide.

On Ubuntu:

```bash
sudo apt install git build-essential pkg-config libssl-dev
rustup toolchain install 1.99.1 --profile minimal
```

Have `agy` installed and signed in. For the default ChatGPT backend, sign in through Codex with `codex login` if you haven't already. Access to the `codex-auto-review` model depends on your account.

### 2. Clone and build the bridge

```bash
mkdir -p "$HOME/.local/share"
git clone https://github.com/xu-hao/agy-auto-mode-with-codex-reviewer.git "$HOME/.local/share/antigravity-guardian"
cd "$HOME/.local/share/antigravity-guardian"
python3 scripts/build.py
```

The first build downloads dependencies and takes several minutes. Keep this checkout outside the workspaces your generating agent can modify.

### 3. Create your configuration

```bash
install -d -m 700 "$HOME/.config/antigravity-guardian"
install -m 600 examples/config.json "$HOME/.config/antigravity-guardian/config.json"
```

Edit `$HOME/.config/antigravity-guardian/config.json`:

- Set `workspace_roots` to your project's absolute path.
- Set `permissions.writable_roots` to the directories Antigravity can actually write.
- Set the remaining `permissions` fields to match your actual filesystem and network restrictions.

The template's `app_data_roots` already cover the standard Antigravity App, CLI and IDE locations. For another model or provider, see [configuration](docs/configuration.md).

### 4. Check model access and register the hook

```bash
python3 "$HOME/.local/share/antigravity-guardian/bridge.py" \
  --config "$HOME/.config/antigravity-guardian/config.json" doctor --live
```

Continue when the response contains `"live_inference_validated": true`. This checks reviewer access without executing the proposed command; either an allow or deny verdict can confirm connectivity.

Register the hook for the project you put in the config:

```bash
python3 "$HOME/.local/share/antigravity-guardian/bridge.py" \
  --config "$HOME/.config/antigravity-guardian/config.json" \
  install --workspace /absolute/path/to/your/project
```

### 5. Start agy in that project

```bash
cd /absolute/path/to/your/project
agy
```

Inside `agy`, type `/hooks` and confirm `codex-guardian-review` is loaded. Then give Antigravity your normal task, for example:

> Create hello.txt containing hello.

Antigravity proposes each tool call; the hook submits it to Guardian for a model-based verdict. An allow verdict lets Antigravity execute the call subject to its own permission rules. A denial or reviewer failure blocks the call and gives Antigravity the reason. Existing allow/deny lists remain in effect.

The hook starts the reviewer automatically. Register each workspace you use, and restart or reload an existing Antigravity session after changing its hooks. The same hook applies to `agy -p "your task"` when run from that workspace.

## Uninstall

Unregister each workspace, then reload Antigravity:

```bash
python3 "$HOME/.local/share/antigravity-guardian/bridge.py" \
  uninstall --workspace /absolute/path/to/your/project
```

This removes only the bridge's named hook and preserves other hooks and permission lists. It works without the config file or model credentials. The [uninstall guide](docs/install.md#uninstall) covers optional local-file cleanup and recovery if the checkout was already deleted.

## Documentation

- [Installation, configuration setup and troubleshooting](docs/install.md)
- [Models, authentication and provider configuration](docs/configuration.md)
- [JSON interface](docs/interface.md)
- [Architecture, upstream reuse and trust boundaries](docs/architecture.md)
- [Contributor guide](docs/development.md)

## License

Apache-2.0. This project borrows unmodified Codex Guardian source pinned to commit `970111f6cb62cc02fe36a82ea7d71b37a2889c97`; it maintains no Codex fork. See [LICENSE](LICENSE) and [upstream notices](UPSTREAM_NOTICE). The [architecture documentation](docs/architecture.md) explains how the review-only host differs from the full Codex runtime.
