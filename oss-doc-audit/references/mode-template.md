version: 1
client:
  id: example
  label: Example
  default_cwd: ~/repos/your-repo
  repos: []
  logs: []
  context:
    cwd_match:
      - ~/repos/your-repo

    oss_doc_audit:
      mode_name: your-repo
      active_codebase_path: path/to/active/code

      deprecated_paths:
        - path/to/deprecated/code

      public_docs_surface:
        - README.md
        - CONTRIBUTING.md
        - docs/
        - .github/

      baseline_commands:
        - <repo-native doc validator>
        - <manifest or route parity command>
        - <package docs validator>

      drift_markers:
        - deprecated route roots
        - old stack names
        - removed workflow files
        - wrong deploy file names
        - license mismatches

  checks: []

# OSS Doc Audit Overlay Key Reference

Add repo-specific audit truths to `client.context.oss_doc_audit` inside
`skillbox-config/clients/{client}/overlay.yaml`.

Guidelines:

- keep `cwd_match` under `client.context`
- keep `oss_doc_audit` under `client.context`
- store repo-specific truths here so the audit does not have to infer them every
  run
- use `mode_name` for the emitted `MODE_NAME`
- keep `active_codebase_path` repo-relative when the audit should open paths
  under the matched repo root

Selection rules:

- the resolver chooses the overlay with the longest matching `cwd_match` prefix
- `scripts/select_mode.py` emits flattened `MODE_*` vars from
  `client.context.oss_doc_audit`
- if a matching overlay lacks `oss_doc_audit`, the selector fails with a
  section-missing error instead of searching for local fallback files
