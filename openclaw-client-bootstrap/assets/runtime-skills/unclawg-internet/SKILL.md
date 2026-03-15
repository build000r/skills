---
name: unclawg-internet
description: >
  Runtime-safe onboarding flow for Larry. Uses only uc_onboard wrapper commands
  for detect, device authorize/poll, and manual provisioning guidance.
metadata: { "openclaw": { "emoji": "🛂", "requires": { "bins": ["uc_onboard"] } } }
---

# /unclawg-internet

Onboard or rotate Larry credentials with wrapper-only auth flows.

## Hard Constraints

- Use `uc_onboard` only.
- Never expose or log secrets in chat.
- Keep provisioning confirmation human-in-the-loop.

## Commands

```bash
uc_onboard detect
uc_onboard device-start --client-id "${OPENCLAW_CLIENT_ID:-unclawg}"
uc_onboard device-poll --device-code <device_code>
uc_onboard provision --agent-id larry --email <email>
```
