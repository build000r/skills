# SSH Info Mode Template

Copy this into `modes/config.sh` and replace the placeholders with your real
values. Keep the file untracked.

```bash
# Optional: when set, prod checks are wrapped in SSH.
STATUS_REMOTE_SSH="ssh-target-placeholder"

# Regex used to filter docker ps output for the services you care about.
PROD_CONTAINER_FILTER='(NAMES|api|worker|db|redis)'

# "Label|URL" pairs for known local or public health endpoints.
LOCAL_HEALTH_CHECKS=(
  "Frontend|http://localhost:3000/health"
  "Backend|http://localhost:8000/health"
)

# "Label|Container|URL" triples for container-local health checks.
PROD_HEALTH_CHECKS=(
  "Backend API|backend-api-1|http://localhost:8000/health"
  "Worker|worker-1|http://localhost:8010/health"
)
```

Use shell-safe values. If a URL or label contains spaces, quote the whole row.
