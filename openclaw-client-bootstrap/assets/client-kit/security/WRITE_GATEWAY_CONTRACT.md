# Write Gateway Contract

This contract enforces the rule:

`OpenClaw may propose writes, but only the operator-controlled gateway may execute them.`

For command-level allowlist/wrapper patterns, see `security/PERMISSIONS_PLAYBOOK.md`.

## 1. Credentials

- OpenClaw host stores read-only credentials only.
- Write credentials are stored only in the write gateway runtime.
- Operators approve each mutation before execution.

## 2. Proposal Object

Every mutating recommendation must produce a proposal object:

```json
{
  "proposal_id": "uuid",
  "created_at": "2026-02-17T18:00:00Z",
  "client_id": "client-a",
  "requested_by": "openclaw-analyst",
  "target_system": "example-crm",
  "operation": {
    "method": "POST",
    "path": "/v1/customers/123/tags",
    "payload": {
      "tag": "at-risk"
    }
  },
  "business_reason": "Reduce churn for users with 30-day inactivity.",
  "expected_impact": "Improves retention in at-risk cohort.",
  "risk_level": "medium",
  "rollback": {
    "method": "DELETE",
    "path": "/v1/customers/123/tags/at-risk"
  },
  "dry_run_supported": true
}
```

## 3. Approval States

`proposed -> approved -> executed -> verified`

or

`proposed -> rejected`

## 4. Mandatory Enforcement

1. Gateway refuses execution when state is not `approved`.
2. Approval must include approver identity and timestamp.
3. Execution must log payload hash and response code.
4. Gateway must support idempotency keys for retries.
5. High-risk operations require two-person approval.

## 5. Operator UX

- Telegram sends a notification with a link to the Unclawg portal.
- The portal displays the full proposal:
  - proposal_id
  - impact
  - risk
  - endpoint and method
  - rollback summary
- Operator reviews at the portal and chooses approve or reject.
- SPAPS records the decision and updates approval state.
- Gateway executes only after SPAPS state is `approved`.

## 6. Auditing

Store immutable logs for:

- proposal creation
- approval/rejection (via SPAPS)
- execution result
- rollback action

Retention: minimum 1 year (or client policy, whichever is stricter).
