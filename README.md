# Antigravity → Codex Guardian

A local review-only bridge using **the real Apache-2.0 Codex Guardian components**, borrowed at commit `970111f6cb62cc02fe36a82ea7d71b37a2889c97`. There is no Codex fork and no change to the borrowed reviewer source.

Antigravity generates the action and runs it after approval. This bridge submits the exact proposed arguments and host transcript to Guardian, then returns `auto_approve` or `deny` through Antigravity’s `PreToolUse` hook. The reviewer has no execution tools, shell dispatcher, or action executor. It does not use execpolicy, command prefix rules, or a replacement safety prompt to decide.

The native binary has been compiled and tested here. Live reviews using the existing ChatGPT login and **`codex-auto-review`** passed the authorized local-write, unauthorized credential-export, and forged-authorization cases. Proposed commands were never executed by the bridge. See [validation details](docs/validation.md).

## Install

Follow the [installation and uninstall guide](docs/install.md) for clone/build steps, protected configuration, verification, hook registration, removal and troubleshooting.

Requirements: Python 3.12+, Rust **1.99.1**, a C/C++ build toolchain, `pkg-config`, OpenSSL development headers, and a supported Codex login or provider credential. On Ubuntu the native dependencies include `build-essential pkg-config libssl-dev`. The first build downloads Rust dependencies and takes several minutes.

```bash
python3 scripts/build.py
cp examples/config.json /tmp/guardian-config.json
chmod 600 /tmp/guardian-config.json
```

Edit that config: set the absolute workspace path and its **actual Antigravity permission context**. For ongoing use, put the config and bridge in an operator-controlled location outside the agent’s writable roots. `/tmp` above is only a quick-start location, not a persistent deployment location.

```bash
python3 bridge.py --config /tmp/guardian-config.json doctor
python3 bridge.py --config /tmp/guardian-config.json doctor --live
python3 bridge.py --config /tmp/guardian-config.json install --workspace /absolute/path/to/workspace
```

`doctor` reports configuration and catalog selection. **`doctor --live` performs an actual review-only inference**; `live_inference_validated: true` means a valid assessment was received. A deny is also a successful connectivity check. It never executes the synthetic command.

The installer merges a named hook into `.agents/hooks.json` without removing other named hooks. It matches **all tools**, including terminal input and file writes, so a rejected command cannot simply be submitted through another tool without review. Reload Antigravity and inspect `/hooks` to confirm it loaded. The installed hook returns `auto_approve` for a completed allow assessment and `deny` for a denial or failure. Antigravity still honors its explicit permission rules.

The real CLI integration tests use temporary workspaces. Run the installer for each workspace where you want the bridge active.

## Uninstall

Run this for each registered workspace, then reload Antigravity:

```bash
python3 bridge.py uninstall --workspace /absolute/path/to/workspace
```

This removes only the named bridge hook and preserves other hooks and Antigravity permission lists. It works without the config file or model credentials. See the [uninstall guide](docs/install.md#uninstall) for optional local-file cleanup and recovery when the checkout was already deleted.

## JSON interface

Public CLI, one request on stdin and one response on stdout:

```bash
python3 bridge.py --config /tmp/guardian-config.json review < request.json
```

```json
{
  "request_id": "unique-action-1",
  "session_id": "d633886d-392a-4338-8b44-80a4b20d424e",
  "transcript_path": "/home/me/.gemini/antigravity-cli/brain/d633886d-392a-4338-8b44-80a4b20d424e/.system_generated/logs/transcript.jsonl",
  "action": {
    "tool": "run_command",
    "arguments": {"CommandLine": "npm test", "Cwd": "/absolute/path/to/workspace"}
  },
  "cwd": "/absolute/path/to/workspace",
  "environment": {"shell": "bash", "network": "restricted"},
  "evidence": {"script_contents": "optional relevant evidence, never authorization"}
}
```

The adapter constructs the full native request with the original user request, role-attributed history, provenance, operator permissions, evidence, and a SHA-256 binding. Caller-supplied `original_user_request` or `history` fields remain untrusted evidence. Only explicit user records loaded from the configured host transcript can establish authorization. See [the protocol and trust boundary](docs/architecture.md).

A successful response includes `request_id`, `binding`, `status: "reviewed"`, `decision: "approve" | "block"`, the upstream `assessment`, model/backend metadata, attempts, and `executed: false`. An error blocks execution and is distinguished from a model denial. The `hook` command emits only Antigravity’s accepted `decision` and `reason` fields, including on errors.

`prepare` has the same input as `review` and emits the actual upstream-rendered policy, bounded context and schema without inference. It can contain private transcript data; use it deliberately.

## Models and providers

At this pin, upstream prefers `codex-auto-review` for ChatGPT authentication and `gpt-5.6-luna` for OpenAI API-key authentication. The existing ChatGPT credential in this environment successfully called `codex-auto-review`. Neither that success nor a catalog listing establishes access for a different account/provider.

The native host uses Codex’s `AuthManager`, `ModelProvider`, models manager, Responses client, proxy/TLS handling and auth refresh. It reads `CODEX_HOME` or `~/.codex` for supported login state. It does not manually extract or print tokens. `codex login` and supported API-key environment mechanisms can provision credentials.

To explicitly choose another model, set `native.model`. The response records that choice; it does **not** claim product equivalence. An unavailable model, authentication error, timeout, or invalid assessment blocks the action. The host does not silently replace the preferred reviewer with a parent fallback.

A supported custom provider can be supplied as `native.provider`, using Codex’s `ModelProviderInfo` JSON shape, for example:

```json
{
  "name": "my-responses-provider",
  "base_url": "https://provider.example/v1",
  "wire_api": "responses",
  "env_key": "MY_PROVIDER_API_KEY",
  "requires_openai_auth": false
}
```

Do not set a provider URL from agent-generated tool arguments. Provider settings are trusted operator configuration. The bridge does not automatically import `config.toml`, managed Codex requirements, enterprise policy overrides, plugins or tools. Supply applicable policy through the trusted config. `native.policy` replaces the tenant policy; copy the complete current upstream policy before customizing it.

## Scope

This reuses Guardian’s implementation and actual reviewer model, while adapting the host runtime. It does **not** claim to reproduce every behavior of the shipping Codex product: it uses fresh review context per action, has no investigation tools, inherits no Codex parent session, and does not reproduce Codex’s async scorer, cached approvals, session pool, compaction, override picker, or denial circuit breaker. Missing evidence can result in conservative denials; supply relevant evidence explicitly. Antigravity retains its own execution sandbox and permission enforcement.

Protect the hook, binary, config and host logs from the generating agent’s writes. A hook running as the same OS user cannot defend against an unrestricted process rewriting its own enforcement mechanism. There is no command execution in the reviewer, but approval cannot freeze a script’s bytes or filesystem state between review and Antigravity execution. The host’s transcript/config freshness check prevents stale authorization, not all filesystem races.

## Tests

```bash
python3 -m unittest discover -s tests -v
python3 scripts/live_validate.py          # real Guardian model; never executes proposals
python3 scripts/antigravity_validate.py   # real agy + Guardian; harmless /tmp marker writes
```

Fixture tests use the real compiled Guardian libraries with a local Responses SSE server. They test transport, parsing, retry and gate behavior, not model safety quality. The live scripts use existing logins and incur normal model usage.

Code provenance, reused functions and runtime differences are traced in [architecture.md](docs/architecture.md). Apache-2.0 licensing is in [LICENSE](LICENSE), with upstream notices in [UPSTREAM_NOTICE](UPSTREAM_NOTICE) and the unmodified vendored snapshot.
