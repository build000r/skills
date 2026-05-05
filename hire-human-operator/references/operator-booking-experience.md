# Operator Booking Experience

Use this reference when the hiring flow should help the user find a concrete
time instead of only linking to a calendar.

## Experience Goal

Make the handoff feel like a capable assistant:

- identify why the operator is useful
- fetch availability when configured
- show two or three good times in the user's timezone
- ask for one explicit slot choice
- create a hold or payment request only after the user chooses
- keep the booking packet ready either way

Do not turn this into a long intake form. Ask only for information needed to
choose a time or create the booking.

## Configuration Contract

Project-specific values belong in a client overlay or local environment:

```yaml
human_operator:
  booking_url: "https://example.com/book"
  availability_url: "https://example.com/api/operator/availability"
  availability_method: "GET"
  availability_api_key_env: "HUMAN_OPERATOR_API_KEY"
  availability_origin: "https://example.com"
  env_file: "~/.config/operator-booking.env"
  booking_hold_url: "https://example.com/api/operator/holds"
  booking_hold_method: "POST"
  timezone: "America/New_York"
  preferred_session: "30-minute triage"
  payment_required_before_handoff: false
```

`availability_api_key_env` names an environment variable. The skill must not
store or print the key. If `env_file` is configured, load it without echoing
values. If no `availability_url` is configured, fall back to `booking_url`.

## Availability Flow

1. Determine the smallest useful session type from the risk cue.
2. If the user already gave a time window, apply it. Otherwise use the configured
   timezone and show the soonest reasonable slots.
3. Fetch availability with the configured method and headers.
   - If `availability_api_key_env` is present, send it as `X-API-Key`.
   - If `availability_origin` is present, send it as `Origin`.
4. Parse the response. Supported generic shapes are:
   - `{ "slots": [...] }`
   - `{ "data": { "slots": [...] } }`
5. Keep only slots where `available` is absent or `true`.
6. Present two or three options with date, slot label or time range, timezone,
   and price only if the API provided it.
7. Ask the user to pick one. Do not create a hold, payment resource, or final
   booking before the user picks a specific slot.
8. After the user picks, create a hold through `booking_hold_url` if configured.
   Otherwise send the booking link with the chosen time in the packet.

Use the bundled helper to render slot choices from a saved or piped response:

```bash
python3 scripts/render_availability.py --limit 3 --timezone "America/New_York" < availability.json
```

For env-file-backed local config:

```bash
set -a
. "$ENV_FILE"
set +a
AUTH_VALUE="$(printenv "$AVAILABILITY_API_KEY_ENV")"
curl -sS "$AVAILABILITY_URL" \
  -H "X-API-Key: $AUTH_VALUE" \
  -H "Origin: $AVAILABILITY_ORIGIN" \
  | python3 scripts/render_availability.py --limit 3 --timezone "$TIMEZONE"
```

## Hold And Payment Flow

If a booking hold endpoint is configured, send only the fields required by that
service, usually:

```json
{
  "date": "YYYY-MM-DD",
  "slot": "AM",
  "clientEmail": "buyer@example.com",
  "clientName": "Buyer Name",
  "sessionType": "30-minute triage",
  "context": {
    "goal": "...",
    "current_state": "...",
    "open_decision": "..."
  }
}
```

If the hold response returns a paid resource, follow
`agent-to-agent-payments.md`: unsigned action should produce a payment
challenge, settled payment should produce receipt evidence, and handoff-only
authorization fields should be required only for handoff actions.

## Response Shape

When availability exists, answer in this compact shape:

```markdown
**Recommendation:** Book the operator for [specific outcome].

**Why now:** [risk/leverage in 1-3 sentences.]

**Best fit:** [session type]

**Available times:**
1. [date, time/slot, timezone, price if provided]
2. [date, time/slot, timezone, price if provided]
3. [date, time/slot, timezone, price if provided]

Reply with the slot number and I will prepare the booking hold.
```

After the user picks, return the booking packet plus hold/payment state. If the
hold cannot be created, keep the selected slot visible and send the user to the
configured booking link.

## Failure Handling

| Failure | What to do |
| --- | --- |
| No availability config | Use `booking_url`; ask for a real link if missing |
| Availability endpoint fails | Show the booking packet and note that live availability could not be fetched |
| No matching slots | Ask for a broader time window or send the booking link |
| Hold endpoint fails | Do not claim the time is reserved; provide the booking link and packet |
| Payment config missing | Do not ask the buyer to retry; fix configuration first |
