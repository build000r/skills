# SSH Info Overlay Key Reference

Add a `deploy` section under `client.context` in
`skillbox-config/clients/{client}/overlay.yaml`:

```yaml
version: 1
client:
  id: example
  label: Example
  default_cwd: ~/repos/my-api
  repos: []
  logs: []
  context:
    cwd_match:
      - ~/repos/my-api

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
          upstream_container: my-api        # concrete container or Docker network alias for health checks
          internal_port: 8000
          domain: api.example.com
          health_url: https://api.example.com/health
          env_file: /opt/envs/my-api/prod.env
          db_volume: /mnt/{volume}/my-api/pgdata  # optional

  checks: []
```

`scripts/status.sh` reads `client.context.deploy` through
`_shared/scripts/resolve_context.py` and maps it to container filters, health
checks, and SSH targets automatically.

If no overlay matches, the helper surfaces the shared legacy-transition error
with a suggested overlay stub. Do not create or rely on local shell config
fallback files.
