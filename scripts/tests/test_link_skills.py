#!/usr/bin/env python3
"""Isolated filesystem tests for scripts/link-skills.sh.

The linker reads HOME, so every run is a child process with HOME pointed at a
temporary directory. Nothing here reads or writes the operator's real home.

Run from the repo root:

  python3 -m unittest discover -s scripts/tests -p test_link_skills.py -v
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "link-skills.sh"
SYSTEM_PATH = "/usr/bin:/bin"


class LinkSkillsTests(unittest.TestCase):
    def setUp(self):
        self._parent_home = os.environ.get("HOME")
        self.tmp = tempfile.TemporaryDirectory(prefix="link-skills-")
        root = Path(self.tmp.name)
        self.home = root / "home with spaces"
        self.source = root / "source repo"
        self.home.mkdir()
        self.source.mkdir()
        self.claude = self.home / ".claude" / "skills"
        self.codex = self.home / ".codex" / "skills"
        self.assertNotEqual(self.home.resolve(), Path.home().resolve())

    def tearDown(self):
        self.tmp.cleanup()
        self.assertEqual(os.environ.get("HOME"), self._parent_home)

    def add_skill(self, name):
        skill = self.source / name
        skill.mkdir()
        (skill / "SKILL.md").write_text("# " + name + "\n", encoding="utf-8")
        return skill

    def payload(self, *parts):
        return ("|".join(parts) + "|").encode("utf-8") + b"\x00\xffUNIQUE"

    def plant_directory(self, path, payload):
        marker = path / "nested" / "payload.bin"
        marker.parent.mkdir(parents=True)
        marker.write_bytes(payload)
        return marker

    def install_roots(self):
        self.claude.mkdir(parents=True, exist_ok=True)
        self.codex.mkdir(parents=True, exist_ok=True)
        return (("claude", self.claude), ("codex", self.codex))

    def run_link(self, *args, stamp=None):
        env = {
            "HOME": str(self.home),
            "PATH": SYSTEM_PATH,
            "LANG": "C",
            "LC_ALL": "C",
        }
        self.assertNotEqual(env["HOME"], self._parent_home)
        if stamp is not None:
            bindir = Path(self.tmp.name) / "date-bin"
            bindir.mkdir(exist_ok=True)
            date_bin = bindir / "date"
            date_bin.write_text(
                "#!/bin/sh\nprintf '%s\\n' '" + stamp + "'\n",
                encoding="utf-8",
            )
            date_bin.chmod(0o755)
            env["PATH"] = str(bindir) + os.pathsep + SYSTEM_PATH
        return subprocess.run(
            ["/bin/bash", str(SCRIPT), *args, str(self.source)],
            cwd=str(self.source),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def assert_ok(self, proc):
        self.assertEqual(
            proc.returncode,
            0,
            "stdout:\n" + proc.stdout + "\nstderr:\n" + proc.stderr,
        )

    def assert_exact_bytes(self, path, payload):
        self.assertTrue(path.is_file(), path)
        self.assertEqual(path.read_bytes(), payload)

    def assert_links_to_source(self, dest, skill_name):
        expected = str((self.source / skill_name).resolve())
        self.assertTrue(dest.is_symlink(), dest)
        self.assertEqual(os.readlink(dest), expected)

    def test_exact_suffix_backup_survives_symlink_sibling(self):
        skill = "alpha"
        self.add_skill(skill)
        payloads = {}
        for label, root in self.install_roots():
            old = Path(self.tmp.name) / ("old " + label)
            old.mkdir()
            (root / skill).symlink_to(old, target_is_directory=True)
            payloads[label] = self.payload("exact-bak", label)
            self.plant_directory(root / (skill + ".bak"), payloads[label])

        proc = self.run_link()
        self.assert_ok(proc)
        self.assertNotIn("cleaned ", proc.stdout)

        for label, root in self.install_roots():
            with self.subTest(target=label):
                self.assert_links_to_source(root / skill, skill)
                marker = root / (skill + ".bak") / "nested" / "payload.bin"
                self.assert_exact_bytes(marker, payloads[label])

    def test_unrelated_backup_survives_skill_filter(self):
        self.add_skill("alpha")
        self.add_skill("beta")
        payloads = {}
        previous = {}
        for label, root in self.install_roots():
            old = Path(self.tmp.name) / ("beta-old " + label)
            old.mkdir()
            beta = root / "beta"
            beta.symlink_to(old, target_is_directory=True)
            previous[label] = os.readlink(beta)
            payloads[label] = self.payload("unrelated-bak", label)
            self.plant_directory(root / "beta.bak", payloads[label])

        proc = self.run_link("--skill", "alpha")
        self.assert_ok(proc)
        self.assertNotIn("cleaned ", proc.stdout)

        for label, root in self.install_roots():
            with self.subTest(target=label):
                self.assert_links_to_source(root / "alpha", "alpha")
                self.assertEqual(os.readlink(root / "beta"), previous[label])
                marker = root / "beta.bak" / "nested" / "payload.bin"
                self.assert_exact_bytes(marker, payloads[label])

    def test_nonlink_destination_skipped_without_replace(self):
        skill = "alpha"
        self.add_skill(skill)
        payloads = {}
        for label, root in self.install_roots():
            payloads[label] = self.payload("keep-copy", label)
            self.plant_directory(root / skill, payloads[label])

        proc = self.run_link()
        self.assert_ok(proc)
        self.assertNotIn("moved ", proc.stdout)

        for label, root in self.install_roots():
            with self.subTest(target=label):
                dest = root / skill
                self.assertFalse(dest.is_symlink(), dest)
                self.assert_exact_bytes(
                    dest / "nested" / "payload.bin",
                    payloads[label],
                )
                self.assertIn(
                    "skip: " + str(dest) + " exists and is not a symlink",
                    proc.stderr,
                )
                self.assertEqual(list(root.glob(skill + ".bak*")), [])

    def test_replace_copies_preserves_bytes_and_links_source(self):
        skill = "spaced skill"
        self.add_skill(skill)
        originals = {}
        siblings = {}
        for label, root in self.install_roots():
            originals[label] = self.payload("original-copy", label)
            siblings[label] = self.payload("sibling-bak", label)
            self.plant_directory(root / skill, originals[label])
            self.plant_directory(root / (skill + ".bak"), siblings[label])

        proc = self.run_link("--replace-copies")
        self.assert_ok(proc)
        self.assertNotIn("cleaned ", proc.stdout)

        for label, root in self.install_roots():
            with self.subTest(target=label):
                dest = root / skill
                self.assert_links_to_source(dest, skill)
                backups = [
                    path
                    for path in root.iterdir()
                    if path.name.startswith(skill + ".bak.")
                ]
                self.assertEqual(len(backups), 1, [path.name for path in backups])
                backup = backups[0]
                self.assertRegex(backup.name, r"\.bak\.\d{14}$")
                self.assert_exact_bytes(
                    backup / "nested" / "payload.bin",
                    originals[label],
                )
                self.assertFalse((backup / skill).exists())
                self.assert_exact_bytes(
                    root / (skill + ".bak") / "nested" / "payload.bin",
                    siblings[label],
                )

    def test_same_second_replacement_keeps_distinct_backups(self):
        skill = "alpha"
        stamp = "20261011120000"
        self.add_skill(skill)
        first = {}
        second = {}
        for label, root in self.install_roots():
            first[label] = self.payload("first", label)
            second[label] = self.payload("second", label)
            self.plant_directory(root / skill, first[label])

        first_run = self.run_link("--replace-copies", stamp=stamp)
        self.assert_ok(first_run)

        for _label, root in self.install_roots():
            dest = root / skill
            self.assertTrue(dest.is_symlink(), dest)
            dest.unlink()
        for label, root in self.install_roots():
            self.plant_directory(root / skill, second[label])

        second_run = self.run_link("--replace-copies", stamp=stamp)
        self.assert_ok(second_run)

        for label, root in self.install_roots():
            with self.subTest(target=label):
                prior = root / (skill + ".bak." + stamp)
                later = root / (skill + ".bak." + stamp + ".2")
                self.assert_exact_bytes(
                    prior / "nested" / "payload.bin",
                    first[label],
                )
                self.assert_exact_bytes(
                    later / "nested" / "payload.bin",
                    second[label],
                )
                self.assertFalse((prior / skill).exists())
                self.assertFalse((later / skill).exists())
                self.assert_links_to_source(root / skill, skill)


if __name__ == "__main__":
    unittest.main()
