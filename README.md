# Auto mode for agy

Auto mode for Google Antigravity, powered by Codex.

## Install and use with agy

Prerequisites:

- Active Codex and Google Antigravity subscriptions, with `codex` and `agy` installed and signed in.
- Access to the configured Codex reviewer model (`codex-auto-review` for the default ChatGPT setup).
- Python 3.12+ and `curl`.

From your agy project directory:

```bash
curl -fsSL https://raw.githubusercontent.com/xu-hao/agy-auto-mode-with-codex-reviewer/main/install.sh | bash
agy
```

The installer builds the reviewer, creates a private workspace configuration, checks Codex access, and registers the hook. It installs Rust and missing build prerequisites automatically on Ubuntu/Debian; `sudo` may ask for your password. The first build can take several minutes. Later installs reuse the build.

Inside `agy`, type `/hooks` and confirm `codex-guardian-review` is loaded. Then give agy your normal task. Codex handles approvals automatically; existing Antigravity allow/deny lists remain in effect.

If you already cloned this repository, run `./install.sh /path/to/your/project` instead. To enable another workspace, run the installer there too. See the [installation guide](docs/install.md) for options and other Linux distributions.

## Audit approvals and rejections

From your project directory:

```bash
"$HOME/.local/share/antigravity-guardian/audit.sh"
```

Shows recent commands, approvals/rejections and reasons. Add `--follow` to watch live, or `--decision rejected` to show policy denials. Private logs are enabled by the installer; rerun it once if you installed before auditing was added. See [auditing](docs/auditing.md) for filters and logging controls.

## Uninstall

From the workspace where you enabled it:

```bash
"$HOME/.local/share/antigravity-guardian/uninstall.sh"
```

Or pass a workspace explicitly: `./uninstall.sh /path/to/your/project` from this checkout. Reload Antigravity afterward. This removes the workspace's hook and preserves other hooks, permission rules, credentials and local files.

## Documentation

- [Installation, options and troubleshooting](docs/install.md)
- [Models, authentication and provider configuration](docs/configuration.md)
- [Audit logs and decision history](docs/auditing.md)
- [Review context and known limitations](docs/context-and-limitations.md)
- [JSON interface](docs/interface.md)
- [Architecture, upstream reuse and trust boundaries](docs/architecture.md)
- [Contributor guide](docs/development.md)

## License

Apache-2.0. See [LICENSE](LICENSE) and [upstream notices](UPSTREAM_NOTICE).
