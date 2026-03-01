# OpenClaw Config Schema Snapshot

Last updated: 2026-02-27 (v2026.2.26)

This is a point-in-time reference of the upstream config schema.
The audit script uses this to detect drift without requiring network access.

## Key Schema Changes by Version

### v2026.2.15 (Breaking)
- `channels.pairing` removed — use `channels.telegram.groupPolicy` + `groupAllowFrom` + `groups`
- Telegram token key: `botToken`, not `token`
- `tools.exec.ask` expects string (`"off"|"on-miss"|"always"`), not array
- Removed keys: `tools.policyMode`, `tools.exec.fallback`, `tools.exec.rules`
- Removed keys: `tools.elevated.require`, `tools.elevated.allowWhenRequestedBy`
- Use `tools.elevated.enabled` + `tools.elevated.allowFrom.telegram`

### v2026.2.17 (Breaking)
- `tools.exec.safeBins` enforced — must be executable names, not paths
- `tools.exec.ask: "on-miss"` recommended for allowlist security
- Approval `to` field: no `${env:...}` interpolation, use concrete IDs
- `SPAPS_WEBHOOK_AUTH_TOKEN` supported for cron webhook auth
- SSRF guards: `SPAPS_API_URL` must be public or Tailscale-routable
- `approvals.exec.mode: session|targets|both` (no legacy `spaps` block)
- Runtime placeholders `{{MediaPath}}`, `{{Prompt}}`, `{{MaxChars}}` are valid

### v2026.2.19
- iOS/Apple Watch companion support
- `device.pair.remove` + `openclaw devices remove` CLI commands
- `gateway.http.no_auth` audit finding when `gateway.auth.mode="none"`

### v2026.2.21
- No config schema changes identified in release notes

### v2026.2.22
- No config schema changes identified in release notes

### v2026.2.23
- No config schema changes identified in release notes

### v2026.2.24
- No config schema changes identified in release notes

### v2026.2.25
- No config schema changes identified in release notes

### v2026.2.26 (Security + Config)
- **DM allowlist enforcement**: `dmPolicy: "allowlist"` with empty `allowFrom` now silently drops DMs (was permissive). Affects Telegram, Discord, Slack, Signal, iMessage, IRC, BlueBubbles, WhatsApp.
- **`openclaw doctor --fix`** restores missing `allowFrom` entries from pairing-store.
- **External secrets management**: `openclaw secrets` workflow (`audit`, `configure`, `apply`, `reload`).
- **Secrets config block**: `secrets.providers`, `secrets.defaults` for env/file/exec secret sources.
- **ACP/Thread-bound agents**: `acp` spawn/send dispatch integration.
- **Agent routing CLI**: `openclaw agents bindings/bind/unbind` for account-scoped routes.
- **Codex WebSocket transport**: `openai-codex` WebSocket-first by default (`transport: "auto"` with SSE fallback).
- **Plugin onboarding hooks**: `configureInteractive` and `configureWhenConfigured` optional hooks.
- **`plugins.entries.*` unknown keys**: now warnings instead of hard crash (was crash-loop).
- **Node exec approvals**: structured `commandArgv` approvals for `host=node`, `GIT_EXTERNAL_DIFF` blocked.
- **Config includes hardening**: `$include` files verified-open, hardlink rejected, size-guarded.
- **Multi-account channel migration**: `openclaw doctor --fix` repairs mixed channel account shapes.
- **`openai-codex-responses`** accepted in config model API schema.
- **Auth profiles alias normalization**: `mode -> type`, `apiKey -> key` aliases accepted.

## Top-Level Config Sections (v2026.2.26)

- `agents` (defaults, list)
- `tools` (profile, allow, deny, elevated, exec, web, media, loopDetection, agentToAgent, sessions, subagents, sandbox)
- `channels` (telegram, discord, slack, whatsapp, signal, imessage, googlechat, mattermost, msteams, web, defaults)
- `gateway` (port, mode, bind, auth, tailscale, controlUi, remote, trustedProxies, http, tools)
- `approvals` (exec: enabled, mode, agentFilter, targets)
- `commands` (native, nativeSkills, text, bash, config, debug, restart, allowFrom, useAccessGroups)
- `plugins` (enabled, allow, deny, load, entries, slots, installs)
- `skills` (allowBundled, load, install, entries)
- `models` (mode, providers, bedrockDiscovery)
- `session` (scope, dmScope, identityLinks, reset, resetByType, resetTriggers, store, parentForkMaxTokens, maintenance, threadBindings, agentToAgent, sendPolicy)
- `messages` (responsePrefix, ackReaction, ackReactionScope, removeAckAfterReply, queue, inbound, groupChat, tts)
- `cron` (enabled, maxConcurrentRuns, webhook, webhookToken, sessionRetention, runLog)
- `hooks` (enabled, token, path, maxBodyBytes, defaultSessionKey, presets, transformsDir, mappings, gmail)
- `browser` (enabled, evaluateEnabled, defaultProfile, ssrfPolicy, profiles, color, headless, noSandbox, executablePath, attachOnly)
- `ui` (seamColor, assistant)
- `logging` (level, file, consoleLevel, consoleStyle, redactSensitive, redactPatterns)
- `env` (vars, shellEnv)
- `secrets` (providers, defaults) — NEW in v2026.2.26
- `auth` (profiles, order)
- `discovery` (mdns, wideArea)
- `canvasHost` (root, liveReload, enabled)
- `talk` (voiceId, voiceAliases, modelId, outputFormat, apiKey, interruptOnSpeech)
- `wizard` (metadata)
- `meta` (lastTouchedVersion, lastTouchedAt)
