from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL = Path(__file__).resolve().parents[1] / "SKILL.md"


class RouteContractTests(unittest.TestCase):
    NON_NORMATIVE_MARKERS = (
        "HISTORICAL ONLY:",
        "NEGATIVE EXAMPLE:",
        "FORBIDDEN:",
    )

    @classmethod
    def setUpClass(cls) -> None:
        cls.skill = SKILL.read_text(encoding="utf-8")
        cls.compact = " ".join(cls.skill.split())
        cls.low_binding = cls._section(
            cls.skill,
            "### Binding Low Tier Allocation",
            "### Binding High Tier Allocation",
        )
        cls.binding = cls._section(
            cls.skill,
            "### Binding High Tier Allocation",
            "### Non-default Model-Change Gate",
        )
        cls.model_change = cls._section(
            cls.skill,
            "### Non-default Model-Change Gate",
            "Route every ready node before spawning workers:",
        )
        cls.spawn = cls._section(
            cls.skill,
            "### 7. Spawn the Wave Swarm",
            "Wait for the swarm to be ready:",
        )
        cls.recovery = cls._section(
            cls.skill,
            "### Transport Hygiene",
            "### 8. Dispatch Node-Specific Prompts",
        )
        cls.binding_dispatch = cls._section(
            cls.skill,
            "### Claim Before Spawn — bind before any work dispatch",
            "### Declare test files in `writes`",
        )
        cls.dispatch = cls._section(
            cls.skill,
            "### 8. Dispatch Node-Specific Prompts",
            "### 9. Monitor the Wave",
        )
        cls.review = cls._section(
            cls.skill,
            "### 12. Run a Final Integration and Review Wave",
            "### 13. Report to User",
        )
        cls.bash_blocks = re.findall(r"```bash\n(.*?)```", cls.skill, re.DOTALL)

    @staticmethod
    def _section(text: str, start: str, end: str) -> str:
        return text.split(start, 1)[1].split(end, 1)[0]

    @classmethod
    def _is_normative_line(cls, line: str) -> bool:
        return not any(marker in line for marker in cls.NON_NORMATIVE_MARKERS)

    def assert_no_normative_pattern(self, pattern: str) -> None:
        compiled = re.compile(pattern, re.IGNORECASE)
        findings = [
            f"{number}: {line}"
            for number, line in enumerate(self.skill.splitlines(), start=1)
            if self._is_normative_line(line) and compiled.search(line)
        ]
        self.assertEqual([], findings)

    def test_exception_requires_explicit_non_normative_marker(self) -> None:
        stale = '--cod=1:gpt-5.6-sol:medium'
        self.assertTrue(self._is_normative_line(stale))
        self.assertFalse(self._is_normative_line(f"HISTORICAL ONLY: {stale}"))
        self.assertFalse(self._is_normative_line(f"NEGATIVE EXAMPLE: {stale}"))
        self.assertFalse(self._is_normative_line(f"FORBIDDEN: {stale}"))

    def test_whole_file_rejects_stale_model_and_effort_guidance(self) -> None:
        for pattern in (
            r"gpt-5\.6-sol",
            r"\bAUTHORITY\s+(?:medium|max)\b",
            r"\bGrok 4\.5\b",
            r"\bgrok-4\.5\b",
            r"--cod(?:=|\s)",
            r"--grok(?:=|\s)",
        ):
            with self.subTest(pattern=pattern):
                self.assert_no_normative_pattern(pattern)

    def test_work_tiers_delegate_model_and_effort_to_sbp(self) -> None:
        self.assertNotIn("gpt-5.6-sol", self.skill)
        self.assertIn("Tier names describe work, not provider reasoning effort", self.compact)
        self.assertIn("SBP and the effective operator overlay own the model", self.compact)
        self.assertIn("`med` for ordinary implementation", self.compact)

    def test_binding_contract_is_exact_and_atomic(self) -> None:
        for text in ('sbp route high --refresh --json', 'route_ladders.py',
                     'retained, already validated JSON verbatim', 'repeatable',
                     '--decision-json', '--project-dir "$PROJECT_DIR"',
                     'Never re-pick between preflight and spawn', 'no static fallback exists'):
            self.assertIn(text, " ".join(self.binding.split()))

    def test_wave_spawn_uses_validated_retained_astra_decisions(self) -> None:
        self.assertEqual(self.spawn.count("sbp route high --refresh --json"), 1)
        self.assertIn('--validate-decision-json "$AUTHORITY_ROUTE"', self.spawn)
        self.assertNotIn('.runner_model ==', self.spawn)
        self.assertIn('AUTHORITY_DECISION_ARGS+=(--decision-json', self.spawn)
        self.assertIn('"$ROUTE_NTM_SPAWN"', self.spawn)
        self.assertIn('--project-dir "$PROJECT_DIR"', self.spawn)

    def test_final_review_repeats_exact_pick_and_atomic_handoff(self) -> None:
        self.assertEqual(self.review.count("sbp route high --refresh --json"), 1)
        self.assertIn('--validate-decision-json "$REVIEW_AUTHORITY_ROUTE"', self.review)
        self.assertNotIn('.runner_model ==', self.review)
        self.assertIn('--decision-json "$REVIEW_AUTHORITY_ROUTE"', self.review)
        self.assertEqual(self.review.count("sbp route low --refresh --json"), 1)
        self.assertEqual(self.review.count("sbp route pick grok --refresh --json"), 1)
        self.assertLess(self.review.index('sbp route high --refresh --json'),
                        self.review.index('\n"$ROUTE_NTM_SPAWN" \\'))
        self.assertNotRegex(self.review, r"(?m)^\s*ntm spawn\b")

    def test_helper_discovery_handles_installed_wrappers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            checkout = root / "repos" / "opensource" / "skillbox"
            scripts = checkout / "scripts"
            scripts.mkdir(parents=True)
            (checkout / ".env-manager").mkdir()
            (checkout / ".env-manager" / "manage.py").write_text("")
            (scripts / "route_ladders.py").write_text("")
            adapter = scripts / "route_ntm_spawn.sh"
            adapter.write_text("#!/bin/sh\nexit 99\n")
            adapter.chmod(0o700)
            wrapper_dir = root / "wrapper"
            wrapper_dir.mkdir()
            wrapper = wrapper_dir / "sbp"
            wrapper.write_text("#!/bin/sh\nexit 99\n")
            wrapper.chmod(0o700)
            for section in (self.spawn, self.review):
                discovery = "SBP_BIN=" + section.split("SBP_BIN=", 1)[1]
                discovery = discovery.split('ROUTE_NTM_SPAWN="$SBP_HELPER_DIR/route_ntm_spawn.sh"', 1)[0]
                for setting in ("SKILLBOX_ROOT", "SKILLBOX_OPERATOR_REPOS_ROOT"):
                    with self.subTest(section=section[:35], setting=setting):
                        env = {key: value for key, value in os.environ.items()
                               if key not in {"SKILLBOX_ROOT", "SKILLBOX_OPERATOR_REPOS_ROOT"}}
                        env["PATH"] = str(wrapper_dir) + os.pathsep + env.get("PATH", "")
                        env[setting] = str(checkout if setting == "SKILLBOX_ROOT" else root / "repos")
                        result = subprocess.run(
                            ["bash", "-eu", "-c", discovery + '\nprintf "%s" "$SBP_HELPER_DIR"'],
                            capture_output=True, text=True, env=env,
                        )
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual(result.stdout, str(scripts.resolve()))

    def test_direct_model_spawns_cannot_recur_in_any_bash_block(self) -> None:
        offenders = [
            block
            for block in self.bash_blocks
            if re.search(r"(?m)^\s*ntm spawn\b", block)
            and re.search(r"--cod|gpt-(?:5\.6|6)-(?:sol|astra|terra)", block, re.IGNORECASE)
            and all(marker not in block for marker in self.NON_NORMATIVE_MARKERS)
        ]
        self.assertEqual([], offenders)

    def test_robot_wait_uses_current_ntm_option(self) -> None:
        self.assertNotIn("--condition=idle", self.skill)
        waits = re.findall(r"ntm --robot-wait=.*", self.skill)
        self.assertGreaterEqual(len(waits), 2)
        self.assertTrue(
            all("--wait-until=idle" in wait for wait in waits),
            waits,
        )

    def test_spawn_examples_use_only_account_safe_extra_flags(self) -> None:
        for section in (self.spawn, self.review):
            matches = re.findall(
                r'"\$ROUTE_NTM_SPAWN"\s*\\\n(?:(?:[^\n]*\\\n)*?)\s*--\s*\\\n([^\n]+)',
                section,
            )
            self.assertTrue(matches, "canonical adapter call was not inspected")
            for extras in matches:
                self.assertEqual(extras.split(), ["--no-user"])

    def test_incompatible_account_allocations_require_separate_sessions(self) -> None:
        for section in (self.spawn, self.review):
            compact = " ".join(section.split())
            self.assertIn("account-bound Codex decisions", compact)
            self.assertIn("separate uniquely labeled sessions", compact)
            self.assertIn("full retained decision", compact)
            self.assertIn("never strip `account`", compact)
            invocation = re.search(r'(?m)^[ \t]*"\$ROUTE_NTM_SPAWN"[ \t]*\\$', section)
            self.assertIsNotNone(invocation, "adapter invocation was not inspected")
            self.assertLess(section.index("adapter-compatible"), invocation.start())

    def test_same_lane_recovery_uses_executable_helper(self) -> None:
        for text in ('references/safe-continuation.md', 'route_ntm_recover.sh',
                     'resends the original prompt', 'replay is proven safe',
                     'new dispatch provenance', 'previous worker', 'actual effort'):
            self.assertIn(text, " ".join(self.recovery.split()))
        self.assertNotRegex(self.recovery, r"(?m)^\s*ntm spawn\b")

    def test_binding_envelope_is_canonical_complete_and_first(self) -> None:
        self.assertIn("NTM_WORK_BINDING_V1", self.binding_dispatch)
        self.assertIn("unique earliest successful singleton dispatch", self.binding_dispatch)
        self.assertIn("complete unfiltered NTM history", self.binding_dispatch)
        binding_compact = " ".join(self.binding_dispatch.split())
        self.assertIn("Before any later successful prompt", self.binding_dispatch)
        self.assertIn("after current session creation", binding_compact)

        self.assertIn("jq -ceS", self.dispatch)
        self.assertIn('assignee: $assignee', self.dispatch)
        self.assertIn('bead: $bead', self.dispatch)
        self.assertIn('from: .', self.dispatch)
        self.assertIn('pane: $pane', self.dispatch)
        self.assertIn('pane_id: $pane_id', self.dispatch)
        self.assertIn('session: $session', self.dispatch)
        self.assertIn('"quota_surface", "reason", "runnable", "runner", "runner_model"', self.dispatch)
        self.assertIn("#{pane_id}", self.dispatch)
        self.assertIn("#{session_created}", self.dispatch)
        self.assertNotIn("pane_created", self.skill)
        self.assertIn("RETAINED_FROM_ROUTE", self.dispatch)

        claim = self.dispatch.index('br update "$ISSUE_ID" --claim --json')
        envelope = self.dispatch.index("NTM_WORK_BINDING_V1")
        send = self.dispatch.index('ntm send "$WAVE_SESSION"')
        history = self.dispatch.index('post "$NTM_BIN"')
        self.assertLess(claim, envelope)
        self.assertLess(envelope, send)
        self.assertLess(send, history)

    def test_first_dispatch_is_singleton_bound_file_not_prompt_prose(self) -> None:
        self.assertIn('--pane="$PANE_INDEX"', self.dispatch)
        self.assertIn('--file="$BOUND_PROMPT_FILE"', self.dispatch)
        self.assertIn("--no-cass-check", self.dispatch)
        self.assertIn("--force-non-interactive", self.dispatch)
        self.assertIn(".targets == [$pane]", self.dispatch)
        self.assertNotIn('ntm --robot-send="$WAVE_SESSION"', self.dispatch)
        self.assertIn("cannot establish the original recovery binding", self.binding_dispatch)
        self.assertIn('read_bytes().rstrip(b"\\r\\n")', self.dispatch)
        self.assertIn("write_bytes(payload)", self.dispatch)
        self.assertIn("must not end in CR", self.binding_dispatch)
        self.assertIn("Retain `BOUND_PROMPT_FILE` byte-for-byte", self.dispatch)
        self.assertNotIn("<INSERT NODE-SPECIFIC PROMPT>", self.dispatch)
        self.assertNotIn("$(cat <<'PROMPT'", self.dispatch)
        self.assertNotIn("Read <absolute-run-dir>/BRIEF-<node>.md", self.skill)

    def test_binding_history_is_complete_exact_and_fail_closed(self) -> None:
        self.assertEqual(1, self.dispatch.count("--period=all"))
        self.assertIn(
            'pre "$NTM_BIN" "$WAVE_SESSION" "$PANE_INDEX" "$SESSION_CREATED"',
            self.dispatch,
        )
        self.assertIn(
            'post "$NTM_BIN" "$WAVE_SESSION" "$PANE_INDEX" "$SESSION_CREATED"',
            self.dispatch,
        )
        self.assertIn('history["total"] != len(entries)', self.dispatch)
        self.assertIn('history["filtered"] != len(entries)', self.dispatch)
        self.assertIn('binding["targets"] != [str(pane)]', self.dispatch)
        self.assertIn('binding["prompt"].encode("utf-8") != prompt_bytes', self.dispatch)
        self.assertIn("pane already has successful work history", self.dispatch)
        self.assertIn("deliberately unrecoverable", self.dispatch)
        self.assertIn("stop all later sends", self.dispatch)

        recovery_compact = " ".join(self.recovery.split())
        for evidence in (
            "Missing",
            "stale",
            "filtered",
            "truncated",
            "broadcast",
            "ambiguous",
            "mismatched",
        ):
            self.assertIn(evidence, self.recovery)
        self.assertIn("zero recovery respawn, prompt send", recovery_compact)
        self.assertIn("`ROUTE_CHANGE` receipt", self.recovery)

    def test_dispatch_history_never_crosses_secret_safe_process_boundary(self) -> None:
        for forbidden in (
            "PREBIND_HISTORY",
            "BOUND_HISTORY_FILE",
            "fromdateiso8601",
            "--rawfile prompt",
            '.history.json',
        ):
            self.assertNotIn(forbidden, self.skill)
        self.assertIn("subprocess.run(", self.dispatch)
        self.assertIn('stdout=subprocess.PIPE', self.dispatch)
        self.assertIn('stderr=subprocess.DEVNULL', self.dispatch)
        self.assertIn('history = load_strict_json(history_result.stdout)', self.dispatch)
        self.assertIn("object_pairs_hook=reject_duplicate_keys", self.dispatch)
        self.assertIn('prompt_bytes = pathlib.Path(prompt_name).read_bytes()', self.dispatch)
        self.assertIn("Never capture the response in a shell variable", self.dispatch)
        self.assertIn("pass prompt/history contents\nthrough argv", self.dispatch)
        self.assertIn("persist the response in the run directory", self.dispatch)
        self.assertNotRegex(
            self.dispatch,
            r'(?m)^[^#\n]*(?:\$\([^\n]*--robot-history|--robot-history[^\n]*>)',
        )

    def test_dispatch_recipe_has_valid_bash_syntax(self) -> None:
        block = next(
            block
            for block in self.bash_blocks
            if "verify_ntm_binding_history" in block
        )
        result = subprocess.run(
            ["bash", "-n"],
            input=block,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_bound_constructor_removes_terminal_line_endings(self) -> None:
        python_blocks = re.findall(
            r"<<'PY'\n(.*?)\nPY", self.dispatch, re.DOTALL
        )
        source = next(
            block for block in python_blocks if "terminal-line normalization" in block
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "base.md"
            bound = root / "bound.md"
            base.write_bytes(b"review body\r\n\n")
            result = subprocess.run(
                ["python3", "-", '{"lane":"astra"}', str(base), str(bound)],
                input=source,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                bound.read_bytes(),
                b'NTM_WORK_BINDING_V1 {"lane":"astra"}\nreview body',
            )
            self.assertFalse(bound.read_bytes().endswith((b"\r", b"\n")))

    def test_embedded_history_verifier_accepts_fractional_rfc3339_secret_safely(self) -> None:
        python_source = self.dispatch.split("<<'PY'\n", 1)[1].split("\nPY\n", 1)[0]
        prompt_bytes = b"NTM_WORK_BINDING_V1 {}\nsecret prompt must not escape\n"
        timestamp = "2026-08-28T05:18:17.749922Z"
        session_created = "1787890086"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prompt = root / "bound.md"
            prompt.write_bytes(prompt_bytes)
            ntm = root / "ntm-fixture"
            history = {
                "success": True,
                "session": "live-shaped",
                "total": 1,
                "filtered": 1,
                "entries": [
                    {
                        "agent_types": ["cod"],
                        "duration_ms": 9,
                        "id": "fractional-live-shape",
                        "prompt": prompt_bytes.decode(),
                        "session": "live-shaped",
                        "source": "cli",
                        "success": True,
                        "targets": ["2"],
                        "ts": timestamp,
                    }
                ],
            }
            ntm.write_text(
                "#!/bin/sh\nprintf '%s\\n' '" + json.dumps(history) + "'\n",
                encoding="utf-8",
            )
            ntm.chmod(0o700)
            result = subprocess.run(
                [
                    "python3",
                    "-",
                    "post",
                    str(ntm),
                    "live-shaped",
                    "2",
                    session_created,
                    "codex",
                    str(prompt),
                ],
                input=python_source,
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(0, result.returncode, result.stderr)
        proof = json.loads(result.stdout)
        self.assertEqual("fractional-live-shape", proof["history_id"])
        self.assertEqual(timestamp, proof["history_timestamp"])
        self.assertRegex(proof["prompt_sha256"], r"^[0-9a-f]{64}$")
        self.assertNotIn("secret prompt", result.stdout)
        self.assertNotIn("secret prompt", result.stderr)

    def test_recovery_authority_is_bound_file_plus_original_history(self) -> None:
        compact = " ".join(self.recovery.split())
        self.assertIn("executable helper and its `--help` output", compact)
        self.assertIn("do not independently prove preservation", compact)
        self.assertIn("complete original NTM history", compact)
        self.assertIn("exact session, pane index, stable pane id", compact)
        self.assertIn("live Bead and assignee", compact)
        self.assertIn("full retained from-route decision", compact)
        self.assertIn("exact prompt bytes", compact)
        self.assertIn("`work_binding.history_id`", self.recovery)
        self.assertIn("`history_timestamp`", self.recovery)
        self.assertIn("`prompt_sha256`", self.recovery)
        self.assertNotIn("Recovery must preserve the exact", self.skill)

    def test_final_review_must_bind_every_pane_before_prompt(self) -> None:
        compact = " ".join(self.review.split())
        self.assertIn("claim one live Bead per pane", compact)
        self.assertIn("Before any review task or controller instruction", compact)
        self.assertIn("apply Step 8", compact)
        self.assertEqual(
            re.findall(r'--decision-json "\$(REVIEW_[A-Z_]+)"', self.review),
            ["REVIEW_AUTHORITY_ROUTE", "REVIEW_LOW_ROUTE", "REVIEW_GROK_ROUTE"],
        )
        self.assertIn("first successful singleton NTM work binding", compact)
        self.assertNotRegex(self.review, r"(?m)^\s*ntm send\b")

    def test_model_change_is_confined_to_one_fail_closed_gate(self) -> None:
        before, remainder = self.skill.split(
            "### Non-default Model-Change Gate", 1
        )
        gate, after = remainder.split("Route every ready node before spawning workers:", 1)
        outside_findings = [
            line
            for line in (before + after).splitlines()
            if self._is_normative_line(line) and re.search(r"(?i)\bterra\b", line)
        ]
        self.assertEqual([], outside_findings)
        self.assertIn('`runnable:false`', gate)
        self.assertIn('`reason:"no-route"`', gate)
        self.assertIn("exact retained `high` tier decision", gate)
        self.assertIn("already grants explicit", gate)
        self.assertIn("`MODEL_CHANGE` receipt", gate)
        self.assertIn("before execution", gate)
        self.assertIn("otherwise", gate.lower())
        self.assertIn("stop", gate)
        self.assertIn("The low-tier controller never becomes planning", gate)

    def test_low_binding_is_exact_retained_and_fail_closed(self) -> None:
        for text in ('sbp route low --refresh --json', 'validate the complete decision',
                     'pass it verbatim', 'route_ntm_spawn.sh --decision-json',
                     'safe-continuation', 'A typed no-route stops this allocation'):
            self.assertIn(text, " ".join(self.low_binding.split()))

    def test_wave_low_allocation_uses_one_pick_and_repeated_decisions(self) -> None:
        self.assertEqual(self.spawn.count('sbp route low --refresh --json'), 1)
        self.assertIn('--validate-decision-json "$LOW_ROUTE"', self.spawn)
        self.assertIn('.runnable == false and .reason == "no-route"', self.spawn)
        self.assertIn('LOW_ROUTE_NO_ROUTE.json', self.spawn)
        self.assertIn('LOW_DECISION_ARGS+=(--decision-json "$LOW_ROUTE")', self.spawn)
        self.assertIn('"${LOW_DECISION_ARGS[@]}"', self.spawn)

    def test_med_implementation_has_retained_route_and_panes(self) -> None:
        self.assertEqual(self.spawn.count('sbp route med --refresh --json'), 1)
        self.assertIn('--validate-decision-json "$MED_ROUTE"', self.spawn)
        self.assertIn('MED_ROUTE_NO_ROUTE.json', self.spawn)
        self.assertIn('MED_DECISION_ARGS+=(--decision-json "$MED_ROUTE")', self.spawn)
        self.assertIn('"${MED_DECISION_ARGS[@]}"', self.spawn)

    def test_final_review_grok_allocation_is_atomic_and_exact(self) -> None:
        self.assertEqual(self.review.count('sbp route low --refresh --json'), 1)
        self.assertEqual(self.review.count('sbp route pick grok --refresh --json'), 1)
        self.assertIn('for decision in "$REVIEW_LOW_ROUTE" "$REVIEW_GROK_ROUTE"', self.review)
        self.assertIn('--validate-decision-json "$decision" >/dev/null || exit 2', self.review)
        self.assertIn('REVIEW_GROK_ROUTE="$(sbp route pick grok --refresh --json)" || exit 2', self.review)
        self.assertIn('A typed no-route stops the affected allocation', " ".join(self.review.split()))
        self.assertIn('--decision-json "$REVIEW_GROK_ROUTE"', self.review)
        self.assertLess(self.review.index('--validate-decision-json "$decision"'),
                        self.review.index('\n"$ROUTE_NTM_SPAWN" \\'))

    def test_low_controller_never_inherits_planning_or_final_authority(self) -> None:
        self.assertIn("The low-tier controller never becomes planning", self.model_change)
        self.assertIn("The controller never gains planning or final authority", self.low_binding)
        self.assertNotIn("because `high` tier uses the Cursor runner", self.skill)
        self.assertIn(
            "the `high` tier allocation independent of its selected runner",
            self.skill,
        )
        self.assertIn(
            "low decision to runtime coordination",
            " ".join(self.review.split()),
        )
        self.assertIn("High-tier final authority remains required", self.review)

    def test_ntm_grok_prose_uses_route_v2_without_headless_quota_fallback(self) -> None:
        self.assertIn(
            "The returned runner may be Grok, Codex, or Cursor",
            " ".join(self.low_binding.split()),
        )
        for section, retained_input in (
            (self.low_binding, 'pass it verbatim'),
            (self.spawn, 'LOW_DECISION_ARGS+=(--decision-json "$LOW_ROUTE")'),
            (self.review, '--decision-json "$REVIEW_GROK_ROUTE"'),
        ):
            self.assertIn(retained_input, section)
        self.assertIn(
            "Headless one-shots are eligible only when independently selected for the node",
            self.compact,
        )
        self.assertIn("separately classified non-NTM substrates", self.skill)
        self.assertNotRegex(
            self.skill,
            r"(?is)NTM Grok plugin when .*?otherwise .*?headless Grok",
        )
        self.assertNotRegex(
            self.skill,
            r"(?is)NTM no-route.{0,120}(?:fallback|reroute).{0,120}headless",
        )

    def test_missing_route_evidence_fails_closed_without_provider_logic(self) -> None:
        self.assertIn("refusing static model fallback", self.spawn)
        self.assertIn("Do not use a static or narrative fallback", self.spawn)
        self.assertNotIn("sbp route doctor", self.skill)
        self.assertNotIn("--exclude-provider", self.skill)
        self.assertNotIn('reason: "all-exhausted"', self.skill)


class BindingProducerTests(unittest.TestCase):
    """Execute the documented producer against an external validator contract.

    The fixture authority accepts only pinned complete decisions. It deliberately
    does not duplicate SBP's account or ladder validation: these tests prove the
    producer delegates its full input and honors rejection before any send.
    Composed SBP/native acceptance remains a separate runtime gate.
    """

    LEGACY = {
        "lane": "sol", "model_family": "sol", "quota_surface": "codex",
        "runner": "codex", "runner_model": "gpt-6.1-sol", "effort": "high",
        "runnable": True, "reason": "headroom", "fallback_depth": 0,
    }
    ACCOUNT = {
        "version": "codex-account/v1", "profile": "test-profile",
        "account_id": "fixture-account", "email": "fixture@example.test",
        "codex_home": "/fixture/.local/share/caam/profiles/codex/test-profile/codex_home",
        "observed_at": "2026-10-17T00:00:00Z",
    }

    @classmethod
    def setUpClass(cls) -> None:
        skill = SKILL.read_text(encoding="utf-8")
        dispatch = skill.split("### 8. Dispatch Node-Specific Prompts", 1)[1]
        cls.producer = re.search(
            r"if ! verify_ntm_binding_history \\\n  pre .*?\nfi\n(.*?)\nFROM_RUNNER=",
            dispatch, re.DOTALL,
        ).group(1)

    def run_producer(self, decision, *, validator_status=0, approved=None,
                     acknowledgment=None, pane_index=2, send_status=0):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            approved = approved if approved is not None else [
                self.LEGACY, {**self.LEGACY, "account": self.ACCOUNT},
            ]
            (root / "approved.json").write_text(json.dumps(approved))
            validator = root / "route_ladders.py"
            validator.write_text(
                "import json, pathlib, sys\n"
                "root = pathlib.Path(__file__).parent\n"
                "args = sys.argv[1:]\n"
                "(root / 'validator-call.json').write_text(json.dumps(args))\n"
                "if len(args) != 2 or args[0] != '--validate-decision-json':\n"
                "    sys.exit(2)\n"
                "try:\n"
                "    decision = json.loads(args[1])\n"
                "except ValueError:\n"
                "    sys.exit(2)\n"
                f"if {validator_status} or decision not in json.loads("
                "(root / 'approved.json').read_text()):\n"
                "    sys.exit(2)\n"
                "print(json.dumps(decision))\n",
                encoding="utf-8",
            )
            ntm = root / "ntm"
            acknowledgment = acknowledgment if acknowledgment is not None else {
                "success": True, "session": "fixture-session", "delivered": 1,
                "failed": 0, "targets": [str(pane_index)],
            }
            ack_text = (acknowledgment if isinstance(acknowledgment, str)
                        else json.dumps(acknowledgment))
            (root / "ack.json").write_text(ack_text)
            ntm.write_text(
                f"#!{sys.executable}\n"
                "import json, pathlib, sys\n"
                "root = pathlib.Path(__file__).parent\n"
                "(root / 'send.json').write_text(json.dumps(sys.argv[1:]))\n"
                "sys.stdout.write((root / 'ack.json').read_text())\n"
                f"sys.exit({send_status})\n",
                encoding="utf-8",
            )
            ntm.chmod(0o700)
            base = root / "base.md"
            bound = root / "bound.md"
            base.write_bytes(b"private fixture task body\r\n\n")
            raw = decision if isinstance(decision, str) else json.dumps(decision)
            env = {
                **os.environ, "PATH": f"{root}{os.pathsep}{os.environ['PATH']}",
                "SBP_BIN": str(root / "sbp"), "SBP_HELPER_DIR": str(root),
                "PYTHON_BIN": sys.executable,
                "RETAINED_FROM_ROUTE": raw, "WAVE_SESSION": "fixture-session",
                "PANE_INDEX": str(pane_index), "PANE_ID": "%42", "ISSUE_ID": "fixture-1",
                "EXPECTED_ASSIGNEE": "fixture-worker", "BASE_PROMPT_FILE": str(base),
                "BOUND_PROMPT_FILE": str(bound),
                "ACK_ACCEPTED": str(root / "ack-accepted"),
            }
            result = subprocess.run(
                ["bash"], input=self.producer + '\nprintf accepted > "$ACK_ACCEPTED"\n', env=env, text=True,
                capture_output=True, check=False,
            )
            read_json = lambda name: (
                json.loads((root / name).read_text()) if (root / name).exists() else None
            )
            return result, {
                "validator_call": read_json("validator-call.json"),
                "send": read_json("send.json"),
                "bound": bound.read_bytes() if bound.exists() else None,
                "raw": raw,
                "bound_path": str(bound),
                "ack_accepted": (root / "ack-accepted").exists(),
            }

    def test_complete_account_and_legacy_decisions_survive_actual_producer(self) -> None:
        for decision in (self.LEGACY, {**self.LEGACY, "account": self.ACCOUNT}):
            with self.subTest(account="account" in decision):
                result, observed = self.run_producer(decision)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual(
                    ["--validate-decision-json", observed["raw"]],
                    observed["validator_call"],
                )
                first, body = observed["bound"].split(b"\n", 1)
                prefix = b"NTM_WORK_BINDING_V1 "
                self.assertTrue(first.startswith(prefix))
                envelope = json.loads(first[len(prefix):])
                self.assertEqual({
                    "assignee": "fixture-worker", "bead": "fixture-1", "from": decision,
                    "pane": 2, "pane_id": "%42", "session": "fixture-session",
                }, envelope)
                self.assertEqual(b"private fixture task body", body)
                self.assertEqual([
                    "send", "fixture-session", "--pane=2",
                    f"--file={observed['bound_path']}", "--no-cass-check",
                    "--force-non-interactive", "--json",
                ], observed["send"])
                self.assertNotIn("private fixture task body", result.stdout + result.stderr)

    def test_official_string_recipient_acknowledgments_include_pane_zero(self) -> None:
        for pane in (0, 2):
            for optional in ({}, {"blocked": False, "error": "", "error_code": "",
                                  "prompt_preview": "private acknowledgment preview"}):
                with self.subTest(pane=pane, optional=bool(optional)):
                    result, observed = self.run_producer(
                        {**self.LEGACY, "account": self.ACCOUNT}, pane_index=pane,
                        acknowledgment={"success": True, "session": "fixture-session",
                                        "targets": [str(pane)], "delivered": 1, "failed": 0,
                                        **optional},
                    )
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertTrue(observed["ack_accepted"])
                    self.assertNotIn("private acknowledgment preview", result.stdout + result.stderr)

    def test_malformed_or_refused_acknowledgment_stops_after_single_send(self) -> None:
        good = {"success": True, "session": "fixture-session", "targets": ["2"],
                "delivered": 1, "failed": 0}
        cases = {"invalid JSON": "not-json", "scalar": "true", "array": [good],
                 "multiple documents": json.dumps(good) + "\n" + json.dumps(good),
                 "dry run": {**good, "dry_run": True}}
        for key in good:
            cases["missing " + key] = {k: v for k, v in good.items() if k != key}
        for key, values in {
            "success": [False, "true", 1, None],
            "session": ["other-session", 2, None],
            "delivered": [0, 2, "1", True, None],
            "failed": [1, -1, "0", False, None],
            "targets": [[], [2], ["0"], ["%42"], ["1.2"], ["2", "3"],
                        ["2", "2"], [{"pane": 2}], "2", None],
            "blocked": [True, "false", 0, None],
            "error": ["refused", 0, None],
            "error_code": ["SEND_FAILED", 0, None],
        }.items():
            for value in values:
                cases[f"{key}={value!r}"] = {**good, key: value}
        for name, ack in cases.items():
            with self.subTest(case=name):
                result, observed = self.run_producer(self.LEGACY, acknowledgment=ack)
                self.assertNotEqual(0, result.returncode)
                self.assertIsNotNone(observed["send"])
                self.assertFalse(observed["ack_accepted"])
                self.assertNotIn("private fixture task body", result.stdout + result.stderr)

    def test_nonzero_send_status_cannot_be_hidden_by_valid_acknowledgment(self) -> None:
        result, observed = self.run_producer(self.LEGACY, send_status=2)
        self.assertNotEqual(0, result.returncode)
        self.assertIsNotNone(observed["send"])
        self.assertFalse(observed["ack_accepted"])

    def test_invalid_complete_decisions_fail_before_envelope_or_send(self) -> None:
        bound = {**self.LEGACY, "account": self.ACCOUNT}
        cases = {
            "account null": {**bound, "account": None},
            "account unknown version": {**bound, "account": {
                **self.ACCOUNT, "version": "unsupported"}},
            "account extra field": {**bound, "account": {**self.ACCOUNT, "extra": "bad"}},
            "account missing field": {**bound, "account": {
                k: v for k, v in self.ACCOUNT.items() if k != "account_id"}},
            "wrong runner": {**bound, "runner": "cursor"},
            "not runnable": {**bound, "runnable": False},
            "extra route field": {**bound, "extra": "bad"},
            "missing route field": {k: v for k, v in bound.items() if k != "effort"},
            "invalid JSON": "not-json",
        }
        for name, decision in cases.items():
            with self.subTest(name=name):
                result, observed = self.run_producer(decision)
                self.assertNotEqual(0, result.returncode)
                self.assertEqual(
                    ["--validate-decision-json", observed["raw"]],
                    observed["validator_call"],
                )
                self.assertIsNone(observed["bound"])
                self.assertIsNone(observed["send"])

    def test_validator_failure_stops_a_valid_decision_before_envelope_or_send(self) -> None:
        result, observed = self.run_producer(
            {**self.LEGACY, "account": self.ACCOUNT}, validator_status=2,
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIsNotNone(observed["validator_call"])
        self.assertIsNone(observed["bound"])
        self.assertIsNone(observed["send"])

    def test_envelope_keeps_strict_route_shape_after_validation(self) -> None:
        for decision in (
            {**self.LEGACY, "extra": "bad"},
            {k: v for k, v in self.LEGACY.items() if k != "reason"},
        ):
            with self.subTest(decision=decision):
                result, observed = self.run_producer(decision, approved=[decision])
                self.assertNotEqual(0, result.returncode)
                self.assertIsNone(observed["bound"])
                self.assertIsNone(observed["send"])


if __name__ == "__main__":
    unittest.main()
