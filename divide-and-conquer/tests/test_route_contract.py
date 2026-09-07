from __future__ import annotations

import json
import re
import subprocess
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
        cls.grok_binding = cls._section(
            cls.skill,
            "### Binding Grok Route-v2 Allocation",
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
        self.assertIn('no second live pick', self.review)
        self.assertNotRegex(self.review, r"(?m)^\s*ntm spawn\b")

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
        self.assertIn("claim one live Bead per review pane", compact)
        self.assertIn("apply Step 8 to all three panes", compact)
        self.assertIn("`REVIEW_AUTHORITY_ROUTE`", self.review)
        self.assertIn("`REVIEW_GROK_ROUTE`", self.review)
        self.assertIn("first successful singleton NTM dispatch", compact)
        self.assertIn("do not send an unbound reviewer prompt", compact)

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
        self.assertIn("Grok never becomes planning", gate)

    def test_grok_binding_is_exact_retained_and_fail_closed(self) -> None:
        for text in ('sbp route low --refresh --json', 'complete decision',
                     'route_ladders.py', 'route_ntm_spawn.sh --decision-json',
                     'safe-continuation', 'never reconstruct'):
            self.assertIn(text, self.grok_binding)

    def test_wave_grok_allocation_uses_one_pick_and_repeated_decisions(self) -> None:
        self.assertEqual(self.spawn.count('sbp route low --refresh --json'), 1)
        self.assertIn('--validate-decision-json "$GROK_ROUTE"', self.spawn)
        self.assertIn('.runnable == false and .reason == "no-route"', self.spawn)
        self.assertIn('GROK_ROUTE_NO_ROUTE.json', self.spawn)
        self.assertIn('GROK_DECISION_ARGS+=(--decision-json "$GROK_ROUTE")', self.spawn)

    def test_final_review_grok_allocation_is_atomic_and_exact(self) -> None:
        self.assertEqual(self.review.count('sbp route low --refresh --json'), 1)
        self.assertIn('--validate-decision-json "$REVIEW_GROK_ROUTE"', self.review)
        self.assertIn('.runnable == false and .reason == "no-route"', self.review)
        self.assertIn('FINAL_REVIEW_GROK_ROUTE_NO_ROUTE.json', self.review)
        self.assertIn('REVIEW_GROK_DECISION_ARGS+=(--decision-json "$REVIEW_GROK_ROUTE")', self.review)

    def test_grok_never_inherits_planning_or_final_authority(self) -> None:
        self.assertIn("Grok never becomes planning", self.model_change)
        self.assertIn("it never plans or makes final decisions", self.skill)
        self.assertNotIn("because `high` tier uses the Cursor runner", self.skill)
        self.assertIn(
            "the `high` tier allocation independent of its selected runner",
            self.skill,
        )
        self.assertIn(
            "never ask the\nGrok controller or fresh-eyes reviewer to make the final acceptance decision",
            self.review,
        )

    def test_ntm_grok_prose_uses_route_v2_without_headless_quota_fallback(self) -> None:
        self.assertIn(
            "The examples below use",
            self.grok_binding,
        )
        self.assertGreaterEqual(
            len(
                re.findall(
                    r"binding retained route-v2\s+decision",
                    self.skill,
                )
            ),
            3,
        )
        self.assertGreaterEqual(
            self.skill.count("separately classified non-NTM substrates"),
            2,
        )
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


if __name__ == "__main__":
    unittest.main()
