from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/copy_lifecycle.py"
SPEC = importlib.util.spec_from_file_location("copy_lifecycle", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CopyLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.repo = self.base / "repo"
        self.repo.mkdir()
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        (self.repo / "source.py").write_text("value = 1\n")
        (self.repo / ".gitignore").write_text("generated/\n")
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")
        self.root = self.base / "artifacts"
        self.run = self.root / "orchestration" / "run"
        self.ledger = self.run / "COPY_LIFECYCLE.json"
        MODULE.initialize(self.ledger, root=self.root, repo=self.repo, owner="controller-bead",
                          purpose="recover useful source", release_condition="source in main; proof retained")
        self.copy = self.base / "worktrees" / "worker"

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], stderr=subprocess.PIPE).decode().strip()

    def cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), "--ledger", str(self.ledger), *args],
                              capture_output=True, text=True)

    def create_copy(self):
        result = self.cli("worktree-add", "--id", "worker-bead", "--path", str(self.copy),
                          "--owner", "worker", "--purpose", "bounded source patch",
                          "--release-condition", "main contains source and proof custody verified",
                          "--revision", "main")
        self.assertEqual(result.returncode, 0, result.stderr)
        return MODULE.load(self.ledger)["copies"][0]

    def decision(self, entry):
        inventory = MODULE.inventory(entry, self.repo)
        proof = self.run / "source-and-custody-review.json"
        proof.write_text(json.dumps({"inventory": inventory, "main": self.git("rev-parse", "main"),
                                     "source": "fixture HEAD contained in main", "proof_payload": "none",
                                     "consumers": "sandbox only", "origin": "sandbox has no external origin"}))
        evidence = [{"path": str(proof), "sha256": hashlib.sha256(proof.read_bytes()).hexdigest()}]
        value = {"inventory_sha256": MODULE.digest(inventory), "reviewed_at": MODULE.now(),
                 "verdict": "already-incorporated", "main_ref": "refs/heads/main",
                 "comparison_revision": self.git("rev-parse", "main")}
        for name, conclusion in (("source_review", "already-incorporated"), ("proof_custody", "none"),
                                 ("consumer_clearance", "clear"), ("origin_review", "fresh-owner-origin")):
            value[name] = {"conclusion": conclusion, "evidence": evidence}
        return inventory, value

    def test_creation_requires_owner_purpose_and_release_condition_before_native_write(self):
        result = self.cli("worktree-add", "--id", "worker", "--path", str(self.copy), "--owner", " ",
                          "--purpose", "patch", "--release-condition", "landed", "--revision", "main")
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.copy.exists())
        self.assertEqual(MODULE.load(self.ledger)["copies"], [])

    def test_worktree_creation_is_registered_and_keeps_source_outside_artifacts(self):
        entry = self.create_copy()
        self.assertEqual(entry["owner"], "worker")
        self.assertIn("main contains", entry["release_condition"])
        self.assertTrue(MODULE.inventory(entry, self.repo)["linked"])
        other = self.run / "source-copy"
        result = self.cli("worktree-add", "--id", "wrong", "--path", str(other), "--owner", "worker",
                          "--purpose", "patch", "--release-condition", "landed", "--revision", "main")
        self.assertEqual(result.returncode, 2)
        self.assertFalse(other.exists())

    def test_dispatch_and_closeout_detect_unregistered_native_worktree(self):
        self.git("worktree", "add", "--detach", str(self.copy), "main")
        dispatch = self.cli("dispatch-check")
        self.assertEqual(dispatch.returncode, 2)
        report = json.loads(dispatch.stdout)
        self.assertEqual(report["unresolved_copies"][0]["path"], str(self.copy))
        self.assertFalse(MODULE.closeout(MODULE.load(self.ledger), {})["complete"])

    def test_retirement_and_closeout_require_semantic_and_proof_custody(self):
        entry = self.create_copy()
        observed, decision = self.decision(entry)
        with mock.patch.object(MODULE, "consumers", return_value={"active": [], "unknown": []}):
            admission = MODULE.admit(entry, observed, decision, MODULE.load(self.ledger))
        self.assertTrue(admission["retirement_admitted"])
        self.assertTrue(self.copy.exists())  # Admission never deletes source.
        report = MODULE.closeout(MODULE.load(self.ledger), {})
        self.assertFalse(report["complete"])
        self.assertEqual(report["unresolved_copies"][0]["owner"], "worker")
        admission_file = self.run / "worker-admission.json"
        admission_file.write_text(json.dumps(admission))
        argv = ["git", "-C", str(self.repo), "worktree", "remove", str(self.copy)]
        native = subprocess.run(argv, capture_output=True)
        self.assertEqual(native.returncode, 0, native.stderr)
        retired = {"worker-bead": {"verdict": "retired", "native_exit": native.returncode,
                                  "native_argv": argv, "admission_receipt": str(admission_file),
                                  "evidence": [{"path": str(admission_file),
                                                "sha256": hashlib.sha256(admission_file.read_bytes()).hexdigest()}]}}
        self.assertTrue(MODULE.closeout(MODULE.load(self.ledger), retired)["complete"])
        retired["worker-bead"]["native_argv"].insert(-1, "--force")
        self.assertFalse(MODULE.closeout(MODULE.load(self.ledger), retired)["complete"])

    def test_dirty_untracked_and_ignored_source_remains_visible(self):
        entry = self.create_copy()
        for relative in ("source.py", "untracked.txt", "generated/proof.zip"):
            with self.subTest(relative=relative):
                path = self.copy / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                original = path.read_bytes() if path.exists() else None
                path.write_bytes(b"retained unique bytes")
                observed, decision = self.decision(entry)
                self.assertEqual(observed["state"], "dirty")
                with self.assertRaisesRegex(ValueError, "retain dirty"):
                    MODULE.admit(entry, observed, decision, MODULE.load(self.ledger))
                report = MODULE.closeout(MODULE.load(self.ledger), {})
                self.assertFalse(report["complete"])
                self.assertEqual(path.read_bytes(), b"retained unique bytes")
                if original is None:
                    path.unlink()
                else:
                    path.write_bytes(original)

    def test_unknown_active_inaccessible_and_stale_reviews_are_retained(self):
        entry = self.create_copy()
        observed, decision = self.decision(entry)
        for activity in ({"active": [123], "unknown": []}, {"active": [], "unknown": [456]}):
            with mock.patch.object(MODULE, "consumers", return_value=activity):
                with self.assertRaisesRegex(ValueError, "active or unknown"):
                    MODULE.admit(entry, observed, decision, MODULE.load(self.ledger))
        with mock.patch.object(MODULE, "consumers", return_value={"active": [], "unknown": []}):
            for field in ("inventory_sha256", "comparison_revision"):
                bad = {**decision, field: "0" * 64}
                with self.assertRaises(ValueError):
                    MODULE.admit(entry, observed, bad, MODULE.load(self.ledger))
            bad = {**decision, "reviewed_at": (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)).isoformat()}
            with self.assertRaisesRegex(ValueError, "refreshed"):
                MODULE.admit(entry, observed, bad, MODULE.load(self.ledger))
            bad = {**decision, "proof_custody": {"conclusion": "unknown", "evidence": []}}
            with self.assertRaisesRegex(ValueError, "proof_custody"):
                MODULE.admit(entry, observed, bad, MODULE.load(self.ledger))
        unknown = {**entry, "path": str(self.base / "unknown")}
        Path(unknown["path"]).mkdir()
        self.assertEqual(MODULE.inventory(unknown, self.repo)["state"], "unknown")
        self.assertTrue(self.copy.exists())

    def test_real_process_cwd_prevents_retirement(self):
        entry = self.create_copy()
        process = subprocess.Popen([sys.executable, "-c", "import time; print('ready', flush=True); time.sleep(30)"],
                                   cwd=self.copy, stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(process.stdout.readline().strip(), "ready")
            activity = MODULE.consumers(self.copy)
            self.assertIn(process.pid, activity["active"])
            original_readlink = MODULE.os.readlink

            def vanished_fd(path, *args, **kwargs):
                if str(path).startswith(f"/proc/{process.pid}/fd/"):
                    raise FileNotFoundError("fixture descriptor closed during inspection")
                return original_readlink(path, *args, **kwargs)

            with mock.patch.object(MODULE.os, "readlink", side_effect=vanished_fd):
                self.assertIn(process.pid, MODULE.consumers(self.copy)["active"])
            observed, decision = self.decision(entry)
            with self.assertRaisesRegex(ValueError, "active or unknown"):
                MODULE.admit(entry, observed, decision, MODULE.load(self.ledger))
        finally:
            process.terminate()
            process.wait(timeout=10)
            process.stdout.close()

    def test_artifacts_must_be_external_and_retirement_without_admission_stays_open(self):
        with self.assertRaisesRegex(ValueError, "external artifacts"):
            MODULE.initialize(self.repo / "run/COPY_LIFECYCLE.json", root=self.repo, repo=self.repo,
                              owner="lead", purpose="patch", release_condition="source integrated")
        entry = self.create_copy()
        self.git("worktree", "remove", str(self.copy))
        self.assertFalse(MODULE.closeout(MODULE.load(self.ledger), {
            entry["id"]: {"verdict": "retired", "native_exit": 0, "evidence": []}})["complete"])


if __name__ == "__main__":
    unittest.main()
