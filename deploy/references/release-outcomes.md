# Release Outcomes

Keep the native process result separate from the effect it produced. Report one
of these states, using observed evidence rather than inference from exit status:

| Result | Meaning |
| --- | --- |
| `not_started` | Preflight stopped execution; no release command started. |
| `running` | The identified native run is still executing. |
| `failed_before_activation` | Evidence establishes failure before target activation. |
| `activated_unverified` | Activation occurred; behavior or exact artifact/SHA proof is missing or failed. |
| `recovery_incomplete` | Expected release and behavior are proven; required rollback eligibility or recovery evidence is missing. |
| `verified` | Exact requested release, behavior, state, artifact record, and required recovery evidence all pass. |
| `outcome_unknown` | Activation or native completion cannot yet be established. |

Use this four-field closeout, including on failure:

```text
Native: <command / run reference>; <exit code, running, or unknown>
Result: <state>; desired <full SHA>; observed <full SHA or unknown>
Evidence: behavior <pass/fail/unknown>; state <pass/fail/unknown>; recovery <eligible/proven/missing/unknown>; <receipt references>
Next: <one safe action, or none>
```

Verification does not erase a nonzero native exit. Keep the fault visible and
repair its cause before the next release. A lock proves serialization only;
it does not make a repeated release idempotent. Use a repo-native inspect or
reconcile operation only when its documented contract permits it; never invent
a flag or rerun activation to recover a missing receipt.

## Three Cold-Start Cases

1. **Nonzero after activation, missing rollback receipt.** Behavior and full SHA
   match, but recovery evidence is absent. Report `recovery_incomplete`, retain
   the nonzero exit, and inspect the existing run/previous release receipt. Do
   not build or deploy again merely to turn the command green.
2. **Timeout with no confirmed activation state.** Report `outcome_unknown`,
   native exit/completion unknown, and inspect the same run reference and target.
   A lost client connection does not establish failure or safe retry eligibility.
3. **Exit zero and HTTP 200, wrong SHA.** Report `activated_unverified`, behavior
   unknown unless the changed flow was proven, and state fail with both SHAs. Inspect target identity;
   do not label the release verified or automatically repeat activation.

For `running`, keep the run reference and name the next observation. For a
terminal failure or unknown outcome, return useful evidence promptly rather than
waiting indefinitely for all checks to pass. An observation failure is not a
new authorization to restart, roll back, or deploy.
