# Dev Sanity Mode Template

Copy this into `modes/config.sh`, replace the placeholders, and keep the file
untracked.

Every section is optional. Delete groups that do not apply to your local stack.
Keep tracked files generic and put all real repo names, ports, container names,
and URLs here instead.

```bash
# shellcheck shell=bash

DEV_SANITY_REPOS=(
  "api|$HOME/path/to/api-repo"
  "web|$HOME/path/to/web-repo"
)

DEV_SANITY_ENV_FILES=(
  "api env|$HOME/path/to/api-repo/.env"
  "web env|$HOME/path/to/web-repo/.env.local"
)

DEV_SANITY_CONTAINERS=(
  "api container|local-api-1"
  "postgres|local-postgres-1"
)

DEV_SANITY_HEALTH_URLS=(
  "api|http://localhost:8000/health"
  "web|http://localhost:3000/health"
)
```
