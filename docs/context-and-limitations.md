# Review context and remaining limitations

Each review sends the configured Codex reviewer model a snapshot of the pending action and the available conversation. It does not send a complete copy of the workspace or execution environment.

## What Guardian receives

| Context | Source and handling |
| --- | --- |
| Proposed action | Exact tool name and complete arguments. Command text is not expanded, rewritten or executed by the reviewer. |
| User authorization | Original request and subsequent explicit user messages from the canonical Antigravity transcript. Assistant claims and tool results cannot create user authorization. |
| Conversation evidence | Source-attributed assistant messages, previous tool calls and results, subject to upstream retention limits. |
| Working directory | An explicit `Execution context.cwd` field in model input, even when tool arguments omit `Cwd`. Its source is included separately. |
| Execution metadata | Hook workspace paths, session step and Antigravity model. `bridge_platform` identifies the Python process's platform, not a verified target platform. |
| Permissions and policy | Trusted operator configuration plus the upstream Guardian policy and output contract. Antigravity continues enforcing its own execution rules. |
| Additional evidence | Public JSON requests may supply evidence; it is labelled untrusted and cannot establish authorization. |

The working directory, environment metadata and original request are reserved outside the bounded assistant/tool transcript. They are counted toward the full input budget. The pending action is kept complete; a request that cannot fit the required context fails instead of approving a partially rendered action.

Conversation and tool evidence can include private file excerpts or secrets. Material included in the retained model input is sent to the configured provider. Audit logs deliberately store less than the complete review context; see [auditing](auditing.md).

## Directory and shell handling

For an Antigravity hook call:

- A tool's explicit `Cwd` is passed through and labelled `explicit tool Cwd`.
- If `Cwd` is absent, a single reported workspace supplies the directory, labelled `inferred single workspace; actual cwd not provided by hook`.
- If the directory is ambiguous, missing or outside the configured workspace roots, review fails and execution is blocked.
- Shell, shell options and environment-variable values are marked unknown (`null`): this hook contract does not report them. The bridge does not substitute its own `$SHELL` or environment. An explicit shell invocation inside the proposed command remains visible as part of that exact command.

For the public JSON interface, the separate `cwd` is always rendered into model input. Optional `environment` must be an object. Shell and other values supplied there remain caller declarations, not independently verified execution state or user authorization. The bridge sets their source labels itself. A contradictory `environment.cwd` or `run_command` argument `Cwd` is rejected. See [the JSON interface](interface.md).

For example, a request with `cwd: "/work/app/packages/api"` and command `rm -rf build` now explicitly shows Guardian which directory the caller declared. This does not prove that Antigravity's executor will use that directory. An inferred workspace is still an inference.

## Remaining gaps

| Gap and example | Current behavior | Work needed |
| --- | --- | --- |
| Missing execution state: `rm -rf "$BUILD_DIR"` depends on the variable's value; a pipeline's behavior can depend on `pipefail`. | Missing facts stay unknown. No process-environment dump or automatic variable expansion is performed. | Obtain relevant values, shell executable/options and actual cwd from a supported executor interface, with source labels and sensitive-value handling. |
| Hidden file behavior: `npm test` may invoke a destructive `pretest`; `python cleanup.py` hides its implementation. | Guardian sees file contents only if retained transcript/evidence contains them. There are no investigation tools. Missing evidence can lead to denial, but the model is not guaranteed to detect every hidden effect. | Add restricted read-only investigation tools with enforced filesystem/network permissions. Native Codex's reviewer has such tools; its documentation says it uses them rarely. |
| Files change after review: `cleanup.sh` is edited after `bash cleanup.sh` is approved. | The binding covers the action, transcript and operator configuration. It does not freeze or hash referenced files, dependencies, symlink targets, directory contents or environment state. | Coordinate review and execution using snapshots or a version check enforced by the executor. Hashing files only inside the hook would leave another race after the hook returns. No general freeze for arbitrary shell dependencies was found in the native Codex review path inspected at our pin either. |
| Old evidence is omitted: an earlier tool result showed that `cleanup.py` deletes a database, but that result no longer fits. | Upstream context selection bounds assistant/tool evidence. Genuine user instructions are protected; required input that cannot fit is blocked. The bridge has no parent checkpoint recovery or file reread tools. | Retrieve action-relevant evidence again, or add checkpoint/context recovery and read-only inspection. Native Codex also has bounded context, with more runtime recovery mechanisms. |
| The host changes or fails to enforce the action: another hook rewrites arguments after approval, or the host ignores an abnormal hook failure. | The bridge returns its verdict for the received action. It cannot enforce the executor's internal behavior or later hooks. | Keep the review gate after argument-rewriting hooks and validate each supported host version. Stronger guarantees need executor cooperation and independent permissions. |

The reviewer remains model based and can make mistakes. A lack of evidence is not proof of safety, and an allow verdict is not proof that execution occurred. Keep Antigravity's filesystem/network restrictions and explicit permission rules in effect.

## Changes during review

The bridge rechecks the transcript and operator config before returning a verdict. If you add “Stop; do not deploy” while review is pending, the changed transcript invalidates the earlier review. Reusing an old verdict for a different action is blocked by request ID and binding checks.

Those checks protect pending review context. They do not freeze external files or eliminate the interval between the hook's final check and execution, and they do not retroactively stop a command already running.

## Native Codex comparison

At the [pinned revision](architecture.md), native Codex constructs approval requests with explicit command arguments, cwd and environment attribution, can provide the reviewer read-only tools, and supports conversation checkpoints and authorization-version checks. This bridge reuses Guardian's policy/context/model/parser/retry components but supplies its own Antigravity adapter and has no investigation tool dispatcher.

Native Codex normally invokes Auto-review for eligible requests at a sandbox boundary; this bridge reviews every pending hooked tool call. Neither arrangement makes model review a deterministic guarantee. See the official [Auto-review documentation](https://developers.openai.com/codex/sandboxing/auto-review) and [architecture](architecture.md) for the inspected implementation and runtime differences.
