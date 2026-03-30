#!/usr/bin/env python3
"""
Quick validation script for skills - validates structure and content
"""

import sys
import re
import yaml
from pathlib import Path
from lib.skill_bundle_filter import iter_included_skill_files

def validate_skill(skill_path, strict=False):
    """
    Validate a skill directory.

    Args:
        skill_path: Path to skill directory
        strict: If True, treat warnings as errors

    Returns:
        (valid, message) tuple
    """
    skill_path = Path(skill_path).resolve()
    warnings = []

    # Check SKILL.md exists
    skill_md = skill_path / 'SKILL.md'
    if not skill_md.exists():
        return False, "SKILL.md not found"

    # Read and validate frontmatter
    content = skill_md.read_text()
    if not content.startswith('---'):
        return False, "No YAML frontmatter found"

    # Extract frontmatter
    match = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
    if not match:
        return False, "Invalid frontmatter format"

    frontmatter_text = match.group(1)
    body = content[match.end():]

    # Parse YAML frontmatter
    try:
        frontmatter = yaml.safe_load(frontmatter_text)
        if not isinstance(frontmatter, dict):
            return False, "Frontmatter must be a YAML dictionary"
    except yaml.YAMLError as e:
        return False, f"Invalid YAML in frontmatter: {e}"

    # Define allowed properties
    ALLOWED_PROPERTIES = {'name', 'description', 'type', 'license', 'allowed-tools', 'metadata'}

    # Check for unexpected properties (excluding nested keys under metadata)
    unexpected_keys = set(frontmatter.keys()) - ALLOWED_PROPERTIES
    if unexpected_keys:
        return False, (
            f"Unexpected key(s) in SKILL.md frontmatter: {', '.join(sorted(unexpected_keys))}. "
            f"Allowed properties are: {', '.join(sorted(ALLOWED_PROPERTIES))}"
        )

    # Check required fields
    if 'name' not in frontmatter:
        return False, "Missing 'name' in frontmatter"
    if 'description' not in frontmatter:
        return False, "Missing 'description' in frontmatter"

    # Extract name for validation
    name = frontmatter.get('name', '')
    if not isinstance(name, str):
        return False, f"Name must be a string, got {type(name).__name__}"
    name = name.strip()
    if name:
        # Check naming convention (hyphen-case: lowercase with hyphens)
        if not re.match(r'^[a-z0-9-]+$', name):
            return False, f"Name '{name}' should be hyphen-case (lowercase letters, digits, and hyphens only)"
        if name.startswith('-') or name.endswith('-') or '--' in name:
            return False, f"Name '{name}' cannot start/end with hyphen or contain consecutive hyphens"
        # Check name length (max 64 characters per spec)
        if len(name) > 64:
            return False, f"Name is too long ({len(name)} characters). Maximum is 64 characters."

    # Extract and validate description
    description = frontmatter.get('description', '')
    if not isinstance(description, str):
        return False, f"Description must be a string, got {type(description).__name__}"
    description = description.strip()
    if description:
        # Check for angle brackets
        if '<' in description or '>' in description:
            return False, "Description cannot contain angle brackets (< or >)"
        # Check description length (max 1024 characters per spec)
        if len(description) > 1024:
            return False, f"Description is too long ({len(description)} characters). Maximum is 1024 characters."
        # Check minimum description length
        if len(description) < 50:
            warnings.append(f"Description is short ({len(description)} chars). Consider adding trigger phrases.")

    # Check for TODO markers in body (indicates incomplete skill)
    todo_matches = re.findall(r'\[TODO[:\]].{0,50}', body, re.IGNORECASE)
    if todo_matches:
        return False, f"Incomplete skill: found TODO marker(s): {todo_matches[0]}..."

    # Privacy scan — check all tracked files for personal/business info leaks
    PRIVACY_PATTERNS = [
        (r'/Users/\w+/', "Hardcoded user path"),
        (r'/root/dev/', "Hardcoded server path"),
        (r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', "IP address"),
        (r'(?:api[_-]?key|token|password|secret)\s*[=:]\s*["\'][^"\']{8,}', "Possible secret/credential"),
        (r'\?fpr=|\?ref=|\?affiliate=', "Referral/affiliate link"),
    ]
    for file_path in iter_included_skill_files(skill_path):
        rel = str(file_path.relative_to(skill_path))
        # Avoid self-referential false positives from validator regex definitions.
        if rel == 'scripts/quick_validate.py':
            continue
        try:
            text = file_path.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            continue
        for pattern, label in PRIVACY_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                sample = matches[0] if isinstance(matches[0], str) else str(matches[0])
                warnings.append(f"Privacy: {label} in {rel} ({sample[:40]}...)")

    # Check SKILL.md line count (recommended max 500)
    line_count = len(content.splitlines())
    if line_count > 500:
        warnings.append(f"SKILL.md has {line_count} lines (recommended max: 500). Consider splitting into references/.")

    # Check for empty resource directories
    for resource_dir in ['scripts', 'references', 'assets']:
        dir_path = skill_path / resource_dir
        if dir_path.exists() and dir_path.is_dir():
            files = [f for f in dir_path.iterdir() if not f.name.startswith('.') and not f.name == '__pycache__']
            if not files:
                warnings.append(f"Empty directory: {resource_dir}/ (delete if unused)")

    # Build result message
    if strict and warnings:
        return False, f"Strict mode failed: {warnings[0]}"

    if warnings:
        return True, f"Skill is valid with warnings:\n  - " + "\n  - ".join(warnings)

    return True, "Skill is valid!"

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python quick_validate.py <skill_directory> [--strict]")
        print("\nOptions:")
        print("  --strict    Treat warnings as errors")
        sys.exit(1)

    skill_path = sys.argv[1]
    strict = '--strict' in sys.argv

    valid, message = validate_skill(skill_path, strict=strict)
    print(message)
    sys.exit(0 if valid else 1)
