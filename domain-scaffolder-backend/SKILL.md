---
name: domain-scaffolder-backend
description: Scaffold backend domain code from an existing plan with a TDD-first workflow that writes tests before implementation. Use for "scaffold the backend" or "implement the backend for {slice}" after domain-planner finishes a slice plan; not for frontend work or general backend tasks outside domain slices.
license: MIT
---

# Domain Scaffolder - Backend

Compatibility wrapper for the canonical `domain-scaffolder` skill.

## Surface Lock

This wrapper always runs the canonical scaffolder with:

```text
surface=backend
```

Use this wrapper when the request is explicitly backend-only:

- "scaffold the backend"
- "implement the backend for {slice}"
- backend/router/model/service/migration work after `domain-planner`

Do not use this wrapper for frontend work or mixed backend+frontend runs.

## Canonical Skill

Immediately open and apply:

```text
../domain-scaffolder/SKILL.md
```

Then continue with the backend surface rules from that skill.

## Mode Compatibility

The canonical private mode store now lives under:

```text
../domain-scaffolder/modes/
```

This wrapper's local `modes/` path is a compatibility layer that preserves old
backend-local filenames. If a mode file exists here, it resolves to the canonical
store. Use the canonical skill's mode-selection rules, but keep `surface=backend`
fixed for all filtering.

## Backend-Specific Rules

- Tests before implementation
- Follow the mode's backend convention files before writing code
- Generate service tests, route tests, models, schemas, repository, service, router, then migration
- Register the router before closeout
- Run the backend validation commands from the active mode

## Closeout

Return the canonical completion contract with `surface=backend`, then hand off to
`domain-reviewer`. If the slice also includes frontend work, direct the user to
`domain-scaffolder-frontend` next.
