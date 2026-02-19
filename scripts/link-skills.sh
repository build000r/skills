#!/usr/bin/env bash
set -euo pipefail

repo_root="${1:-$(pwd)}"
repo_root="$(cd "$repo_root" && pwd -P)"

targets=(
  "$HOME/.claude/skills"
  "$HOME/.codex/skills"
)

for target in "${targets[@]}"; do
  mkdir -p "$target"
done

linked=0
skipped=0

for skill_md in "$repo_root"/*/SKILL.md; do
  if [[ ! -f "$skill_md" ]]; then
    continue
  fi

  skill_dir="$(dirname "$skill_md")"
  skill_name="$(basename "$skill_dir")"

  for target in "${targets[@]}"; do
    dest="$target/$skill_name"

    if [[ -e "$dest" && ! -L "$dest" ]]; then
      printf 'skip: %s exists and is not a symlink\n' "$dest" >&2
      skipped=$((skipped + 1))
      continue
    fi

    ln -sfn "$skill_dir" "$dest"
    printf 'linked %s -> %s\n' "$dest" "$skill_dir"
    linked=$((linked + 1))
  done
done

# Clean up .bak dirs that have a symlinked replacement
cleaned=0
for target in "${targets[@]}"; do
  for bak in "$target"/*.bak; do
    [[ -d "$bak" ]] || continue
    base="${bak%.bak}"
    if [[ -L "$base" ]]; then
      rm -rf "$bak"
      printf 'cleaned %s (replaced by symlink)\n' "$bak"
      cleaned=$((cleaned + 1))
    fi
  done
done

printf '\nDone. %d links created/updated, %d skipped, %d .bak dirs cleaned.\n' "$linked" "$skipped" "$cleaned"
