version: 1
client:
  id: example
  label: Example
  default_cwd: ~/repos/your-api
  repos: []
  logs: []
  context:
    cwd_match:
      - ~/repos/your-api
      - ~/repos/your-frontend
      - <ssh-dev-root>/your-api

    deploy:
      droplet_ssh: ssh-target-placeholder
      droplet_ip: <server-ip>
      ssh_key: tailscale
      reverse_proxy_root: /opt/reverse-proxy
      storage_root: /mnt/block-storage

      services:
        api:
          repo_root: ~/repos/your-api
          mode_name: your-api
          surface: docker_compose
          repo_slug: your-org/your-api
          deploy_root: /opt/your-api
          compose_file: deploy/docker-compose.prod.yml
          compose_project: your-api
          compose_service: api
          health_url: https://api.example.com/health
          ci_workflow: .github/workflows/deploy.yml

        frontend:
          repo_root: ~/repos/your-frontend
          mode_name: your-frontend
          surface: pages_edge
          repo_slug: your-org/your-frontend
          frontend_pages_project: example-pages-project
          frontend_pages_origin: example-pages-project.pages.dev
          health_url: https://app.example.com/health
          worker_config_path: workers/frontdoor/wrangler.toml

  checks: []

# Deploy Overlay Key Reference

Use this as a reference when creating a client overlay at
`skillbox-config/clients/{client}/overlay.yaml`.

Guidelines:

- keep real hosts, repo names, filesystem paths, workflow files, and health
  URLs in the client overlay
- put `cwd_match` under `client.context`
- put deploy data under `client.context.deploy`
- use a shared deploy block with `services` and/or `packages` when one client
  covers multiple repos
- `scripts/select_mode.py` narrows that shared deploy block to the current repo
  and emits flattened `MODE_*` vars

Common keys:

- shared deploy keys: `droplet_ssh`, `droplet_ip`, `ssh_key`,
  `reverse_proxy_root`, `storage_root`
- target keys: `mode_name`, `surface`, `repo_root`, `repo_slug`,
  `deploy_root`, `compose_file`, `compose_project`, `compose_service`,
  `health_url`, `ci_workflow`

Selection rules:

- the resolver chooses the overlay with the longest matching `cwd_match`
- `select_mode.py` then chooses the deploy target whose `repo_root` is the most
  specific prefix match for the current cwd
- if no overlay matches, the selector prints a legacy-transition probe plus a
  valid overlay stub instead of falling back to any private legacy config files
