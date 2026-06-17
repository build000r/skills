#!/usr/bin/env bash
set -euo pipefail

replace_copies=0
only_skill=""
repo_root=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --replace-copies)
      replace_copies=1
      shift
      ;;
    --skill)
      if [[ $# -lt 2 ]]; then
        printf 'error: --skill requires a skill name\n' >&2
        exit 2
      fi
      only_skill="$2"
      shift 2
      ;;
    --help|-h)
      cat <<'USAGE'
Usage: scripts/link-skills.sh [--replace-copies] [--skill NAME] [repo_root]

Links repo skills into ~/.claude/skills and ~/.codex/skills.

Options:
  --skill NAME        Link only one skill.
  --replace-copies   Move existing non-symlink installs to .bak.TIMESTAMP,
                     then create symlinks to the source repo.
USAGE
      exit 0
      ;;
    *)
      if [[ -n "$repo_root" ]]; then
        printf 'error: unexpected argument: %s\n' "$1" >&2
        exit 2
      fi
      repo_root="$1"
      shift
      ;;
  esac
done

repo_root="${repo_root:-$(pwd)}"
repo_root="$(cd "$repo_root" && pwd -P)"
backup_suffix="$(date +%Y%m%d%H%M%S)"

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
  if [[ -n "$only_skill" && "$skill_name" != "$only_skill" ]]; then
    continue
  fi

  for target in "${targets[@]}"; do
    dest="$target/$skill_name"

    if [[ -e "$dest" && ! -L "$dest" ]]; then
      if [[ "$replace_copies" -eq 1 ]]; then
        backup="$dest.bak.$backup_suffix"
        mv "$dest" "$backup"
        printf 'moved %s -> %s\n' "$dest" "$backup"
      else
      printf 'skip: %s exists and is not a symlink\n' "$dest" >&2
      skipped=$((skipped + 1))
      continue
      fi
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
