# Development and testing

Cargo fetches the pinned Codex crates directly from upstream; this repository does not vendor the Codex source tree. Build the native reviewer first, following the [installation guide](install.md#prerequisites) for toolchain requirements:

```bash
python3 scripts/build.py
```

The Python test suite does not require model credentials. Native integration cases use the compiled binary and a local Responses SSE fixture. Those cases are skipped if the binary is missing, so build it before running the complete suite.

## Run the checks

```bash
python3 -m unittest discover -s tests -v
python3 scripts/live_validate.py          # real Guardian model; never executes proposals
python3 scripts/antigravity_validate.py   # real agy + Guardian; harmless /tmp marker writes
```

Fixture tests use the real compiled Guardian libraries with a local Responses SSE server. They test transport, parsing, retry and gate behavior, not model safety quality. The live scripts use existing logins and incur normal model usage.

The live scripts require the real model/provider credentials and, for the executor check, the installed `agy` CLI. They write reports under `docs/`; the saved publication report anonymizes workstation and temporary-workspace paths.

See [validation results](validation.md) for completed checks and their practical limits, and [architecture](architecture.md) for the upstream flow and adapters.
