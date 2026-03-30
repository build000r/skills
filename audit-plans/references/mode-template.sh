# Copy to modes/config.sh and customize for your workspace.
# This file is a template reference and should remain generic.

# Top-level catalog root.
export PLAN_ROOT="/absolute/path/to/plan-catalog"

# Index files.
export RELEASED_INDEX="${PLAN_ROOT}/released/INDEX.md"
export PLANNED_INDEX="${PLAN_ROOT}/planned/INDEX.md"
export SESSION_INDEX="${PLAN_ROOT}/session-plans/INDEX.md"

# Plan discovery.
export PLAN_DIRS="${PLAN_ROOT}/released ${PLAN_ROOT}/planned"
export SESSION_PLAN_GLOB="${PLAN_ROOT}/session-plans/*.md"

# Optional diagram validation.
export MERMAID_VALIDATE_CMD='cd "$PLAN_ROOT" && npm run docs:validate-mermaid'

# Optional focus-mode repo relationships.
# Format: one mapping per line, `primary=related1,related2`
export FOCUS_RELATED_REPOS=$'app-api=app-web,ops-console\napp-web=app-api'
