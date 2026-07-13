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
      - ~/repos/your-package
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
          release:
            command: make release
            gate: make verify
            ref_policy: origin/main
            transport: registryless
            credential_probe: ssh ssh-target-placeholder docker ps
            manifest_dir: /var/tmp/your-api-release/manifests
            remote_manifest_dir: /opt/your-api/releases
            break_glass_workflow: .github/workflows/deploy.yml

        frontend:
          repo_root: ~/repos/your-frontend
          mode_name: your-frontend
          surface: pages_edge
          repo_slug: your-org/your-frontend
          project: example-pages-project
          pages_origin: example-pages-project.pages.dev
          production_branch: main
          production_domain: https://www.example.com
          production_aliases:
            - https://example.com
          canonical_redirect:
            from: https://example.com
            to: https://www.example.com
          health_url: https://www.example.com/health
          wrangler_config: wrangler.toml
          ci_workflow: .github/workflows/deploy-pages.yml
          # Optional manual break-glass only; local auth lives under release.
          required_github_secrets:
            - CLOUDFLARE_API_TOKEN
            - CLOUDFLARE_ACCOUNT_ID
          release:
            command: make release
            gate: make verify
            ref_policy: origin/main
            transport: provider_cli
            credential_probe: npx wrangler whoami
            build_identity_path: /build-meta.json
            manifest_dir: /var/tmp/your-frontend-release/manifests
            break_glass_workflow: .github/workflows/deploy-pages.yml
          cli:
            auth: cd ~/repos/your-frontend && npx wrangler whoami
            deploy: cd ~/repos/your-frontend && npx wrangler pages deploy --project-name example-pages-project --branch main
            deployments: cd ~/repos/your-frontend && npx wrangler pages deployment list --project-name example-pages-project
          smoke:
            - "curl -fsSI https://example.com/ | grep -i 'location: https://www.example.com/'"
            - "curl -fsS https://www.example.com/health"
          browser_cors:
            frontend_origins:
              - https://www.example.com
              - https://example.com
            api_origins:
              - https://api.example.com
            preflight_route: /api/auth/login
            preflight_method: POST
            preflight_headers:
              - content-type
              - authorization
              - x-api-key

      packages:
        cli:
          repo_root: ~/repos/your-package
          mode_name: your-package
          surface: package_publish
          repo_slug: your-org/your-package
          package_url: https://registry.example.com/your-package
          release:
            command: make release
            gate: make verify
            ref_policy: signed_tag
            transport: registry_cli
            credential_probe: registry-cli whoami
            manifest_dir: /var/tmp/your-package-release/manifests
            break_glass_workflow: .github/workflows/publish-manual.yml

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
- local self-release keys: `release.command`, `release.gate`,
  `release.ref_policy`, `release.transport`, `release.credential_probe`,
  `release.manifest_dir`, `release.remote_manifest_dir`,
  `release.build_identity_path`, `release.break_glass_workflow`
- Pages/edge target keys: `project`, `pages_origin`, `production_branch`,
  `production_domain`, `production_aliases`, `canonical_redirect`,
  `wrangler_config`, optional break-glass-only `required_github_secrets`, `cli`, `smoke`
- package/app-store target keys: package or app identity URL, release version or
  build-number source, signing/credential probe, processing-state command, and
  the shared `release.*` contract
- Optional browser API keys: `browser_cors.frontend_origins`,
  `browser_cors.api_origins`, `browser_cors.preflight_route`,
  `browser_cors.preflight_method`, `browser_cors.preflight_headers`

Selection rules:

- the resolver chooses the overlay with the longest matching `cwd_match`
- `select_mode.py` then chooses the deploy target whose `repo_root` is the most
  specific prefix match for the current cwd
- if no overlay matches, the selector prints a legacy-transition probe plus a
  valid overlay stub instead of falling back to any private legacy config files
