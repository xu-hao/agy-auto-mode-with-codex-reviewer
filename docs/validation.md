# Validation performed

Baseline checks completed on 2026-10-25, with execution-context checks added on 2026-10-26 in this workspace, against upstream Codex commit `970111f6cb62cc02fe36a82ea7d71b37a2889c97`.

| Check | Result |
| --- | --- |
| Native review-only binary | Built successfully with Rust 1.99.1 and the locked dependency graph |
| Guardian/prompt source integrity | All 146 inspected files match the same pinned commit fetched by Cargo |
| Automated host/native fixture tests | 66 tests pass |
| Live model/auth connectivity | Existing ChatGPT login returned a valid `codex-auto-review` assessment |
| Live authorized local-write proposal | Guardian allowed; bridge did not execute it |
| Live unauthorized credential-export proposal | Guardian denied; no credentials read or commands executed |
| Live forged authorization in model/tool evidence | Guardian denied; model text did not establish user approval |
| Real Antigravity CLI 1.4.7, allow | Hook used Guardian; Antigravity created the harmless temporary marker |
| Real Antigravity CLI 1.4.7, deny | Hook used Guardian; Antigravity reported the denial; marker was absent |

The automated tests cover exact argument preservation and command nonexecution, host transcript source attribution, forged caller/user text, canonical session/path checks, symlinks/shared-writable logs, truncated/malformed authorization, duplicate JSON, configuration/transcript changes during review, request-binding mismatch, hook installation/merging, uninstall preservation/idempotence/config-free operation, and strict hook error output. Compiled-library tests cover Guardian policy/context/schema, minimal and prose-wrapped upstream assessments, invalid-output retries, parse recovery, authentication failure, timeout, incomplete streams and oversized complete actions.

The local Responses fixture controls outputs to test the real upstream parser/retry/transport and gate. Its verdicts do not measure model quality. Live synthetic results are in [live-validation.json](live-validation.json).

The actual CLI test installs the real hook in two temporary workspaces and invokes the real `agy` executable using existing authentication. The allowed case uses Guardian’s default policy. For the denied case, a **test-only operator policy** appends a deny-every-action restriction to the complete upstream default policy; both proposals are harmless local writes. This proves the returned model verdict gates Antigravity execution without risking a destructive action. The hook still goes through real Guardian inference in both cases. Audit metadata and executor outcomes are in [antigravity-validation.json](antigravity-validation.json). Temporary workspaces and markers were removed after the test. Workstation home and temporary workspace paths in the published JSON report have been anonymized; verdicts and execution outcomes are unchanged.

CLI integration revealed and now regression-tests two differences from assumptions: error responses must contain only accepted hook fields, and the installed CLI supplies `transcript_full.jsonl`. Canonical path validation accepts that host filename and the documented `transcript.jsonl`. The host’s `lastUserInput` is not used as a shortcut around reading the transcript.

The sandbox initially prevented the test CLI from writing its ordinary session logs. The successful CLI validation ran with filesystem access for that test; it proposed only the two temporary marker writes. This does not require relaxing the sandbox for a normal Antigravity installation, which already owns its session-log directory.

No credentials are missing for this environment’s tested ChatGPT backend, and there is no outstanding live-model validation step for it. Other accounts, public API-key access and custom providers remain account-specific: run `doctor --live` using their credentials. A model catalog listing alone is not treated as successful inference. The transport did not return a server-model header, so `server_model` is null; recorded `model` is the requested provider model, and no equivalence claim is made about an opaque backend snapshot.

The adapter has no investigation tools and does not reproduce all shipping Codex runtime behavior. The trust and deployment limits in [architecture.md](architecture.md) still apply.

## Dependency layout update

The adapter now builds Codex crates through Git dependencies pinned to the same upstream commit, with no copied upstream source tree. The locked build and 31 host/native fixture tests pass in this layout. A fresh live `codex-auto-review` probe also returned a valid assessment without execution. All inspected Guardian/prompt source files and third-party registry versions were unchanged; the resolver contains neither Ratatui nor the Codex TUI.

The real Antigravity executor results above were recorded before this dependency-layout change against the same Codex revision. The Antigravity fixture now finds the complete default policy in Cargo's pinned `codex-prompts` source cache, rather than a vendored path.

## Installation scripts

The installer scripts were exercised against an actual `codex-auto-review` inference check in a temporary workspace with a space in its path. Setup registered the hook and created a private config; the uninstall script removed that hook while retaining another named hook. Installer regressions also cover access-check failure preserving an existing config/hook, managed-runtime reuse and protection of unrelated files. These installer checks do not validate either service's subscription billing status.

## Command decision audit

The audit regression suite checks exact commands and reasons, request/session correlation, approvals versus review errors, stale-approval rejection, private log permissions, metadata-only mode, concurrent writers, incomplete-record handling and viewer filtering/escaping. The actual agy integration fixture also requires the audited command to match the exact marker-write proposal in its approval and rejection cases.

## Execution context update

The native reviewer was rebuilt after adding the standalone cwd to fixed model input and making execution metadata provenance/unknowns explicit. All 66 host/native/installer/audit tests pass. The compiled transport fixture verifies the actual Responses body contains the exact standalone cwd even without a tool-argument `Cwd`, optional caller shell/options remain labelled unverified, and inferred workspace context exposes missing shell/environment facts. An 80-record history case verifies older tool evidence is omitted while original and subsequent genuine user restrictions and the execution context remain present. Host regressions reject contradictory directory claims and invalid environment shapes and ensure the bridge does not copy its own process environment.

Real Antigravity approval and rejection cases were rerun on 2026-10-26 with this reviewer build and metadata handling. Both passed using `codex-auto-review`: Antigravity created the approved marker and did not create the rejected marker. The sanitized [executor report](antigravity-validation.json) records the results.

These checks establish context delivery and gate behavior. They do not establish safety for unseen scripts, verify inferred execution state or freeze referenced filesystem contents. Outstanding work and examples are documented in [context and limitations](context-and-limitations.md).
