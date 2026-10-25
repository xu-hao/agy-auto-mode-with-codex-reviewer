# Models and providers

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

See [installation](install.md) for the operator config location and workspace setup, and [architecture](architecture.md) for differences from shipping Codex.
