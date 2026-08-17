"""The overlay env bridge must survive Python 3.9, and must never eval garbage.

Two independent defects produced one silent failure:

1. `manage_overlays.py` used PEP-604 unions (`Path | None`). Those are evaluated
   eagerly at function-definition time, so under Python 3.9 the module raised
   TypeError at import -- and `resolve_overlay_config.py` imports it, so the
   resolver died before emitting anything.

2. The documented consumer line was `eval "$(resolver ...)"`. Command
   substitution discards the resolver's exit status, so that line returned 0
   with nothing set and the caller proceeded with its own defaults. `--require`
   and `set -e` both fail to catch it.

Either alone is survivable. Together they mean a crashed resolver looks exactly
like "no overlay configured", and the run silently targets the wrong ChatGPT
account or CDP port.

macOS ships `/usr/bin/python3` as 3.9, and
`deep-research-prompt/tests/live/oracle-subagent-local-proof.sh` hardcodes that
interpreter, so 3.9 is a live target rather than a hypothetical one.
"""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
RESOLVER = SCRIPTS / "resolve_overlay_config.py"
MANAGE_OVERLAYS = SCRIPTS / "manage_overlays.py"
HELPER = SCRIPTS / "overlay_env.sh"

# Both modules load inside the shell eval bridge, so a union in either one
# disables the resolver.
BRIDGE_MODULES = (RESOLVER, MANAGE_OVERLAYS)


def find_python39() -> str | None:
    """A real 3.9 interpreter, if this machine has one."""
    candidates = [shutil.which("python3.9"), "/usr/bin/python3"]
    for candidate in candidates:
        if not candidate or not Path(candidate).exists():
            continue
        probe = subprocess.run(
            [candidate, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
            text=True,
            capture_output=True,
            check=False,
        )
        if probe.returncode == 0 and probe.stdout.strip() == "3.9":
            return candidate
    return None


def annotation_nodes(tree: ast.AST):
    """Every AST node that sits in an annotation position."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.returns is not None:
                yield node.returns
            args = node.args
            for arg in [
                *args.posonlyargs,
                *args.args,
                *args.kwonlyargs,
                args.vararg,
                args.kwarg,
            ]:
                if arg is not None and arg.annotation is not None:
                    yield arg.annotation
        elif isinstance(node, ast.AnnAssign) and node.annotation is not None:
            yield node.annotation


def has_future_annotations(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            if any(alias.name == "annotations" for alias in node.names):
                return True
    return False


def run_helper(
    script: str,
    env_extra: dict | None = None,
    helper: Path | None = None,
) -> subprocess.CompletedProcess:
    """Run a snippet with overlay_env.sh sourced, under bash."""
    body = f'. "{helper or HELPER}"\n{script}\n'
    env = dict(os.environ)
    # The helper finds the resolver beside itself unless told otherwise, so a
    # stale value from the ambient environment would mask what a test sets.
    env.pop("OVERLAY_ENV_RESOLVER", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["bash", "-c", body], text=True, capture_output=True, check=False, env=env
    )


# --------------------------------------------------------------------------
# Defect 1: the modules must load under Python 3.9.
# --------------------------------------------------------------------------


def test_bridge_modules_declare_postponed_annotations() -> None:
    """The mechanism that makes PEP-604 safe on 3.9 must actually be present.

    This runs everywhere, including machines with no 3.9 interpreter, so the
    protection is never silently absent just because it could not be exercised.
    """
    for module in BRIDGE_MODULES:
        tree = ast.parse(module.read_text(encoding="utf-8"))
        assert has_future_annotations(tree), (
            f"{module.name} lacks `from __future__ import annotations`; a PEP-604 "
            f"union added later would break the resolver under Python 3.9"
        )


def test_bridge_modules_have_no_pep604_outside_annotations() -> None:
    """`from __future__ import annotations` postpones annotations only.

    A `|` union in a runtime position -- isinstance(), a TypeAlias, a default --
    still raises TypeError on 3.9, and the future import would not save it.
    """
    for module in BRIDGE_MODULES:
        tree = ast.parse(module.read_text(encoding="utf-8"))
        annotation_ids = {id(node) for a in annotation_nodes(tree) for node in ast.walk(a)}
        offenders = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.BinOp)
            and isinstance(node.op, ast.BitOr)
            and id(node) not in annotation_ids
            # Numeric/bitwise `a | b` on real values is fine; only type
            # expressions matter. Names/attributes/subscripts are the risky shape.
            and isinstance(node.left, (ast.Name, ast.Attribute, ast.Subscript))
        ]
        assert not offenders, (
            f"{module.name}: PEP-604 union in a runtime position at line(s) "
            f"{[n.lineno for n in offenders]}"
        )


def test_bridge_modules_compile_under_python39() -> None:
    py39 = find_python39()
    if py39 is None:
        pytest.skip("no Python 3.9 interpreter on this machine")
    result = subprocess.run(
        [py39, "-m", "py_compile", *[str(m) for m in BRIDGE_MODULES]],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_resolver_runs_under_python39(tmp_path: Path) -> None:
    """The end-to-end regression: the exact interpreter that used to crash."""
    py39 = find_python39()
    if py39 is None:
        pytest.skip("no Python 3.9 interpreter on this machine")
    result = subprocess.run(
        [py39, str(RESOLVER), "--section", "oracle", "--cwd", str(tmp_path), "--format", "env"],
        text=True,
        capture_output=True,
        check=False,
    )
    # tmp_path matches no overlay, so this is the documented no-op: exit 0,
    # nothing emitted. What matters is that it did not die at import.
    assert result.returncode == 0, result.stderr
    assert "TypeError" not in result.stderr
    assert "unsupported operand" not in result.stderr


# --------------------------------------------------------------------------
# Defect 2: the consumer must fail closed rather than proceed unoverlaid.
# --------------------------------------------------------------------------


def test_helper_loads_a_real_overlay(tmp_path: Path) -> None:
    overlay = tmp_path / ".buildooor" / "skillbox-config" / "clients" / "proj"
    overlay.mkdir(parents=True)
    (overlay / "overlay.yaml").write_text(
        "version: 1\n"
        "client:\n"
        "  id: proj\n"
        "  label: proj\n"
        "  context:\n"
        f"    cwd_match: ['{tmp_path}']\n"
        "    oracle:\n"
        "      cdp_port: 9333\n",
        encoding="utf-8",
    )
    result = run_helper(
        f'overlay_env_load oracle --cwd "{tmp_path}" || exit 1\n'
        'echo "PORT=$ORACLE_CDP_PORT"',
        {"OVERLAY_ENV_RESOLVER": str(RESOLVER)},
    )
    assert result.returncode == 0, result.stderr
    assert "PORT=9333" in result.stdout


def test_helper_fails_closed_when_resolver_crashes(tmp_path: Path) -> None:
    """The bug in one assertion: a dead resolver must not look like success."""
    broken = tmp_path / "broken_resolver.py"
    broken.write_text(
        "import sys\n"
        "sys.stderr.write('TypeError: unsupported operand type(s) for |\\n')\n"
        "sys.exit(1)\n",
        encoding="utf-8",
    )
    result = run_helper(
        'overlay_env_load oracle; echo "return=$?"\n'
        'echo "PORT=${ORACLE_CDP_PORT:-UNSET}"',
        {"OVERLAY_ENV_RESOLVER": str(broken)},
    )
    assert "return=1" in result.stdout, result.stdout
    assert "PORT=UNSET" in result.stdout
    assert "refusing to continue unoverlaid" in result.stderr
    # The diagnostic must name the interpreter, since the original cause was
    # which python3 happened to be on PATH.
    assert "interpreter:" in result.stderr


def test_helper_propagates_failure_to_set_e(tmp_path: Path) -> None:
    """`set -e` must abort. This is what `eval "$(...)"` could not do."""
    broken = tmp_path / "broken_resolver.py"
    broken.write_text("import sys; sys.exit(3)\n", encoding="utf-8")
    result = run_helper(
        'set -e\noverlay_env_load oracle\necho "SHOULD NOT PRINT"',
        {"OVERLAY_ENV_RESOLVER": str(broken)},
    )
    assert result.returncode != 0
    assert "SHOULD NOT PRINT" not in result.stdout


@pytest.mark.parametrize(
    "payload,label",
    [
        ("export ORACLE_CDP_PORT='9222'\ntouch {marker}; echo pwned", "injected command"),
        ("export ORACLE_CDP_PORT='9222'\nexport ORACLE_TRUNC", "truncated line"),
        ("Traceback (most recent call last):\n  File x", "traceback on stdout"),
        ("export ORACLE_CDP_PORT='9222'\nrm -rf {marker}", "destructive trailer"),
        ("export 9BAD='x'", "invalid identifier"),
        ("export ORACLE A='x'", "space in name"),
        ("ORACLE_CDP_PORT=9222", "bare assignment, no export"),
    ],
)
def test_helper_refuses_hostile_output(tmp_path: Path, payload: str, label: str) -> None:
    """Anything that is not a pure export line must never reach eval."""
    marker = tmp_path / "PWNED"
    hostile = tmp_path / "hostile_resolver.py"
    body = payload.format(marker=marker)
    hostile.write_text(
        "import sys\nsys.stdout.write({!r})\n".format(body + "\n"), encoding="utf-8"
    )
    result = run_helper(
        'overlay_env_load oracle; echo "return=$?"\n'
        'echo "PORT=${ORACLE_CDP_PORT:-UNSET}"',
        {"OVERLAY_ENV_RESOLVER": str(hostile)},
    )
    assert "return=1" in result.stdout, f"{label}: {result.stdout}"
    assert "refusing to eval" in result.stderr, label
    assert not marker.exists(), f"{label}: hostile payload executed"
    # All-or-nothing: a valid line sharing the payload must not be applied
    # either, or the caller gets a half-configured environment.
    assert "PORT=UNSET" in result.stdout, label


def test_helper_is_a_noop_when_resolver_absent(tmp_path: Path) -> None:
    """skill-issue is an optional dependency; absent is not the same as broken.

    The helper is copied somewhere with no resolver beside it, because next to
    the real script it would (correctly) find the real one.
    """
    lonely = tmp_path / "lonely"
    lonely.mkdir()
    helper_copy = lonely / "overlay_env.sh"
    helper_copy.write_text(HELPER.read_text(encoding="utf-8"), encoding="utf-8")
    result = run_helper(
        'overlay_env_load oracle; echo "return=$?"',
        {"HOME": str(tmp_path)},
        helper=helper_copy,
    )
    assert "return=0" in result.stdout, result.stdout + result.stderr
    assert result.stderr.strip() == "", "an absent optional dependency must be quiet"


def test_helper_requires_resolver_when_asked(tmp_path: Path) -> None:
    """A caller that cannot tolerate the no-op can demand the resolver."""
    lonely = tmp_path / "lonely"
    lonely.mkdir()
    helper_copy = lonely / "overlay_env.sh"
    helper_copy.write_text(HELPER.read_text(encoding="utf-8"), encoding="utf-8")
    result = run_helper(
        'overlay_env_load oracle; echo "return=$?"',
        {"HOME": str(tmp_path), "OVERLAY_ENV_REQUIRE": "1"},
        helper=helper_copy,
    )
    assert "return=1" in result.stdout, result.stdout + result.stderr


def test_helper_fails_closed_when_resolver_dependency_missing(tmp_path: Path) -> None:
    """A resolver that cannot import PyYAML must not read as \"no overlay\"."""
    broken = tmp_path / "no_yaml_resolver.py"
    broken.write_text("import nonexistent_module_xyz\n", encoding="utf-8")
    result = run_helper(
        'overlay_env_load oracle; echo "return=$?"',
        {"OVERLAY_ENV_RESOLVER": str(broken)},
    )
    assert "return=1" in result.stdout, result.stdout
    assert "ModuleNotFoundError" in result.stderr


def test_helper_accepts_blank_lines_and_quoted_values(tmp_path: Path) -> None:
    """Precision check: the allowlist must not reject legitimate resolver output."""
    ok = tmp_path / "ok_resolver.py"
    ok.write_text(
        "print(\"export ORACLE_A='a b c'\")\n"
        "print()\n"
        "print('export ORACLE_B=plain')\n"
        "print(\"export ORACLE_C='has=equals'\")\n",
        encoding="utf-8",
    )
    result = run_helper(
        'overlay_env_load oracle || exit 1\n'
        'echo "A=[$ORACLE_A] B=[$ORACLE_B] C=[$ORACLE_C]"',
        {"OVERLAY_ENV_RESOLVER": str(ok)},
    )
    assert result.returncode == 0, result.stderr
    assert "A=[a b c] B=[plain] C=[has=equals]" in result.stdout


def test_shape_check_survives_a_grep_whose_qv_is_inverted(tmp_path: Path) -> None:
    """The check must not change meaning with the installed grep.

    This machine's `grep` is ugrep, whose `-q -v` reports whether the pattern
    matched rather than whether any line failed to match -- the inverse of BSD
    and GNU grep. An earlier draft of this helper used `grep -qvE` and silently
    allowed an injected command through because of exactly that. The saboteur
    below reproduces the divergence: if the implementation ever reaches for grep
    again, this test fails.
    """
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    saboteur = fake_bin / "grep"
    saboteur.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    saboteur.chmod(0o755)

    marker = tmp_path / "PWNED_BADGREP"
    hostile = tmp_path / "hostile_resolver.py"
    hostile.write_text(
        "print(\"export ORACLE_X='1'\")\nprint(\"touch {}\")\n".format(marker),
        encoding="utf-8",
    )
    result = run_helper(
        'overlay_env_load oracle; echo "return=$?"',
        {
            "OVERLAY_ENV_RESOLVER": str(hostile),
            "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
        },
    )
    assert "return=1" in result.stdout, result.stdout + result.stderr
    assert not marker.exists(), "hostile payload executed under a sabotaged grep"


def test_helper_syntax_is_portable() -> None:
    """Consumers source this from bash, zsh, and sh alike."""
    for shell in ("bash", "sh", "zsh"):
        if shutil.which(shell) is None:
            continue
        result = subprocess.run(
            [shell, "-n", str(HELPER)], text=True, capture_output=True, check=False
        )
        assert result.returncode == 0, f"{shell}: {result.stderr}"


def test_documented_snippets_do_not_teach_the_unsafe_eval() -> None:
    """Docs are the delivery mechanism for this pattern; drift reintroduces it.

    The failure mode is copy-paste: every consumer learned the unsafe line from
    a reference snippet, so leaving one in place re-creates the bug elsewhere.
    """
    repo = SCRIPTS.parents[1]
    docs = [
        repo / "skill-issue" / "SKILL.md",
        repo / "skill-issue" / "references" / "overlay-config.md",
        repo / "deep-research-prompt" / "SKILL.md",
        repo / "deep-research-prompt" / "references" / "deep-research-tool-toggle.md",
        repo / "deep-research-prompt" / "references" / "oracle-subagent-local-proof.md",
    ]
    offenders = []
    for doc in docs:
        if not doc.exists():
            continue
        in_code_block = False
        for lineno, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("```"):
                in_code_block = not in_code_block
                continue
            # Only runnable snippets are dangerous. Prose that quotes the unsafe
            # form in order to forbid it is the opposite of the problem, and a
            # check that cannot tell a prescription from a prohibition would
            # push the warning out of the docs.
            if not in_code_block:
                continue
            # An anti-pattern shown deliberately must be labelled as one.
            if "DO NOT" in line:
                continue
            if 'eval "$(' in stripped and (
                "resolve_overlay_config" in stripped or "RESOLVER" in stripped
            ):
                offenders.append(f"{doc.name}:{lineno}")
    assert not offenders, (
        'unsafe `eval "$(resolve_overlay_config.py ...)"` still documented at: '
        + ", ".join(offenders)
    )


def test_docs_still_warn_against_the_unsafe_eval() -> None:
    """The inverse of the check above: the warning must not be deleted either.

    Removing the anti-pattern silently would satisfy the previous test while
    leaving the next author free to reinvent it.
    """
    contract = SCRIPTS.parent / "references" / "overlay-config.md"
    text = contract.read_text(encoding="utf-8")
    assert "why-not-eval" in text, "the rationale anchor is gone"
    assert "discards the resolver's exit status" in text


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
