#!/usr/bin/env python3
"""Register agent source copies and gate their retirement without deleting them.

The ledger is execution evidence, not a replacement for Beads or semantic diff
review. Retirement admission supports already-incorporated linked worktrees;
clones, dirty payload and other dispositions require their owning recovery lane.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


SCHEMA = "dac-copy-lifecycle/v1"


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def required(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing {name}")
    return value


def absolute(raw: str) -> Path:
    path = Path(raw)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("paths must be normalized and absolute")
    if path.is_symlink():
        raise ValueError("copy and ledger paths must not be symlinks")
    return path.resolve()


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args],
                                   stderr=subprocess.PIPE).decode().strip()


def repository(raw: str) -> Path:
    path = absolute(raw)
    if Path(git(path, "rev-parse", "--show-toplevel")).resolve() != path:
        raise ValueError("repo must name the actual Git root")
    return path


def worktrees(repo: Path) -> list[str]:
    return sorted(line.removeprefix("worktree ") for line in
                  git(repo, "worktree", "list", "--porcelain").splitlines()
                  if line.startswith("worktree "))


def write(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    with temporary.open("x") as output:
        json.dump(value, output, indent=2, sort_keys=True)
        output.write("\n")
    os.replace(temporary, path)


def load(path: Path) -> dict:
    value = json.loads(path.read_text())
    if value.get("schema") != SCHEMA:
        raise ValueError("unsupported copy ledger schema")
    root, run = absolute(value["artifacts_root"]), absolute(value["run_dir"])
    if run == root or not run.is_relative_to(root) or path.parent != run:
        raise ValueError("ledger escaped its declared artifacts root")
    for name in ("owner", "purpose", "release_condition"):
        required(value.get(name), name)
    if not isinstance(value.get("copies"), list):
        raise ValueError("copy ledger requires a copies array")
    if not isinstance(value.get("baseline_worktrees"), list):
        raise ValueError("copy ledger requires its baseline worktree inventory")
    repo = repository(value["repo"])
    if run.is_relative_to(repo):
        raise ValueError("ledger belongs outside the primary checkout")
    ids, paths = set(), set()
    for entry in value["copies"]:
        for name in ("id", "path", "kind", "owner", "purpose", "release_condition"):
            required(entry.get(name), "copy." + name)
        copy_path = absolute(entry["path"])
        if str(copy_path) != entry["path"] or copy_path == repo:
            raise ValueError("copy path is not a canonical independent source location")
        if entry["id"] in ids or entry["path"] in paths:
            raise ValueError("copy ledger contains duplicate custody entries")
        ids.add(entry["id"])
        paths.add(entry["path"])
    return value


def initialize(path: Path, *, root: Path, repo: Path, owner: str,
               purpose: str, release_condition: str) -> dict:
    run = path.parent
    if run == root or not run.is_relative_to(root) or run.is_relative_to(repo):
        raise ValueError("run directory must be an external artifacts descendant")
    if any(part in {".git", ".dac", ".ntm"} for part in run.parts):
        raise ValueError("run directory is not an artifact boundary")
    for name, value in (("owner", owner), ("purpose", purpose),
                        ("release_condition", release_condition)):
        required(value, name)
    if path.exists():
        raise ValueError("ledger already exists; resume it instead of replacing custody")
    run.mkdir(parents=True, exist_ok=True)
    value = {"schema": SCHEMA, "artifacts_root": str(root), "run_dir": str(run),
             "repo": str(repo), "owner": owner, "purpose": purpose,
             "release_condition": release_condition, "created_at": now(),
             "baseline_worktrees": worktrees(repo), "copies": []}
    write(path, value)
    return value


def register(path: Path, *, copy_id: str, copy_path: Path, kind: str,
             owner: str, purpose: str, release_condition: str) -> dict:
    ledger = load(path)
    for name, value in (("id", copy_id), ("owner", owner), ("purpose", purpose),
                        ("release_condition", release_condition)):
        required(value, name)
    if any(item["id"] == copy_id or item["path"] == str(copy_path)
           for item in ledger["copies"]):
        raise ValueError("copy already registered; preserve its original custody entry")
    if copy_path == Path(ledger["repo"]):
        raise ValueError("primary checkout is not a disposable agent copy")
    entry = {"id": copy_id, "path": str(copy_path), "kind": kind, "owner": owner,
             "purpose": purpose, "release_condition": release_condition,
             "registered_at": now()}
    ledger["copies"].append(entry)
    write(path, ledger)
    return entry


def consumers(copy_path: Path) -> dict:
    """Check this OS user's cwd/exe/fd/maps; inaccessible owner processes block."""
    if not Path("/proc").is_dir():
        return {"active": [], "unknown": ["native process proof required on this host"]}
    active, unknown = [], []
    prefix = str(copy_path) + "/"

    def inside(raw: str) -> bool:
        raw = raw.removesuffix(" (deleted)")
        return raw == str(copy_path) or raw.startswith(prefix)

    for process in Path("/proc").iterdir():
        if not process.name.isdigit():
            continue
        targets: list[str] = []
        try:
            if process.stat().st_uid != os.getuid():
                continue
            for name in ("cwd", "exe"):
                targets.append(os.readlink(process / name))
            for fd in (process / "fd").iterdir():
                try:
                    targets.append(os.readlink(fd))
                except (FileNotFoundError, ProcessLookupError):
                    # Includes the descriptor used to enumerate /proc/self/fd.
                    # Continue this process; its other FDs/maps can still pin it.
                    continue
            mappings = (process / "maps").read_text()
            targets.extend(line.split(None, 5)[5] for line in mappings.splitlines()
                           if len(line.split(None, 5)) == 6)
            if any(inside(target) for target in targets):
                active.append(int(process.name))
        except (FileNotFoundError, ProcessLookupError):
            if any(inside(target) for target in targets):
                active.append(int(process.name))
            elif process.exists():
                unknown.append(int(process.name))
        except (PermissionError, OSError):
            if any(inside(target) for target in targets):
                active.append(int(process.name))
            else:
                unknown.append(int(process.name))
    return {"active": sorted(active), "unknown": sorted(unknown)}


def inventory(entry: dict, repo: Path) -> dict:
    path = absolute(entry["path"])
    result = {"id": entry["id"], "path": str(path), "kind": entry["kind"]}
    if not path.exists():
        return {**result, "state": "absent"}
    try:
        if repository(str(path)) != path:
            raise ValueError("not an exact Git root")
        common = Path(git(path, "rev-parse", "--path-format=absolute", "--git-common-dir"))
        owner_common = Path(git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir"))
        raw_status = subprocess.check_output(
            ["git", "-C", str(path), "status", "--porcelain=v1", "-z",
             "--untracked-files=all", "--ignored"])
        registrations = git(repo, "worktree", "list", "--porcelain").splitlines()
        result.update(head=git(path, "rev-parse", "HEAD"),
                      refs_sha256=hashlib.sha256(git(path, "show-ref", "--head").encode()).hexdigest(),
                      status_hex=raw_status.hex(),
                      linked=common.resolve() == owner_common.resolve()
                      and (path / ".git").is_file(),
                      registered=f"worktree {path}" in registrations,
                      state="dirty" if raw_status else "clean")
    except (OSError, ValueError, subprocess.CalledProcessError):
        result["state"] = "unknown"
    return result


def evidence(items: Any, *, copy_path: Path, root: Path) -> None:
    if not isinstance(items, list) or not items:
        raise ValueError("reviewed source/proof custody evidence is required")
    for item in items:
        path = absolute(item["path"])
        if path.is_relative_to(copy_path) or not path.is_relative_to(root):
            raise ValueError("custody evidence must survive outside the source copy")
        if hashlib.sha256(path.read_bytes()).hexdigest() != item.get("sha256"):
            raise ValueError("custody evidence digest mismatch")


def admit(entry: dict, observed: dict, decision: dict, ledger: dict) -> dict:
    """Admission is local-main containment plus external semantic/custody proof."""
    path, repo = Path(entry["path"]), Path(ledger["repo"])
    if observed["state"] != "clean" or not observed.get("linked") or not observed.get("registered"):
        raise ValueError("retain dirty, unknown, unregistered or independent source copies")
    activity = consumers(path)
    if activity["active"] or activity["unknown"]:
        raise ValueError(f"retain copy with active or unknown consumers: {activity}")
    if decision.get("inventory_sha256") != digest(observed):
        raise ValueError("source/ref inventory changed since semantic review")
    reviewed = dt.datetime.fromisoformat(required(decision.get("reviewed_at"), "reviewed_at"))
    if reviewed.tzinfo is None or not -30 <= (dt.datetime.now(dt.timezone.utc) - reviewed).total_seconds() <= 300:
        raise ValueError("semantic/consumer/origin review must be refreshed within five minutes")
    if decision.get("verdict") != "already-incorporated":
        raise ValueError("retained source requires its owning semantic recovery lane")
    main_ref = required(decision.get("main_ref"), "main_ref")
    if main_ref != "refs/heads/main":
        raise ValueError("retirement comparison must use the owning main branch")
    revision = git(repo, "rev-parse", main_ref)
    if revision != decision.get("comparison_revision"):
        raise ValueError("main changed since semantic review")
    subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor",
                    observed["head"], revision], check=True, capture_output=True)
    root = Path(ledger["artifacts_root"])
    conclusions = {"source_review": {"already-incorporated"},
                   "proof_custody": {"none", "retained"},
                   "consumer_clearance": {"clear"}, "origin_review": {"fresh-owner-origin"}}
    for name, allowed in conclusions.items():
        section = decision.get(name, {})
        if section.get("conclusion") not in allowed:
            raise ValueError(f"unresolved {name}")
        evidence(section.get("evidence"), copy_path=path, root=root)
    return {"schema": SCHEMA, "id": entry["id"], "path": str(path),
            "admitted_at": now(), "inventory": observed,
            "inventory_sha256": digest(observed), "comparison_revision": revision,
            "decision_sha256": digest(decision), "retirement_admitted": True,
            "limitation": "Refresh external origin, all-user consumers and proof pins before native removal."}


def closeout(ledger: dict, decisions: dict) -> dict:
    resolved, unresolved = [], []
    repo = Path(ledger["repo"])
    registrations = git(repo, "worktree", "list", "--porcelain").splitlines()
    registered = {item["path"] for item in ledger["copies"]}
    for path in sorted(set(worktrees(repo)) - set(ledger["baseline_worktrees"]) - registered):
        unresolved.append({"path": path, "reason": "new unregistered worktree; establish owner and custody"})
    for entry in ledger["copies"]:
        observed = inventory(entry, repo)
        decision = decisions.get(entry["id"], {})
        try:
            if observed["state"] != "absent":
                raise ValueError("copy still exists; reconcile content then use admitted native removal")
            if f"worktree {entry['path']}" in registrations:
                raise ValueError("Git still registers the absent worktree")
            if decision.get("verdict") != "retired" or decision.get("native_exit") != 0:
                raise ValueError("missing successful native retirement receipt")
            evidence(decision.get("evidence"), copy_path=Path(entry["path"]),
                     root=Path(ledger["artifacts_root"]))
            admission_file = absolute(required(decision.get("admission_receipt"), "admission_receipt"))
            if str(admission_file) not in [item["path"] for item in decision["evidence"]]:
                raise ValueError("retirement must retain its hashed admission receipt")
            admission = json.loads(admission_file.read_text())
            if (admission.get("retirement_admitted") is not True
                    or admission.get("id") != entry["id"] or admission.get("path") != entry["path"]
                    or admission.get("inventory_sha256") != digest(admission["inventory"])):
                raise ValueError("retirement admission does not bind this source copy")
            expected = ["git", "-C", ledger["repo"], "worktree", "remove", entry["path"]]
            if decision.get("native_argv") != expected:
                raise ValueError("retirement must use exact native nonforced worktree removal")
            resolved.append(entry["id"])
        except (OSError, ValueError, KeyError) as exc:
            unresolved.append({**entry, "observation": observed, "reason": str(exc)})
    return {"schema": SCHEMA, "observed_at": now(), "resolved": resolved,
            "unresolved_copies": unresolved, "complete": not unresolved}


def dispatch_check(ledger: dict) -> dict:
    repo = Path(ledger["repo"])
    observations = [inventory(item, repo) for item in ledger["copies"]]
    registered = {item["path"] for item in ledger["copies"]}
    unresolved = [{"path": path, "reason": "new unregistered worktree"} for path in
                  sorted(set(worktrees(repo)) - set(ledger["baseline_worktrees"]) - registered)]
    unresolved.extend(item for item in observations if item["state"] != "clean")
    return {"schema": SCHEMA, "copies": observations, "unresolved_copies": unresolved,
            "complete": not unresolved}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--artifacts-root", required=True)
    init.add_argument("--repo", required=True)
    for selected in (init,):
        for name in ("owner", "purpose", "release-condition"):
            selected.add_argument("--" + name, required=True)
    for command in ("register", "worktree-add"):
        selected = sub.add_parser(command)
        for name in ("id", "path", "owner", "purpose", "release-condition"):
            selected.add_argument("--" + name, required=True)
        if command == "register":
            selected.add_argument("--kind", choices=("worktree", "clone", "source-directory"), required=True)
        else:
            selected.add_argument("--revision", required=True)
    sub.add_parser("inspect")
    sub.add_parser("dispatch-check")
    selected = sub.add_parser("admit-retirement")
    selected.add_argument("--id", required=True)
    selected.add_argument("--decisions", required=True)
    selected = sub.add_parser("closeout")
    selected.add_argument("--decisions", required=True)
    args = parser.parse_args()
    try:
        path = absolute(args.ledger)
        if args.command == "init":
            result = initialize(path, root=absolute(args.artifacts_root), repo=repository(args.repo),
                                owner=args.owner, purpose=args.purpose,
                                release_condition=args.release_condition)
        elif args.command in ("register", "worktree-add"):
            ledger = load(path)
            copy_path = absolute(args.path)
            if args.command == "worktree-add":
                if copy_path.exists() or copy_path.is_relative_to(Path(ledger["artifacts_root"])):
                    raise ValueError("new source worktree must be absent and outside retained artifacts")
                if copy_path.is_relative_to(Path(ledger["repo"])):
                    raise ValueError("new worktree must be outside the primary checkout")
            result = register(path, copy_id=args.id, copy_path=copy_path,
                              kind=getattr(args, "kind", "worktree"), owner=args.owner,
                              purpose=args.purpose, release_condition=args.release_condition)
            if args.command == "worktree-add":
                subprocess.run(["git", "-C", ledger["repo"], "worktree", "add", "--detach",
                                str(copy_path), args.revision], check=True, capture_output=True)
        else:
            ledger = load(path)
            if args.command == "inspect":
                result = {"schema": SCHEMA, "copies": [inventory(item, Path(ledger["repo"]))
                                                         for item in ledger["copies"]]}
            elif args.command == "dispatch-check":
                result = dispatch_check(ledger)
            else:
                decisions = json.loads(Path(args.decisions).read_text())
                if args.command == "closeout":
                    result = closeout(ledger, decisions)
                else:
                    entry = next(item for item in ledger["copies"] if item["id"] == args.id)
                    result = admit(entry, inventory(entry, Path(ledger["repo"])), decisions[args.id], ledger)
        print(json.dumps(result, sort_keys=True))
        return 2 if result.get("complete") is False else 0
    except (OSError, ValueError, KeyError, StopIteration, subprocess.CalledProcessError) as exc:
        print(json.dumps({"schema": SCHEMA, "complete": False, "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
