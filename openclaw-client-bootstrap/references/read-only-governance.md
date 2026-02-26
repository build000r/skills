# Read-Only Governance Pattern

This skill enforces:

`Read-only discovery in OpenClaw, write execution through human approval at the Unclawg portal backed by SPAPS.`

## Controls in OpenClaw

- Sandbox `workspaceAccess` set to `ro`
- File write/edit tools denied
- `exec` default is approval-gated (`ask: "always"`, fallback deny)
- Telegram DM policy restricted to operator allowlists

## Credential Model

- OpenClaw host stores read-only credentials only
- Write credentials never stored on the OpenClaw host
- All mutating API calls require explicit operator approval

## Approval Surface

- **Telegram** = notification channel ("doorbell") — sends links to the approval portal
- **unclawg.com** = approval UI ("front door") — operator reviews and approves/rejects
- **SPAPS** = approval backend — manages approval state and audit trail

Operators never approve inline in Telegram. They click the portal link, review the full proposal, and approve or reject in the Unclawg portal.

## Required Proposal Contents

Every suggested write action should include:

1. Endpoint + method
2. Payload summary
3. Business reason
4. Expected impact
5. Risk level
6. Rollback action
7. Approval owner

## Approval Ownership

- Unclawg portal is the single approval surface for all operators
- Telegram delivers notification links to designated operators
- High-risk changes use two-person approval
- SPAPS records approver identity, timestamp, payload hash, and result
