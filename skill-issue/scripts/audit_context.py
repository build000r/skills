#!/usr/bin/env python3
"""
Context Audit - Scan Claude environment and generate context registry.

Usage:
    audit_context.py [--scan-root <path>] [--output <path>] [--report-only]

Examples:
    audit_context.py                              # Scan ~/repos, write to ~/.claude/context/
    audit_context.py --scan-root ~/projects       # Custom scan root
    audit_context.py --report-only                # Print report without writing registry
    audit_context.py --scan-root ~/repos --scan-root ~/work  # Multiple scan roots
"""

import sys
import os
from pathlib import Path

# Add parent dir to path for lib imports
sys.path.insert(0, str(Path(__file__).parent))

from lib.scanner import scan_global_config, scan_projects
from lib.reporter import format_audit_report, detect_issues
from lib.registry import write_registry


def main():
    args = sys.argv[1:]

    # Parse arguments
    scan_roots = []
    output_dir = os.path.expanduser("~/.claude/context")
    report_only = False

    i = 0
    while i < len(args):
        if args[i] == "--scan-root" and i + 1 < len(args):
            scan_roots.append(args[i + 1])
            i += 2
        elif args[i] == "--output" and i + 1 < len(args):
            output_dir = args[i + 1]
            i += 2
        elif args[i] == "--report-only":
            report_only = True
            i += 1
        elif args[i] in ("-h", "--help"):
            print(__doc__)
            sys.exit(0)
        else:
            print(f"Unknown argument: {args[i]}")
            print("Usage: audit_context.py [--scan-root <path>] [--output <path>] [--report-only]")
            sys.exit(1)

    # Default scan root
    if not scan_roots:
        scan_roots = [os.path.expanduser("~/repos")]

    # Run scan
    global_config = scan_global_config()
    projects = scan_projects(scan_roots)
    issues = detect_issues(global_config, projects)

    # Print report
    report = format_audit_report(global_config, projects, issues)
    print(report)

    # Write registry
    if not report_only:
        write_registry(output_dir, global_config, projects)
        print(f"Registry written to {output_dir}/")
    else:
        print("(report only — registry not written)")


if __name__ == "__main__":
    main()
