# JSON interface

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
    "arguments": {"CommandLine": "npm test"}
  },
  "cwd": "/absolute/path/to/workspace",
  "environment": {},
  "evidence": {"script_contents": "optional relevant evidence, never authorization"}
}
```

The adapter constructs the full native request with the original user request, role-attributed history, provenance, operator permissions, evidence, and a SHA-256 binding. Caller-supplied `original_user_request` or `history` fields remain untrusted evidence. Only explicit user records loaded from the configured host transcript can establish authorization. See [the protocol and trust boundary](architecture.md).

The separate absolute `cwd` is always included in the model's execution context, including when action arguments omit `Cwd`. A conflicting `Cwd` on `run_command` or conflicting `environment.cwd` is rejected. The command and its original arguments are preserved.

`environment` is an optional object. A caller may provide relevant shell/options/variable details, but the bridge labels them as caller declarations that have not been independently verified; they cannot authorize actions. Missing shell, shell options and variable values remain `null`. The bridge sets `declared_by`, `cwd_source` and `shell_source` rather than trusting caller-provided source labels. It does not collect its own process environment as a substitute for the executor's state. See [review context and remaining limitations](context-and-limitations.md).

A successful response includes `request_id`, `binding`, `status: "reviewed"`, `decision: "approve" | "block"`, the upstream `assessment`, model/backend metadata, attempts, and `executed: false`. An error blocks execution and is distinguished from a model denial. The `hook` command emits only Antigravity’s accepted `decision` and `reason` fields, including on errors.

`prepare` has the same input as `review` and emits the actual upstream-rendered policy, bounded context and schema without inference. It can contain private transcript data; use it deliberately.

See [architecture and trust boundaries](architecture.md) for provenance, request binding and the internal native interface.
