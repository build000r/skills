# Source-copy creation and closeout

`scripts/copy_lifecycle.py` owns the run's source-copy ledger. Beads remains the
work authority. The helper creates only a linked worktree through native Git;
it never deletes a copy, merges source, rewrites refs or prunes a cache.

Initialize `COPY_LIFECYCLE.json` under the declared external artifact root as
shown in `SKILL.md`. Each copy has an owner Bead, a concrete purpose and an
observable release condition. These fields are required before native creation:

```bash
python3 "$COPY_LIFECYCLE" --ledger "$COPY_LEDGER" worktree-add \
  --id "$WORKER_BEAD" --path "$WORKTREE_PATH" --owner "$WORKER_BEAD" \
  --purpose "$WORKER_PURPOSE" --release-condition "$WORKER_RELEASE_CONDITION" \
  --revision "$ACCEPTED_REVISION"
```

The wrapper uses `git worktree add --detach`; root integration owns commits and
main. New source worktrees must be outside both the primary checkout and retained
artifact root. A failed creation leaves its custody entry visible. Use `register`
with the same metadata and `--kind clone|worktree|source-directory` for an existing
copy. It does not move or copy payload. Before dispatch, `dispatch-check` must
pass; it also detects new native worktrees missing from the ledger.

At harvest, run `inspect` and retain its JSON. Every entry includes an exact HEAD,
all-ref digest and a hexadecimal Git porcelain status including untracked and
ignored paths. Review semantic intent against current main and freshly verified
owner origin. Inventory alone is not a content decision. Resolve useful source
into main, reject or supersede it with evidence, or retain it for a real current
consumer with a release condition. Classify ignored payload before deleting any:
proof/source/state needs custody; dependencies/build outputs need a native owner
cleanup receipt. Do not archive regenerated dependencies to make retirement pass.

The first automatic admission is deliberately narrow: an already-incorporated,
clean linked worktree. Other semantic dispositions or independent clones stay
with the owning recovery lane. Do not weaken this gate to retire them.

For each candidate, write a decision keyed by its ledger ID:

```json
{
  "worker-bead": {
    "inventory_sha256": "SHA256 of canonical inspect copy object",
    "reviewed_at": "timezone-aware ISO timestamp",
    "verdict": "already-incorporated",
    "main_ref": "refs/heads/main",
    "comparison_revision": "exact current main OID",
    "source_review": {"conclusion": "already-incorporated", "evidence": []},
    "proof_custody": {"conclusion": "none", "evidence": []},
    "consumer_clearance": {"conclusion": "clear", "evidence": []},
    "origin_review": {"conclusion": "fresh-owner-origin", "evidence": []}
  }
}
```

Every `evidence` array must contain real `{"path": "absolute artifact path",
"sha256": "file SHA256"}` entries under the declared artifacts root, outside
the source copy. Empty arrays above are intentionally inadmissible. Source review
states what the original change intended and where main now implements it. Proof
custody uses `none` only after inventory proves no proof payload; otherwise use
`retained` with its checked independent custody paths. Consumer/origin review
must cover all-user processes, other agents/NTM, proof pins, service/config
references and fresh owner-origin containment; a same-user `/proc` scan alone is
insufficient. The helper checks that scan too, retaining active or inaccessible
consumers. A non-Linux host needs an owning native process-proof lane.

The decision expires after five minutes and binds exact source/ref inventory and
main. Canonical hashing is `json.dumps(copy, sort_keys=True,
separators=(",", ":")).encode()` followed by SHA256. Obtain a fresh admission:

```bash
python3 "$COPY_LIFECYCLE" --ledger "$COPY_LEDGER" admit-retirement \
  --id "$WORKER_BEAD" --decisions "$COPY_DECISIONS" > "$ADMISSION_RECEIPT"
```

Refresh realpath/Git identity, source/ignored classification, all refs/origin,
process fd/maps/cwd/exe, agent/proof consumers and custody immediately before the
native `git -C <owning-repo> worktree remove <exact-copy>` operation. Never pass
`--force` or switch to another deleter after refusal. Record the exact argv,
exit, path/registration state, retained hashes and measured footprint/df. Admission
is a local-main gate; it does not grant origin publication or deployment authority.

After native removal, replace that entry's decision with:

```json
{
  "verdict": "retired",
  "native_argv": ["git", "-C", "absolute owning repo", "worktree", "remove", "absolute copy"],
  "native_exit": 0,
  "admission_receipt": "absolute admission JSON path",
  "evidence": [{"path": "absolute admission JSON path", "sha256": "file SHA256"}]
}
```

Retain the native command receipt alongside admission as additional hashed
evidence. `closeout --decisions <file>` requires absent copy and registration,
an exact nonforced native argv/exit and bound admission. Present or unknown
copies remain visible with their owner and release condition. Exit 2 prevents a
false complete closeout; report it and keep its Bead open. No age-only deletion,
cron removal, whole-container archive or hidden unresolved-copy queue.
