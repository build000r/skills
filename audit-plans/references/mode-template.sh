# Copy to modes/config.sh and customize for your workspace.
# This file is a template reference and should remain generic.

# --- Required ---

# Top-level catalog root.
export PLAN_ROOT="/absolute/path/to/plan-catalog"

# Plan discovery directories (space-separated).
export PLAN_DIRS="${PLAN_ROOT}/released ${PLAN_ROOT}/planned"

# --- Auto-derived (override only if your layout is non-standard) ---
# These are discovered automatically from PLAN_DIRS when not set:
#   RELEASED_INDEX - first INDEX.md in a dir named "released"
#   PLANNED_INDEX  - first INDEX.md in a dir named "planned"
#   SESSION_INDEX  - ${PLAN_ROOT}/session-plans/INDEX.md if it exists
#   SESSION_PLAN_GLOB - ${PLAN_ROOT}/session-plans/*.md if dir exists

# Uncomment to override auto-detection:
# export RELEASED_INDEX="${PLAN_ROOT}/released/INDEX.md"
# export PLANNED_INDEX="${PLAN_ROOT}/planned/INDEX.md"

# --- Session plans (only if your catalog uses them) ---
# export SESSION_INDEX="${PLAN_ROOT}/session-plans/INDEX.md"
# export SESSION_PLAN_GLOB="${PLAN_ROOT}/session-plans/*.md"

# --- Optional ---

# Diagram validation command.
# export MERMAID_VALIDATE_CMD='cd "$PLAN_ROOT" && npm run docs:validate-mermaid'

# Focus-mode repo relationships.
# Format: one mapping per line, `primary=related1,related2`
# export FOCUS_RELATED_REPOS=$'app-api=app-web,ops-console\napp-web=app-api'
