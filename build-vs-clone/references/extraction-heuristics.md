# Extraction Heuristics

Use this when the question is not only "where should this go?" but also
"should this be lifted out into a more reusable/shared home?"

## Extraction Outcomes

- `LEAVE IN PLACE`
- `EXTRACT UP`
- `SHARED PACKAGE`
- `SKILL`
- `HELPER REPO`
- `NEW REPO`

## What Counts As A Good Extraction Signal

- the same concept appears in multiple repos or workflows
- the same prompt/process keeps being re-explained manually
- multiple repos need the same API client, schema adapter, or utility
- a repo is accumulating obviously generic helper code that is not domain-owned
- one repo is acting as the natural higher-level owner already

## Weak Signals

- "this file looks reusable"
- "I might use this later"
- one-off copy/paste pressure without stable shared concepts
- abstract elegance without present maintenance pain

## Destination Guide

Choose `LEAVE IN PLACE` when:

- the capability is still tightly coupled to one domain
- extracting would create a premature abstraction
- the second consumer is hypothetical, not real

Choose `EXTRACT UP` when:

- the capability already serves multiple sibling surfaces
- there is a natural parent/shared repo or monorepo for it
- the extracted boundary would stay legible

Choose `SHARED PACKAGE` when:

- this is code with a stable API surface
- an existing repo is already the right shared home
- packaging inside that repo is cleaner than a new top-level repo

Choose `SKILL` when:

- the reusable part is mostly workflow, operator knowledge, prompts, or review
  logic
- correctness depends more on process than on a runtime library
- the value is cross-project and agent-facing

Choose `HELPER REPO` when:

- the utility is real and reusable
- it is too generic for any current product/domain repo
- it is too small to justify a broader product repo

Choose `NEW REPO` when:

- the extraction creates a durable new product/domain boundary
- ownership in every existing repo would remain muddy
- independent release/versioning/deploy cadence matters

## "Extract Up" Rule

When more than one target is plausible, prefer the nearest stable shared layer:

1. current repo package/module
2. existing monorepo/shared repo
3. skills/tooling repo
4. helper repo
5. new top-level repo

Do not skip levels without a concrete reason.

## Evidence To Inspect

- current repo docs and manifests
- sibling repo docs/manifests where reuse is suspected
- repeated scripts, prompts, API clients, schemas, or helper utilities
- operator workflows that recur across projects
- whether the proposed shared home already exists and is actively used
