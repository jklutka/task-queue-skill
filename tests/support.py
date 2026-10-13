"""Shared helpers for the CLI and install tests."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / "plugins" / "task-queue"
SKILL = PLUGIN / "skills" / "task-queue"
ASSETS = SKILL / "assets"
CLI = ASSETS / "scripts" / "tasks.py"
INSTALL = SKILL / "scripts" / "install.py"
STATES = ("backlog", "ready", "in-progress", "review", "blocked", "done")

FILLED_BODY = {
    "<!-- One or two sentences describing the outcome, not the steps. -->": "Make the thing work.",
    "- [ ]\n": "- [ ] It works\n",
    "<!-- Files, modules or changes that must not be touched. -->": "Everything else.",
}


def run(*args, cwd=None, stdin=None, env=None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *map(str, args)], cwd=cwd, input=stdin, env=env,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


def tree(root: Path) -> dict[str, str]:
    """Every file and folder under root, mapped to a content hash ('dir' for folders)."""
    result = {}
    for path in sorted(root.rglob("*")):
        key = path.relative_to(root).as_posix()
        result[key] = "dir" if path.is_dir() else hashlib.sha256(path.read_bytes()).hexdigest()
    return result


class TempProject(unittest.TestCase):
    """A test case with a fresh temporary project folder in self.root."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()

    def tearDown(self):
        self._tmp.cleanup()

    def cli(self, *args, stdin=None) -> subprocess.CompletedProcess:
        return run(CLI, *args, "--root", self.root, stdin=stdin)

    def ok(self, *args) -> str:
        result = self.cli(*args)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return result.stdout

    def new(self, title="A task", agent="either", priority="p2", depends=None, filled=True) -> Path:
        args = ["new", title, "--agent", agent, "--priority", priority]
        if depends:
            args += ["--depends", depends]
        path = self.root / self.ok(*args).strip()
        if filled:
            text = path.read_text(encoding="utf-8")
            for old, new in FILLED_BODY.items():
                text = text.replace(old, new)
            path.write_bytes(text.encode("utf-8"))
        return path

    def place(self, path: Path, state: str) -> Path:
        """Put a task file directly into a state folder, with managed fields that fit it."""
        text = path.read_text(encoding="utf-8")
        if state == "in-progress":
            text = re.sub(r"(?m)^claimed_by:.*$", "claimed_by: codex", text)
            text = re.sub(r"(?m)^started:.*$", "started: 2026-10-13T09:00:00+00:00", text)
        target = self.root / "tasks" / state / path.name
        os.replace(path, target)
        target.write_bytes(text.encode("utf-8"))
        return target

    def find(self, task_id: str) -> Path:
        matches = list((self.root / "tasks").glob(f"*/{task_id}-*.md"))
        self.assertEqual(len(matches), 1, matches)
        return matches[0]

    def copy_skill(self) -> Path:
        target = self.root.parent / (self.root.name + "-skill")
        shutil.copytree(SKILL, target)
        self.addCleanup(shutil.rmtree, target, ignore_errors=True)
        return target
