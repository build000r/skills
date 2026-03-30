---
mode_name: example-prod
cwd_match:
  - ~/repos/your-api
  - ~/repos/your-frontend
  - <ssh-dev-root>/your-api

repo_slug_api: your-org/your-api
repo_slug_frontend: your-org/your-frontend

repo_root_api: ~/repos/your-api
repo_root_frontend: ~/repos/your-frontend
repos_root: ~/repos

droplet_ssh: ssh-target-placeholder
droplet_ip: <server-ip>

deploy_root_api: /opt/your-api
deploy_root_frontend: /opt/your-frontend
compose_project_api: your-api
compose_service_api: api
compose_service_worker: worker

health_url_api: https://api.example.com/health
health_url_frontend: https://app.example.com/health

frontend_pages_project: example-pages-project
frontend_pages_origin: example-pages-project.pages.dev
worker_config_path: workers/frontdoor/wrangler.toml
reverse_proxy_root: /opt/reverse-proxy
backup_root: /mnt/block-storage/example
storage_root: /mnt/block-storage
package_name: your-package-name
package_registry: npm
---

# Deploy Mode Template

Copy this file to `modes/<name>.md` and replace placeholders with real values.
`health_url_frontend` can be any lightweight public smoke URL for the frontend,
not necessarily `/health`.

Guidelines:

- keep all real hosts, repo names, and filesystem paths in the mode file
- prefer one mode per deploy surface or environment
- let `cwd_match` point at the repos or SSH-dev roots where this mode should activate
- add extra keys freely; `scripts/select_mode.py` flattens nested YAML into `MODE_*` exports

Optional keys are fine. If a project does not publish a package or does not use
Pages, leave those placeholders out in the real local mode.

Selection rules:

- the selector chooses the mode with the longest matching `cwd_match`
- if multiple modes tie, selection is ambiguous and should be resolved by the user
