# OSS Doc Audit Report Template

```markdown
Score: <n>/100

Fail Gates
- <gate> | none

Top Findings
- High: <problem>. Docs: <file>. Proof: <file>.
- High: <problem>. Docs: <file>. Proof: <file>.
- Medium: <problem>. Docs: <file>. Proof: <file>.

Ranked Cleanup Queue
1. <fix title>
   - Files: <docs>, <proof>
   - Why now: <reader impact>
   - Expected score recovery: +<n>
2. <fix title>
   - Files: <docs>, <proof>
   - Why now: <reader impact>
   - Expected score recovery: +<n>

Validation Run
- <command>: pass | fail
- <command>: pass | fail

Next Loop
- Fix items 1-2, rerun validators, rerun grade.
```
