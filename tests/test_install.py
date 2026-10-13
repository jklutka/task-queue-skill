"""Tests for the task-queue skill's install.py, one group per acceptance criterion."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from support import ASSETS, INSTALL, REPO, SKILL, STATES, TempProject, run, tree

SECTION = (ASSETS / "agents-section.md").read_text(encoding="utf-8").strip()


def bump(skill: Path, version: int = 2) -> None:
    """Release a new version of a copied skill the way SKILL.md says to."""
    (skill / "VERSION").write_text(f"{version}\n", encoding="utf-8")
    edits = {
        "assets/tasks/README.md": [("<!-- task-queue v1 -->", f"<!-- task-queue v{version} -->")],
        "assets/scripts/tasks.py": [('__version__ = "1"', f'__version__ = "{version}"'),
                                    ("<!-- task-queue v1 -->", f"<!-- task-queue v{version} -->")],
        "assets/agents-section.md": [("task-queue:start v1", f"task-queue:start v{version}")],
        "SKILL.md": [('  version: "1"', f'  version: "{version}"')],
    }
    for name, replacements in edits.items():
        path = skill / name
        text = path.read_text(encoding="utf-8")
        for old, new in replacements:
            assert old in text, (name, old)
            text = text.replace(old, new)
        path.write_bytes(text.encode("utf-8"))


class InstallTests(TempProject):
    def install(self, *args, skill: Path = SKILL, expect: int = 0) -> str:
        result = run(skill / "scripts" / "install.py", "--project", self.root, *args)
        self.assertEqual(result.returncode, expect, result.stdout + result.stderr)
        return result.stdout + result.stderr

    def test_fresh_project_gets_queue_agents_and_claude(self):
        out = self.install()
        for state in STATES:
            self.assertTrue((self.root / "tasks" / state / ".gitkeep").is_file())
        for name in ("tasks.py", "tasks", "tasks.cmd"):
            self.assertEqual((self.root / "scripts" / name).read_bytes(),
                             (ASSETS / "scripts" / name).read_bytes())
        self.assertEqual((self.root / "AGENTS.md").read_text(encoding="utf-8"), SECTION + "\n")
        self.assertEqual((self.root / "CLAUDE.md").read_text(encoding="utf-8"), "@AGENTS.md\n")
        self.assertIn("ok: 0 tasks", out)
        self.assertEqual(run(self.root / "scripts" / "tasks.py", "validate", cwd=self.root).returncode, 0)

    def test_existing_files_keep_every_line(self):
        agents = "# Agents\n\nUse tabs.\n\n## Testing\nRun make test.\n"
        claude = "# Claude\nBe brief."  # no trailing newline
        (self.root / "AGENTS.md").write_text(agents, encoding="utf-8")
        (self.root / "CLAUDE.md").write_text(claude, encoding="utf-8")
        self.install()
        new_agents = (self.root / "AGENTS.md").read_text(encoding="utf-8")
        new_claude = (self.root / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertEqual(new_agents.splitlines()[:len(agents.splitlines())], agents.splitlines())
        self.assertIn(SECTION, new_agents)
        self.assertEqual(new_claude.splitlines()[:2], claude.splitlines())
        self.assertEqual(new_claude.splitlines()[-1], "@AGENTS.md")
        self.assertNotIn("Task queue", new_claude)

    def test_existing_import_and_moved_section_are_respected(self):
        before = "# Agents\n\n{}\n\n## Later\nKeep me last.\n".format(SECTION)
        (self.root / "AGENTS.md").write_text(before, encoding="utf-8")
        (self.root / "CLAUDE.md").write_text("Intro\n@AGENTS.md\nOutro\n", encoding="utf-8")
        self.install()
        self.assertEqual((self.root / "AGENTS.md").read_text(encoding="utf-8"), before)
        self.assertEqual((self.root / "CLAUDE.md").read_text(encoding="utf-8"), "Intro\n@AGENTS.md\nOutro\n")

    def test_crlf_files_stay_crlf(self):
        (self.root / "AGENTS.md").write_bytes(b"# Agents\r\nLine.\r\n")
        (self.root / "CLAUDE.md").write_bytes(b"# Claude\r\n")
        self.install()
        for name in ("AGENTS.md", "CLAUDE.md"):
            data = (self.root / name).read_bytes()
            self.assertNotIn(b"\n", data.replace(b"\r\n", b""), name)

    def test_second_run_changes_nothing(self):
        (self.root / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")
        self.install("--claude-hook")
        before = tree(self.root)
        out = self.install("--claude-hook")
        self.assertIn("no changes", out)
        self.assertEqual(tree(self.root), before)

    def test_version_bump_replaces_only_marked_content(self):
        agents = "# Agents\n\nBefore.\n"
        (self.root / "AGENTS.md").write_text(agents, encoding="utf-8")
        self.install()
        task = self.root / run(self.root / "scripts" / "tasks.py", "new", "Keep me", "--agent", "codex",
                               cwd=self.root).stdout.strip()
        (self.root / "AGENTS.md").write_text(
            (self.root / "AGENTS.md").read_text(encoding="utf-8") + "\nAfter.\n", encoding="utf-8")
        before = tree(self.root)
        task_bytes = task.read_bytes()

        skill = self.copy_skill()
        bump(skill)
        out = self.install(skill=skill)
        after = tree(self.root)
        changed = {k for k in after if before.get(k) != after[k]}
        self.assertEqual(changed, {"AGENTS.md", "tasks/README.md", "scripts/tasks.py"}, out)
        self.assertEqual(task.read_bytes(), task_bytes)
        text = (self.root / "AGENTS.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith(agents))
        self.assertTrue(text.endswith("<!-- task-queue:end -->\n\nAfter.\n"))
        self.assertIn("task-queue:start v2", text)
        self.assertTrue((self.root / "tasks" / "README.md").read_text(encoding="utf-8")
                        .startswith("<!-- task-queue v2 -->"))
        self.assertIn("no changes", self.install(skill=skill))

    def test_stops_on_unmarked_tasks_folder(self):
        (self.root / "tasks").mkdir()
        (self.root / "tasks" / "todo.md").write_text("my own list\n", encoding="utf-8")
        before = tree(self.root)
        out = self.install(expect=2)
        self.assertIn("not created by task-queue", out)
        self.assertEqual(tree(self.root), before)
        self.assertEqual(run(INSTALL, "--project", self.root, "--check").returncode, 2)

    def test_stops_on_unmarked_cli(self):
        (self.root / "scripts").mkdir()
        (self.root / "scripts" / "tasks.py").write_text("print('mine')\n", encoding="utf-8")
        before = tree(self.root)
        self.assertIn("scripts/tasks.py", self.install(expect=2))
        self.assertEqual(tree(self.root), before)

    def test_adopt_replaces_control_files_but_not_tasks(self):
        (self.root / "tasks" / "backlog").mkdir(parents=True)
        (self.root / "tasks" / "README.md").write_text("old rules\n", encoding="utf-8")
        mine = self.root / "tasks" / "backlog" / "0007-mine.md"
        mine.write_text("hand written\n", encoding="utf-8")
        (self.root / "scripts").mkdir()
        (self.root / "scripts" / "tasks").write_text("#!/bin/sh\necho mine\n", encoding="utf-8")
        self.install("--adopt", expect=1)  # validate fails on the hand-written task, as it should
        self.assertEqual(mine.read_text(encoding="utf-8"), "hand written\n")
        self.assertEqual((self.root / "tasks" / "README.md").read_bytes(),
                         (ASSETS / "tasks" / "README.md").read_bytes())
        self.assertEqual((self.root / "scripts" / "tasks").read_bytes(),
                         (ASSETS / "scripts" / "tasks").read_bytes())

    def test_refuses_downgrade(self):
        skill = self.copy_skill()
        bump(skill)
        self.install(skill=skill)
        before = tree(self.root)
        self.assertIn("newer than this skill", self.install(expect=2))
        self.assertEqual(tree(self.root), before)

    def test_half_marked_agents_stops_before_changes(self):
        (self.root / "AGENTS.md").write_text("<!-- task-queue:start v1 -->\nno end\n", encoding="utf-8")
        before = tree(self.root)
        self.install(expect=2)
        self.assertEqual(tree(self.root), before)

    def test_hook_merges_into_existing_settings(self):
        settings = self.root / ".claude" / "settings.json"
        settings.parent.mkdir()
        existing = {"permissions": {"allow": ["Bash(ls:*)"]},
                    "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo hi"}]}]}}
        settings.write_text(json.dumps(existing), encoding="utf-8")
        self.install("--claude-hook")
        merged = json.loads(settings.read_text(encoding="utf-8"))
        self.assertEqual(merged["permissions"], existing["permissions"])
        commands = [h["command"] for g in merged["hooks"]["Stop"] for h in g["hooks"]]
        self.assertEqual(commands[0], "echo hi")
        self.assertEqual(len(commands), 2)
        self.assertIn("validate --hook", commands[1])

    def test_hook_refuses_invalid_settings(self):
        settings = self.root / ".claude" / "settings.json"
        settings.parent.mkdir()
        settings.write_text("{not json", encoding="utf-8")
        before = tree(self.root)
        self.install("--claude-hook", expect=2)
        self.assertEqual(tree(self.root), before)

    def test_codex_hook_merges_into_codex_hooks_json(self):
        hooks = self.root / ".codex" / "hooks.json"
        hooks.parent.mkdir()
        existing = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo hi"}]}],
                              "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command",
                                                                             "command": "check"}]}]}}
        hooks.write_text(json.dumps(existing), encoding="utf-8")
        out = self.install("--codex-hook")
        self.assertIn("/hooks", out)  # reminds the user to trust the hook in Codex
        merged = json.loads(hooks.read_text(encoding="utf-8"))
        self.assertEqual(merged["hooks"]["PreToolUse"], existing["hooks"]["PreToolUse"])
        added = merged["hooks"]["Stop"][1]["hooks"][0]
        self.assertIn("validate --hook", added["command"])
        self.assertIn("validate --hook", added["commandWindows"])
        self.assertFalse((self.root / ".claude").exists())
        before = tree(self.root)
        self.install("--codex-hook")
        self.assertEqual(tree(self.root), before)

    def test_both_hooks(self):
        self.install("--claude-hook", "--codex-hook")
        for name in (".claude/settings.json", ".codex/hooks.json"):
            self.assertIn("validate --hook", (self.root / name).read_text(encoding="utf-8"))
        out = run(INSTALL, "--project", self.root, "--check").stdout
        self.assertEqual(out.count("Stop hook"), 2)
        self.assertNotIn("not installed", out)

    def test_codex_hook_refuses_invalid_json(self):
        hooks = self.root / ".codex" / "hooks.json"
        hooks.parent.mkdir()
        hooks.write_text("[]", encoding="utf-8")
        before = tree(self.root)
        self.assertIn("unexpected shape", self.install("--codex-hook", expect=2))
        self.assertEqual(tree(self.root), before)

    def test_check_reports_without_changing(self):
        self.assertEqual(run(INSTALL, "--project", self.root, "--check").returncode, 1)
        self.assertEqual(tree(self.root), {})
        self.install()
        self.assertEqual(run(INSTALL, "--project", self.root, "--check").returncode, 0)


class ShimTests(TempProject):
    """The same commands work through the platform's shim (PowerShell/cmd on Windows, sh elsewhere)."""

    def setUp(self):
        super().setUp()
        result = run(INSTALL, "--project", self.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def shim(self, *args) -> subprocess.CompletedProcess:
        if os.name == "nt":
            command = ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                       "& .\\scripts\\tasks " + " ".join(f"'{a}'" for a in args) + "; exit $LASTEXITCODE"]
        else:
            command = ["sh", "scripts/tasks", *args]
        return subprocess.run(command, cwd=self.root, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")

    @unittest.skipIf(os.name == "nt" and not shutil.which("powershell"), "PowerShell not available")
    def test_shim_round_trip(self):
        result = self.shim("new", "Shim task", "--agent", "codex")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "tasks/backlog/0001-shim-task.md")
        result = self.shim("list")
        self.assertIn("Shim task", result.stdout)
        self.assertEqual(self.shim("validate").returncode, 0)
        self.assertEqual(self.shim("next", "--agent", "codex").returncode, 1)

    @unittest.skipUnless(shutil.which("sh"), "sh not available")
    def test_stop_hook_command_runs(self):
        fragment = json.loads((ASSETS / "hooks" / "claude-stop-validate.json").read_text(encoding="utf-8"))
        command = fragment["hooks"]["Stop"][0]["hooks"][0]["command"]
        env = dict(os.environ, CLAUDE_PROJECT_DIR=self.root.as_posix())
        ok = subprocess.run(["sh", "-c", command], input="{}", env=env, capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        (self.root / "tasks" / "stray.txt").write_text("x", encoding="utf-8")
        bad = subprocess.run(["sh", "-c", command], input="{}", env=env, capture_output=True, text=True)
        self.assertEqual(bad.returncode, 2, bad.stderr)
        self.assertIn("stray.txt", bad.stderr)


class CodexHookCommandTests(TempProject):
    """The Codex Stop hook commands find the project from any folder in the repo."""

    def setUp(self):
        super().setUp()
        result = run(INSTALL, "--project", self.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        fragment = json.loads((ASSETS / "hooks" / "codex-stop-validate.json").read_text(encoding="utf-8"))
        self.hook = fragment["hooks"]["Stop"][0]["hooks"][0]

    def check(self, command: list[str], cwd: Path) -> None:
        ok = subprocess.run(command, cwd=cwd, input="{}", capture_output=True, text=True)
        self.assertEqual((ok.returncode, ok.stdout.strip()), (0, "{}"), ok.stderr)
        stray = self.root / "tasks" / "stray.txt"
        stray.write_text("x", encoding="utf-8")
        try:
            bad = subprocess.run(command, cwd=cwd, input="{}", capture_output=True, text=True)
        finally:
            stray.unlink()
        self.assertEqual(bad.returncode, 2, bad.stderr)
        self.assertIn("stray.txt", bad.stderr)
        active = subprocess.run(command, cwd=cwd, input='{"stop_hook_active": true}',
                                capture_output=True, text=True)
        self.assertEqual(active.returncode, 0)

    @unittest.skipUnless(shutil.which("sh") and shutil.which("git"), "needs sh and git")
    def test_posix_command_from_a_subfolder(self):
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        sub = self.root / "src" / "deep"
        sub.mkdir(parents=True)
        self.check(["sh", "-c", self.hook["command"]], sub)

    @unittest.skipUnless(os.name == "nt", "Windows only")
    def test_windows_command_in_cmd_and_powershell(self):
        self.check(["cmd", "/c", self.hook["commandWindows"]], self.root)
        if shutil.which("powershell"):
            self.check(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                        self.hook["commandWindows"] + "; exit $LASTEXITCODE"], self.root)


class ConsistencyTests(unittest.TestCase):
    def test_version_markers_agree(self):
        version = (SKILL / "VERSION").read_text(encoding="utf-8").strip()
        cli = (ASSETS / "scripts" / "tasks.py").read_text(encoding="utf-8")
        self.assertIn(f'__version__ = "{version}"', cli)
        self.assertTrue((ASSETS / "tasks" / "README.md").read_text(encoding="utf-8")
                        .startswith(f"<!-- task-queue v{version} -->"))
        self.assertTrue(SECTION.startswith(f"<!-- task-queue:start v{version} -->"))
        self.assertTrue(SECTION.endswith("<!-- task-queue:end -->"))
        self.assertIn(f'  version: "{version}"', (SKILL / "SKILL.md").read_text(encoding="utf-8"))

    def test_skill_frontmatter(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        front = text.split("---")[1]
        self.assertRegex(front, r"(?m)^name: task-queue$")
        self.assertEqual(SKILL.name, "task-queue")  # the standard requires name == folder name
        self.assertRegex(front, r"(?m)^license: MIT$")
        compatibility = re.search(r"(?m)^compatibility: (.+)$", front).group(1)
        self.assertLessEqual(len(compatibility), 500)
        description = re.search(r"(?m)^description: (.+)$", front).group(1)
        self.assertLessEqual(len(description), 1024)

    def test_shims_are_marked(self):
        for name in ("tasks", "tasks.cmd"):
            self.assertIn("task-queue shim", (ASSETS / "scripts" / name).read_text(encoding="utf-8"))
        self.assertNotIn(b"\r\n", (ASSETS / "scripts" / "tasks").read_bytes())
        self.assertIn(b"\r\n", (ASSETS / "scripts" / "tasks.cmd").read_bytes())

    def test_repo_installed_copy_is_current(self):
        """This repo dogfoods the skill; its installed copy must match the assets."""
        repo = REPO
        for name in ("tasks.py", "tasks", "tasks.cmd"):
            self.assertEqual((repo / "scripts" / name).read_bytes(),
                             (ASSETS / "scripts" / name).read_bytes(), f"scripts/{name}")
        for name in ("README.md", "_template.md"):
            self.assertEqual((repo / "tasks" / name).read_bytes(),
                             (ASSETS / "tasks" / name).read_bytes(), f"tasks/{name}")


if __name__ == "__main__":
    unittest.main()
