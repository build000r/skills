from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "SKILL.md"


class EmptyHistoryCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        skill = SKILL.read_text(encoding="utf-8")
        dispatch = skill.split("### 8. Dispatch Node-Specific Prompts", 1)[1].split(
            "### 9. Monitor the Wave", 1
        )[0]
        cls.python_source = dispatch.split("<<'PY'\n", 1)[1].split("\nPY\n", 1)[0]

    def test_embedded_history_verifier_corroborates_omitted_empty_entries(self) -> None:
        python_source = self.python_source
        robot_empty = {
            "success": True, "session": "exact-session", "total": 0, "filtered": 0,
        }
        documented_empty = {
            "entries": [], "total_count": 0, "showing": 0, "has_more": False,
            "pagination": {
                "limit": 100000, "offset": 0, "count": 0,
                "total": 0, "has_more": False,
            },
        }
        cases = (
            ("live empty shape", robot_empty, documented_empty, "pre", True),
            ("empty post cannot bind", robot_empty, documented_empty, "post", False),
            ("robot wrong session", {**robot_empty, "session": "stale"},
             documented_empty, "pre", False),
            ("robot nonzero total", {**robot_empty, "total": 1},
             documented_empty, "pre", False),
            ("robot nonzero filtered", {**robot_empty, "filtered": 1},
             documented_empty, "pre", False),
            ("robot boolean total", {**robot_empty, "total": False},
             documented_empty, "pre", False),
            ("explicit entries count mismatch", {**robot_empty, "entries": [], "total": 1},
             documented_empty, "pre", False),
            ("robot malformed entries", {**robot_empty, "entries": None},
             documented_empty, "pre", False),
            ("documented command failure", robot_empty, "__FAIL__", "pre", False),
            ("documented malformed JSON", robot_empty, "__MALFORMED__", "pre", False),
            ("documented nonempty", robot_empty,
             {**documented_empty, "entries": [{}], "total_count": 1, "showing": 1},
             "pre", False),
            ("documented showing nonzero", robot_empty,
             {**documented_empty, "showing": 1}, "pre", False),
            ("documented more pages", robot_empty,
             {**documented_empty, "has_more": True}, "pre", False),
            ("pagination more pages", robot_empty,
             {**documented_empty, "pagination": {
                 **documented_empty["pagination"], "has_more": True,
             }}, "pre", False),
            ("pagination offset", robot_empty,
             {**documented_empty, "pagination": {
                 **documented_empty["pagination"], "offset": 1,
             }}, "pre", False),
            ("pagination count nonzero", robot_empty,
             {**documented_empty, "pagination": {
                 **documented_empty["pagination"], "count": 1,
             }}, "pre", False),
            ("pagination total nonzero", robot_empty,
             {**documented_empty, "pagination": {
                 **documented_empty["pagination"], "total": 1,
             }}, "pre", False),
            ("documented wrong session", robot_empty,
             {**documented_empty, "session": "stale"}, "pre", False),
            ("documented count boolean", robot_empty,
             {**documented_empty, "total_count": False}, "pre", False),
        )
        with tempfile.TemporaryDirectory() as tmp:
            ntm = Path(tmp) / "ntm-fixture"
            for name, robot, documented, mode, expected_pass in cases:
                with self.subTest(name=name):
                    documented_response = (
                        "sys.exit(7)" if documented == "__FAIL__"
                        else "print('not-json')" if documented == "__MALFORMED__"
                        else f"print(json.dumps({documented!r}))"
                    )
                    ntm.write_text(
                        "#!/usr/bin/env python3\n"
                        "import json, sys\n"
                        "if sys.argv[1:] == ['--robot-history=exact-session', '--period=all']:\n"
                        f"    print(json.dumps({robot!r}))\n"
                        "elif sys.argv[1:] == ['history', '--session', 'exact-session', "
                        "'--limit', '100000', '--json']:\n"
                        f"    {documented_response}\n"
                        "else:\n"
                        "    sys.exit(2)\n",
                        encoding="utf-8",
                    )
                    ntm.chmod(0o700)
                    result = subprocess.run(
                        ["python3", "-", mode, str(ntm), "exact-session", "2",
                         "1787890086", "codex" if mode == "post" else "-", "-"],
                        input=python_source, text=True, capture_output=True,
                        check=False,
                    )
                    self.assertEqual(0 if expected_pass else 1, result.returncode,
                                     result.stderr)

    def test_nonempty_post_rejects_wrong_binding(self) -> None:
        entry = {
            "agent_types": ["grok"], "duration_ms": 1, "id": "wrong-agent",
            "prompt": "bound prompt", "session": "exact-session", "source": "cli",
            "success": True, "targets": ["2"], "ts": "2026-09-27T00:00:00Z",
        }
        history = {
            "success": True, "session": "exact-session", "total": 1,
            "filtered": 1, "entries": [entry],
        }
        with tempfile.TemporaryDirectory() as tmp:
            ntm = Path(tmp) / "ntm-fixture"
            ntm.write_text(
                "#!/usr/bin/env python3\nimport json, sys\n"
                "if sys.argv[1:] != ['--robot-history=exact-session', '--period=all']:\n"
                "    sys.exit(2)\n"
                f"print(json.dumps({history!r}))\n",
                encoding="utf-8",
            )
            ntm.chmod(0o700)
            result = subprocess.run(
                ["python3", "-", "post", str(ntm), "exact-session", "2",
                 "1", "codex", "-"],
                input=self.python_source, text=True, capture_output=True, check=False,
            )
        self.assertEqual(1, result.returncode)
        self.assertIn("agent type does not match retained runner", result.stderr)

    def test_post_binding_accepts_nanosecond_utc_and_rejects_bad_timestamps(self) -> None:
        # Model the Python 3.10 fromisoformat limit even when this test host
        # runs a newer Python that accepts nine fractional digits.
        python310_guard = r'''
_real_datetime = datetime.datetime
class _Python310Datetime:
    @staticmethod
    def fromtimestamp(*args):
        return _real_datetime.fromtimestamp(*args)
    @staticmethod
    def fromisoformat(value):
        if re.search(r"\.\d{7,}(?=[+-]\d{2}:\d{2}$)", value):
            raise ValueError("Python 3.10 rejects nanoseconds")
        return _real_datetime.fromisoformat(value)
datetime.datetime = _Python310Datetime
try:
    _Python310Datetime.fromisoformat("2026-09-27T20:33:19.825351434+00:00")
except ValueError:
    pass
else:
    raise AssertionError("Python 3.10 compatibility guard did not activate")
'''
        marker = "\nif len(sys.argv) != 8:\n"
        self.assertIn(marker, self.python_source)
        compatible_source = self.python_source.replace(marker, python310_guard + marker, 1)
        prompt_bytes = b"NTM_WORK_BINDING_V1 {}\nbound prompt"
        with tempfile.TemporaryDirectory() as tmp:
            prompt = Path(tmp) / "bound.md"
            prompt.write_bytes(prompt_bytes)
            ntm = Path(tmp) / "ntm-fixture"
            for timestamp, expected_pass in (
                ("2026-09-27T20:33:19.825351434Z", True),
                ("2026-09-27T20:33:19.badZ", False),
                ("2026-09-27T20:33:19.825351434", False),
            ):
                with self.subTest(timestamp=timestamp):
                    entry = {
                        "agent_types": ["cod"], "duration_ms": 1, "id": "bound-send",
                        "prompt": prompt_bytes.decode(), "session": "exact-session",
                        "source": "cli", "success": True, "targets": ["2"],
                        "ts": timestamp,
                    }
                    history = {
                        "success": True, "session": "exact-session", "total": 1,
                        "filtered": 1, "entries": [entry],
                    }
                    ntm.write_text(
                        "#!/usr/bin/env python3\nimport json, sys\n"
                        "if sys.argv[1:] != ['--robot-history=exact-session', '--period=all']:\n"
                        "    sys.exit(2)\n"
                        f"print(json.dumps({history!r}))\n",
                        encoding="utf-8",
                    )
                    ntm.chmod(0o700)
                    result = subprocess.run(
                        ["python3", "-", "post", str(ntm), "exact-session", "2",
                         "1", "codex", str(prompt)],
                        input=compatible_source, text=True, capture_output=True,
                        check=False,
                    )
                    self.assertEqual(0 if expected_pass else 1, result.returncode,
                                     result.stderr)
                    if expected_pass:
                        self.assertEqual("bound-send", json.loads(result.stdout)["history_id"])
                    else:
                        self.assertIn("not timezone-aware RFC3339", result.stderr)


if __name__ == "__main__":
    unittest.main()
