# Proof Checklist

Use this checklist before you call a finding “real.”

## For Route Drift

1. Open the doc page that names the route.
2. Open the active router or app registration file.
3. Confirm one of:
   - route is missing
   - route path differs
   - auth model differs
   - method differs
   - handler is a `501` stub

## For Payload Drift

1. Open the doc example request or response.
2. Open the active schema or serializer.
3. Confirm a concrete mismatch in:
   - field names
   - required fields
   - allowed values
   - nesting shape

## For Validator Findings

1. Run the validator.
2. Confirm whether it passes, fails, or crashes.
3. Open the validator source.
4. Verify whether it still targets the active stack or a deprecated tree.
5. If the validator now runs and reports drift, reclassify the remaining issue
   as content drift rather than validator failure.

## For Spec Drift

1. Open the checked-in API spec.
2. Compare it to `docs/manifest.json`.
3. Compare it to the active app surface or generated OpenAPI output.
4. Record whether the problem is stale content, generator drift, or both.

## For Workflow Doc Drift

1. Open the workflow guide.
2. List the workflow files, status checks, or commands it names.
3. Verify those files and names exist in the repo today.

## For Publishability Findings

1. Open the repo license file.
2. Open the root package manifest.
3. Open package-level manifests and READMEs.
4. Record any contradiction once per issue cluster.

## Loop Discipline

1. Mark completed queue items explicitly after each loop.
2. Recompute the score from the new baseline, not the original snapshot.
3. Do not keep deducting for a fixed validator just because it used to crash.
