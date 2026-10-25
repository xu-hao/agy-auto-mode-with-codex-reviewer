# Antigravity → Codex Guardian

Run `agy` normally, with Codex Guardian reviewing proposed tool calls before Antigravity executes them.

## Use it with agy

First, complete the [one-time installation](docs/install.md#install): build the bridge and create its operator config. In that config, set your project's absolute path in `workspace_roots` and `permissions.writable_roots`, with the actual permissions for your environment.

Register the hook for your project, then launch `agy` there:

```bash
python3 "$HOME/.local/share/antigravity-guardian/bridge.py" \
  --config "$HOME/.config/antigravity-guardian/config.json" \
  install --workspace /absolute/path/to/your/project

cd /absolute/path/to/your/project
agy
```

The checkout and config paths above match the installation guide. Inside `agy`, type `/hooks` and confirm `codex-guardian-review` is loaded. Then give Antigravity your normal task, for example:

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
