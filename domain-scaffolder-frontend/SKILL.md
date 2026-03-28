---
name: domain-scaffolder-frontend
description: Scaffold frontend code from an existing plan after loading project-specific UI patterns. Use for "scaffold the frontend" or "implement the frontend for {slice}" after backend scaffolding, and not for backend work or general frontend changes outside domain slices.
license: MIT
---

# Domain Scaffolder - Frontend

Compatibility wrapper for the canonical `domain-scaffolder` skill.

## Surface Lock

This wrapper always runs the canonical scaffolder with:

```text
surface=frontend
```

Use this wrapper when the request is explicitly frontend-only:

- "scaffold the frontend"
- "implement the frontend for {slice}"
- hooks/components/widgets/page work after backend scaffolding

Do not use this wrapper for backend work or mixed backend+frontend runs.

## Canonical Skill

Immediately open and apply:

```text
../domain-scaffolder/SKILL.md
```

Then continue with the frontend surface rules from that skill.

## Mode Compatibility

The canonical private mode store now lives under:

```text
../domain-scaffolder/modes/
```

This wrapper's local `modes/` path is a compatibility layer that preserves old
frontend-local filenames. If a mode file exists here, it resolves to the canonical
store. Use the canonical skill's mode-selection rules, but keep `surface=frontend`
fixed for all filtering.

## Frontend-Specific Rules

- Load `patterns_reference` before generating any components
- Generate types, API layer, hooks, components, then widget/page wrappers
- Use the mode's library primitives and data-fetching patterns
- Run the frontend validation commands from the active mode

## Closeout

Return the canonical completion contract with `surface=frontend`, then hand off to
`domain-reviewer`.
