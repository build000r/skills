# Agent-To-Agent Payment Handoffs

Use this reference when one agent, app, or operator service should only perform a
valuable action after a payment has settled. Treat payment as a protected action
contract, not as a chat instruction.

## Core Shape

Sell one specific server-owned action:

- `resource_key`: stable handle for the thing being paid for
- `resource_type`: `handoff_action`, `booking_action`, `review_action`, or another narrow type
- `resource_ref`: opaque pointer to the domain object, such as a booking hold or work request
- `action_key`: exact action being unlocked, such as `operator-book` or `agent-handoff`
- `amount_atomic`, `price_display`, `network`, `asset`, `account_ref_id`: server-authoritative payment terms

The browser or requesting agent may choose whether to pay, but must not choose
the pay-to wallet, facilitator, account reference, amount, network, or asset.

## Recommended Flow

1. The seller service creates or reuses a domain-owned pending object, such as a
   booking hold, review case, or work order.
2. The seller service creates a paid resource for the protected action. Secret
   or server authority owns lifecycle changes; publishable keys can only call
   explicitly public creation/status/action endpoints.
3. The buyer agent reads resource status with application context.
4. The buyer agent attempts the protected action without a payment header.
5. The server responds `402` with `PAYMENT-REQUIRED`, including the x402
   challenge and a server-minted payment identifier.
6. The buyer wallet or payment adapter signs/pays the exact requirement and
   retries with `PAYMENT-SIGNATURE`.
7. The server verifies and settles through the configured facilitator, records
   the attempt and receipt, and returns `PAYMENT-RESPONSE`.
8. The seller domain confirms the original hold or opens the paid work surface.

For handoffs to a local bridge or another agent, return a short-lived,
single-use authorization token after settlement. Bind that authorization to the
receipt, `resource_key`, `action_key`, downstream `target`, and a bridge-token
hash. The bridge must verify the authorization before executing. For non-handoff
paid resources, return the settled receipt without requiring handoff-only fields.

## Binding Rules

Bind paid work to enough state that a valid payment cannot be reused for a
different action:

- `application_id`
- `resource_key`
- `action_key`
- payment identifier
- receipt id or transaction signature
- idempotency key
- payload fingerprint for semantic create requests

Same-payment retries against the same resource/action should return the same
receipt. Replays against a different resource, action, application, or payload
must be rejected.

## Booking Packet Additions

When recommending a paid human/operator booking, include only configured payment
facts:

```markdown
**Payment state:** [not required | required before handoff | already settled]

**Paid action:** [configured resource/action name]

**Payment proof to bring:** [receipt id, payment response header, or none yet]
```

If those fields are not configured, leave them out or ask for the missing
business term. Do not infer settlement from a screenshot, URL, wallet address,
or user claim unless the server has verified the receipt.

## Failure Signatures

| Signal | Meaning | Next action |
| --- | --- | --- |
| `402 x402_payment_required` plus `PAYMENT-REQUIRED` | Payment is required and no valid payment was supplied | Buyer should pay and retry with `PAYMENT-SIGNATURE` |
| `402 x402_payment_invalid` | Payment was malformed, rejected, failed, or mismatched | Retry with a fresh challenge; inspect payload binding |
| `403 x402_resource_paused` | Paid action is administratively paused | Do not bypass; ask the operator to unpause or choose another path |
| `409 x402_replay_detected` | Payment proof was reused across the wrong boundary | Stop and verify resource/action/payload binding |
| `502 x402_facilitator_unavailable` | Payment verifier/settler is unreachable | Retry later or switch to a configured fallback |
| `x402_resource_misconfigured` | Server lacks a valid payment account/resource config | Fix server config before asking the buyer to retry |

## Safety Checks

- Keep mainnet or production payments disabled until a testnet smoke has proved
  challenge, signing, settlement, receipt lookup, replay rejection, invalid
  payment handling, paused resource handling, and rollback.
- Do not log raw payment signatures, payment response headers, bridge tokens,
  private keys, seed phrases, facilitator credentials, or raw authorization
  tokens.
- Do not treat a wallet address as identity by itself. Attach receipts to a
  user only through the app's normal identity rules.
- Keep payment code behind a small adapter boundary. The skill should describe
  the handoff and evidence needed; the application should own settlement.
