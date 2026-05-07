---
name: lube
description: Friction-removal retrospective for agent sessions. Use when the user says "lube", "$lube", "/lube", "friction", "several frictions were observed", "how do we unblock this", "avoid this in the future", or asks to prevent similar or adjacent blockers across future sessions.
---

# Lube

Several frictions were observed in our session that I believe could have been avoided. How do we unblock this and all similar or adjacent situations in the future?

Use the current session as evidence, then convert each friction into the smallest durable unblocker.

## Workflow

1. List the observed frictions as concrete moments. If details are missing, state the assumption instead of inventing evidence.
2. Classify the avoidable cause: missing skill trigger, unclear skill contract, absent API key, unavailable CLI/API/SDK, brittle manual step, missing environment setup, weak defaults, missing test, missing runbook, or missing automation.
3. Pick the smallest durable fix:
   - Use `$skill-issue` to create or improve a skill when the fix belongs in an agent workflow.
   - Set up or document credentials, environment variables, or one-time configuration when access blocked the work.
   - Check for an official CLI, API, or SDK when repeated browser/manual service work caused friction.
   - Add or improve a script when the same shell/API sequence is likely to recur.
   - Add a checklist, test, or repo doc when the prevention belongs next to the code.
4. Execute safe local fixes immediately. Ask only for secrets, paid external actions, destructive changes, or ambiguous policy decisions.
5. Close with what changed, what still needs human input, and how the change prevents adjacent failures.

## Output Shape

- Observed friction
- Root cause class
- Durable unblocker
- Action taken
- Remaining ask

Do not turn this into a blame postmortem. Do not stop at advice when a safe concrete fix can be made in the workspace.
