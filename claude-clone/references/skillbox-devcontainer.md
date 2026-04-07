# Using skillbox as the Dev Container

`claude-clone` runs all build, test, and benchmark work for ported code
inside the sibling `skillbox` repo's main workspace container. The host
stays clean; the container has the opinionated toolchain.

## Why skillbox

- One Docker workspace with a stable package surface — compilers, linters,
  fuzzers, hyperfine, ripgrep, jq, gh, language runtimes — already installed.
- Bind mounts the parent monoserver root, so the target repo and any
  upstream clones are visible inside the box at the same paths as on the host.
- Durable `home/.claude` and `home/.codex` so a follow-up agent session
  picks up where the previous one stopped.
- Client overlays declare which extra packages or repos a given client
  needs — the right surface activates automatically.

This means a clone never needs `brew install` or a host-level toolchain.
If a needed tool is missing from the box, add it to skillbox (or the
relevant client overlay), not to the host.

## Locating skillbox

Skillbox is expected as a sibling of the target repo's parent. The
canonical resolution order:

1. `$SKILLBOX_WORKSPACE_ROOT` if set
2. `../skillbox` relative to the target repo
3. `~/repos/opensource/skillbox` as a last fallback

If none of those resolve to a directory containing `Makefile` and
`docker-compose.yml`, stop and tell the user — do not silently fall back
to host tooling.

## Standard Entry Sequence

From the resolved skillbox directory:

```bash
make doctor          # validate outer drift (host-side manifest)
make up              # start the workspace container if not running
make shell           # exec into the workspace
```

Inside the container, the target repo is mounted at the same path it has
on the host (typically under `/monoserver/...`). Run the port's build,
test, and bench commands from there.

For one-shot commands without an interactive shell:

```bash
docker compose exec workspace bash -lc "<command>"
```

## Validating the Port

Inside the container, at minimum:

1. Build the target repo with its native build command.
2. Run only the test(s) that exercise the ported code (not the full suite).
3. If the upstream is performance-sensitive, run `hyperfine` on the ported
   path against a baseline and record the result in the output report.

If a build or test fails because a tool is missing from the container,
that is a skillbox issue, not a port issue — fix it there before
continuing.

## What NOT to do

- Do not run language-specific package managers (`pip`, `npm`, `cargo`,
  `go install`) on the host to support the clone. Use the container.
- Do not vendor toolchain into the target repo to avoid the container.
  The container is the toolchain.
- Do not commit container-only artifacts (built binaries, `.venv`, etc.)
  back to the target repo. The container's view of the repo is the same
  filesystem — respect the target's `.gitignore`.
- Do not edit skillbox's `Dockerfile` to add a tool just for one clone
  unless the user asks. Prefer a client overlay or a one-off `apt install`
  inside the running container, and report the divergence in the output.

## Reporting

In the final output, list the exact skillbox commands the user can rerun
to revalidate, e.g.:

```
cd ../skillbox && make shell
# inside container:
cd /monoserver/<target-repo>
<build cmd>
<test cmd>
```

The user should be able to re-run the validation in under a minute.
