---
mode_name: example-repo
cwd_match:
  - ~/repos/your-repo

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
---

# oss-doc-audit Mode Template

Use this as a reference when creating a new mode file at
`modes/<repo>.local.md`. The YAML frontmatter is parsed by
`scripts/select_mode.py` via the shared
`_shared/scripts/resolve_context.py` resolver.

Selection rules:

- the selector chooses the mode with the longest matching `cwd_match` prefix
- if multiple modes tie, selection is ambiguous and should be resolved by
  renaming or narrowing `cwd_match`
- `cwd_match` may be a single string or a list of paths

Real repo-specific truths (deprecated paths, baseline doc validators,
repo-specific drift markers) belong in the frontmatter so the audit does not
have to infer them. Keep free-form notes below the fence.

Clients that want to put this data in their skillbox overlay instead can add
an `oss_doc_audit:` section to `skillbox-config/clients/{client}/overlay.yaml`
— it will take precedence over local mode files.
