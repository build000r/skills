# Plan Quality Review

Use one independent review of the requested plan against its acceptance criteria
and the relevant dimensions in [plan-quality-rubric.md](plan-quality-rubric.md).
Combine architectural review and completeness checks when one reviewer can cover
both. Honor the selected model and substrate, including tracked native Codex
agents. No external tool, second provider or additional review round is required
merely by this workflow.

The reviewer reads the existing plan, implementation constraints and applicable
standards. Check contract consistency, failure modes, ownership, dependencies,
validation, scope and the primary user's intended outcome. Auth, payments and
identity plans must reuse the configured canonical packages and identify real
capability gaps. Changes to production data require an appropriate transition
and recovery plan; do not add unrequested compatibility layers.

Return a concrete PASS/FAIL verdict, required checks, and severity-ranked
material findings with location, reason and smallest repair. Use a numerical
rubric only when requested; an optional score never substitutes for acceptance.
A requested threshold remains binding together with the actual criteria.

Repair material findings within the authorized scope. Recheck affected findings
and any new risks caused by the repair; reuse reviewer context where helpful.
Stop when acceptance is demonstrated. Do not schedule clean re-reviews, generic
perfect-score loops or an automatic hardening phase. If the same repair makes no
progress, report the concrete unresolved decision or external dependency.

Keep results in the existing task store and tracked result channel. A temporary
report is allowed for an actual parser/consumer; update its current verdict
instead of appending history, then remove obsolete scratch after collection.
Do not create another plan, invocation history, or score report by default.
Once the plan passes and user direction is already clear, reuse or create the
execution tasks. Render WORKGRAPH.md only when a human or tool needs that view.
