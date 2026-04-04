# SSH Info Overlay Key Reference

## Skillbox Client Overlay (preferred)

Add a `deploy` section to your client overlay at
`skillbox-config/clients/{client}/overlay.yaml`:

```yaml
    deploy:
      droplet_ssh: root@{server-ip}
      droplet_ip: {server-ip}
      ssh_key: ~/.ssh/{key-name}
      storage_root: /mnt/{volume-name}
      reverse_proxy_root: /opt/{proxy-path}

      services:
        my_api:
          label: My API
          repo_slug: org/my-api
          repo_root: ~/repos/my-api
          deploy_root: /opt/my-api
          compose_file: docker-compose.prod.yml
          compose_project: my-api
          compose_service: api
          compose_service_worker: worker    # optional
          internal_port: 8000
          domain: api.example.com
          health_url: https://api.example.com/health
          env_file: /opt/envs/my-api/prod.env
          db_volume: /mnt/{volume}/my-api/pgdata  # optional
```

The `status.sh` script reads the `deploy` section via `resolve_context.py` and
maps it to container filters, health checks, and SSH targets automatically.

## Legacy Shell Config (fallback)

If no overlay matches, `status.sh` falls back to `modes/config.sh`. Copy this
template and fill in your values. Keep the file untracked.

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
