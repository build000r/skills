# Visual Picker

Load this reference when a visual direction, component treatment, layout, hierarchy, or “what looks best?” decision can be inspected in the real project.

## Trigger

Use a picker when the project can render the relevant surface and concrete alternatives would answer the question better than prose. Use a normal frontier question when the blocker is product logic or data, the user already specified one exact change, or a preview is impractical.

First search the repository and active skill inventory for a canonical picker skill, helper, or protocol. Delegate to it when present; retain Ask Cascade's ordering, decision-rights, label-matching, and cleanup rules.

## Fallback Protocol

When no canonical picker exists:

1. Inspect the current surface and identify the highest-impact visual decision.
2. Implement grounded variants in the existing source. Keep the current implementation as an explicitly labeled `(current)` option when useful.
3. Mark the comparison wrapper with `data-uidotsh-pick="Human readable label"`.
4. Mark each option with `data-uidotsh-option="Human readable option"`. Use layout-neutral wrappers such as the `contents` class where supported so comparison scaffolding does not alter layout.
5. Display exactly one option at a time and hide the others according to the project's established mechanism.
6. Use the repository's framework-native and security-appropriate picker integration. If none exists, inspect and approve the mechanism before adding any remote script; never inject a remote picker blindly.
7. Let the user inspect the variants, then ask one structured preference question whose labels exactly match the rendered option labels.
8. After selection, retain the chosen implementation and remove unselected variants, picker attributes, toolbar/script integration, and other comparison scaffolding unless another round is requested.

If the existing project explicitly uses the `ui.sh` protocol, its toolbar source is `https://ui.sh/ui-picker.js`; preserve that convention rather than inventing a second protocol. Treat introducing it to a project that does not already use it as a security-relevant integration choice requiring inspection.

## Verification

- The rendered alternatives are grounded in the real surface.
- Comparison scaffolding does not change the layout being judged.
- Only one option is visible at a time when that is the established protocol.
- Rendered and structured-question labels match exactly.
- The chosen source remains functional after cleanup.
- No unselected variant or picker integration remains unless requested.
