"""Tests for the tasks CLI, one group per acceptance criterion in docs/spec.md."""

from __future__ import annotations

import json
import re
import unittest

from support import ASSETS, CLI, STATES, TempProject, run, tree

ALLOWED = {
    ("backlog", "ready"), ("ready", "in-progress"), ("in-progress", "review"),
    ("in-progress", "blocked"), ("in-progress", "ready"), ("review", "done"),
    ("review", "ready"), ("blocked", "ready"),
} | {(s, "backlog") for s in STATES if s != "backlog"}


def field(path, key):
    match = re.search(rf"(?m)^{key}:[ \t]*(.*?)[ \t]*\r?$", path.read_text(encoding="utf-8"))
    return match.group(1) if match else None


def log_lines(path):
    text = path.read_text(encoding="utf-8")
    return [l for l in text.split("## Log", 1)[1].splitlines() if l.startswith("- ")]


class InitTests(TempProject):
    def test_init_creates_exact_structure(self):
        self.ok("init")
        expected = {"tasks", "tasks/README.md", "tasks/_template.md"}
        for state in STATES:
            expected |= {f"tasks/{state}", f"tasks/{state}/.gitkeep"}
        self.assertEqual(set(tree(self.root)), expected)

    def test_second_init_changes_nothing(self):
        self.ok("init")
        before = tree(self.root)
        mtimes = {p: p.stat().st_mtime_ns for p in self.root.rglob("*")}
        self.assertIn("nothing changed", self.ok("init"))
        self.assertEqual(tree(self.root), before)
        self.assertEqual({p: p.stat().st_mtime_ns for p in self.root.rglob("*")}, mtimes)

    def test_init_never_overwrites(self):
        self.ok("init")
        readme = self.root / "tasks" / "README.md"
        readme.write_text("<!-- task-queue v1 -->\nlocal edits\n", encoding="utf-8")
        self.ok("init")
        self.assertIn("local edits", readme.read_text(encoding="utf-8"))

    def test_embedded_files_match_assets(self):
        self.ok("init")
        for name in ("README.md", "_template.md"):
            self.assertEqual((self.root / "tasks" / name).read_bytes(),
                             (ASSETS / "tasks" / name).read_bytes(), name)


class NewTests(TempProject):
    def setUp(self):
        super().setUp()
        self.ok("init")

    def test_first_task_is_0001_in_backlog(self):
        out = self.ok("new", "Add retry with backoff to the sync job!", "--agent", "claude").strip()
        self.assertEqual(out, "tasks/backlog/0001-add-retry-with-backoff-to-the-sync-job.md")
        path = self.root / out
        self.assertEqual(field(path, "id"), "0001")
        self.assertEqual(field(path, "title"), "Add retry with backoff to the sync job!")
        self.assertEqual(field(path, "agent"), "claude")
        self.assertEqual(field(path, "priority"), "p2")
        self.assertEqual(field(path, "attempts"), "0")
        self.assertRegex(field(path, "created"), r"^\d{4}-\d{2}-\d{2}$")

    def test_ids_are_never_reused_after_done(self):
        first = self.new("First")
        self.place(first, "done")
        out = self.ok("new", "Second", "--agent", "codex").strip()
        self.assertEqual(out, "tasks/backlog/0002-second.md")

    def test_depends_and_priority(self):
        self.new("Base")
        path = self.new("Child", priority="p1", depends="1")
        self.assertEqual(field(path, "depends_on"), "[0001]")
        self.assertEqual(field(path, "priority"), "p1")

    def test_unknown_dependency_is_rejected(self):
        result = self.cli("new", "Child", "--agent", "codex", "--depends", "0039")
        self.assertEqual(result.returncode, 1)
        self.assertIn("0039", result.stderr)
        self.assertEqual(list((self.root / "tasks" / "backlog").glob("*.md")), [])

    def test_bad_agent_is_rejected(self):
        self.assertNotEqual(self.cli("new", "X", "--agent", "bob").returncode, 0)

    def test_new_task_validates(self):
        self.new("Plain", filled=False)
        self.ok("validate")


class MoveTests(TempProject):
    def setUp(self):
        super().setUp()
        self.ok("init")

    def task_in(self, state):
        return self.place(self.new(f"Task for {state}"), state)

    def test_every_allowed_transition(self):
        for source, target in sorted(ALLOWED):
            with self.subTest(f"{source} -> {target}"):
                path = self.task_in(source)
                task_id = path.name[:4]
                result = self.cli("move", task_id, target, "--by", "codex", "--note", "because")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse(path.exists())
                self.assertTrue((self.root / "tasks" / target / path.name).is_file())

    def test_every_other_transition_is_rejected_without_touching_the_file(self):
        for source in STATES:
            for target in STATES:
                if (source, target) in ALLOWED:
                    continue
                with self.subTest(f"{source} -> {target}"):
                    path = self.task_in(source)
                    before = path.read_bytes()
                    result = self.cli("move", path.name[:4], target, "--by", "codex", "--note", "x")
                    self.assertEqual(result.returncode, 1)
                    self.assertTrue(path.is_file())
                    self.assertEqual(path.read_bytes(), before)
                    if source != target:
                        self.assertIn("allowed from", result.stderr)

    def test_ready_requires_filled_sections(self):
        placeholders = {
            "Goal": "Make the thing work.",
            "Done when": "- [ ] It works",
            "Out of scope": "Everything else.",
        }
        for source in ("backlog", "blocked"):
            for section, text in placeholders.items():
                with self.subTest(f"{source}, empty {section}"):
                    path = self.task_in(source)
                    body = path.read_text(encoding="utf-8").replace(text, "", 1)
                    path.write_bytes(body.encode("utf-8"))
                    result = self.cli("move", path.name[:4], "ready")
                    self.assertEqual(result.returncode, 1)
                    self.assertIn(section, result.stderr)
                    self.assertEqual(path.read_bytes(), body.encode("utf-8"))

    def test_notes_required(self):
        for source, target in (("in-progress", "blocked"), ("review", "ready")):
            with self.subTest(f"{source} -> {target}"):
                path = self.task_in(source)
                result = self.cli("move", path.name[:4], target, "--by", "codex")
                self.assertEqual(result.returncode, 1)
                self.assertIn("--note", result.stderr)
                self.assertTrue(path.is_file())

    def test_claim_sets_managed_fields_and_release_clears_them(self):
        path = self.task_in("ready")
        task_id = path.name[:4]
        self.ok("move", task_id, "in-progress", "--by", "codex")
        moved = self.find(task_id)
        self.assertEqual(field(moved, "claimed_by"), "codex")
        self.assertRegex(field(moved, "started"), r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
        self.assertEqual(field(moved, "attempts"), "1")
        self.ok("move", task_id, "ready", "--by", "codex", "--note", "usage limit")
        moved = self.find(task_id)
        self.assertEqual(field(moved, "claimed_by"), "")
        self.assertEqual(field(moved, "started"), "")
        self.assertEqual(field(moved, "attempts"), "1")
        self.ok("move", task_id, "in-progress", "--by", "claude")
        self.assertEqual(field(self.find(task_id), "attempts"), "2")

    def test_each_move_appends_exactly_one_log_line(self):
        path = self.task_in("ready")
        task_id = path.name[:4]
        steps = [("in-progress", "codex", None), ("blocked", "codex", "needs creds"),
                 ("ready", "human", None), ("in-progress", "codex", None), ("review", "codex", None),
                 ("done", "human", None)]
        count = len(log_lines(path))
        for target, who, note in steps:
            args = ["move", task_id, target, "--by", who] + (["--note", note] if note else [])
            self.ok(*args)
            lines = log_lines(self.find(task_id))
            self.assertEqual(len(lines), count + 1, lines)
            self.assertRegex(lines[-1], rf"^- \d{{4}}-\d{{2}}-\d{{2}} \d{{2}}:\d{{2}} {who}: .* -> {target}")
            count += 1
        self.assertIn("needs creds", "\n".join(log_lines(self.find(task_id))))

    def test_move_preserves_body_and_field_order(self):
        path = self.task_in("ready")
        original = path.read_text(encoding="utf-8").replace("Make the thing work.", "Keep *this*  text.")
        path.write_bytes(original.encode("utf-8"))
        self.ok("move", path.name[:4], "in-progress", "--by", "codex")
        updated = self.find(path.name[:4]).read_text(encoding="utf-8")
        changed = {"claimed_by", "started", "attempts"}
        old_lines = [l for l in original.splitlines() if l.split(":")[0] not in changed]
        new_lines = [l for l in updated.splitlines() if l.split(":")[0] not in changed]
        self.assertEqual(new_lines[:-1], old_lines)  # only one Log line added at the end
        keys = lambda text: re.findall(r"(?m)^(\w+):", text.split("---")[1])
        self.assertEqual(keys(updated), keys(original))

    def test_crlf_files_keep_crlf(self):
        path = self.task_in("ready")
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
        self.ok("move", path.name[:4], "in-progress", "--by", "codex")
        data = self.find(path.name[:4]).read_bytes()
        self.assertNotIn(b"\n", data.replace(b"\r\n", b""))

    def test_claim_requires_eligible_agent(self):
        path = self.place(self.new("Claude only", agent="claude"), "ready")
        result = self.cli("move", path.name[:4], "in-progress", "--by", "codex")
        self.assertEqual(result.returncode, 1)
        self.assertIn("not eligible", result.stderr)
        self.assertEqual(self.cli("move", path.name[:4], "in-progress").returncode, 1)
        self.ok("move", path.name[:4], "in-progress", "--by", "claude")

    def test_claim_requires_dependencies_done(self):
        base = self.new("Base")
        child = self.place(self.new("Child", depends=base.name[:4]), "ready")
        result = self.cli("move", child.name[:4], "in-progress", "--by", "codex")
        self.assertEqual(result.returncode, 1)
        self.assertIn("0001", result.stderr)
        self.place(base, "done")
        self.ok("move", child.name[:4], "in-progress", "--by", "codex")

    def test_missing_task(self):
        result = self.cli("move", "0099", "ready")
        self.assertEqual(result.returncode, 1)
        self.assertIn("not found", result.stderr)

    def test_already_moved_is_reported(self):
        # Simulate losing a race: the file vanishes between scan and os.replace.
        import importlib.util, sys, os
        spec = importlib.util.spec_from_file_location("tasks_under_test", CLI)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        path = self.task_in("ready")
        real_replace = os.replace

        def racing_replace(src, dst):
            if str(src) == str(path):
                real_replace(src, self.root / "tasks" / "in-progress" / path.name)
            return real_replace(src, dst)

        import contextlib, io
        module.os.replace = racing_replace
        err = io.StringIO()
        try:
            with contextlib.redirect_stderr(err):
                code = module.main(["move", path.name[:4], "in-progress", "--by", "codex",
                                    "--root", str(self.root)])
        finally:
            module.os.replace = real_replace
        self.assertEqual(code, 1)
        self.assertIn("already moved", err.getvalue())


class NextAndListTests(TempProject):
    def setUp(self):
        super().setUp()
        self.ok("init")

    def test_next_rules(self):
        claude = self.place(self.new("Claude p1", agent="claude", priority="p1"), "ready")      # 0001
        base = self.new("Base")                                                                # 0002
        blocked = self.place(self.new("Waits", agent="codex", priority="p1", depends=base.name[:4]), "ready")  # 0003
        p2 = self.place(self.new("Codex p2", agent="codex", priority="p2"), "ready")            # 0004
        p1 = self.place(self.new("Either p1", agent="either", priority="p1"), "ready")          # 0005
        self.new("Backlog p1", agent="codex", priority="p1")                                   # 0006
        self.assertEqual(self.ok("next", "--agent", "codex").strip(), p1.name[:4])
        self.assertEqual(self.ok("next", "--agent", "claude").strip(), claude.name[:4])
        self.place(self.find(p1.name[:4]), "done")
        self.assertEqual(self.ok("next", "--agent", "codex").strip(), p2.name[:4])
        self.place(self.find(base.name[:4]), "done")
        self.assertEqual(self.ok("next", "--agent", "codex").strip(), blocked.name[:4])

    def test_ties_break_by_lowest_id(self):
        first = self.place(self.new("One"), "ready")
        self.place(self.new("Two"), "ready")
        self.assertEqual(self.ok("next", "--agent", "codex").strip(), first.name[:4])

    def test_next_skips_unfilled(self):
        self.place(self.new("Empty", filled=False), "ready")
        result = self.cli("next", "--agent", "codex")
        self.assertEqual((result.returncode, result.stdout), (1, ""))

    def test_next_with_nothing_eligible(self):
        result = self.cli("next", "--agent", "claude")
        self.assertEqual((result.returncode, result.stdout), (1, ""))

    def test_list_sorted_and_filtered(self):
        self.new("Backlog p3", priority="p3")
        self.place(self.new("Done p1", priority="p1"), "done")
        self.new("Backlog p1", priority="p1", agent="claude")
        self.place(self.new("Ready p2"), "ready")
        rows = self.ok("list").splitlines()
        self.assertTrue(rows[0].startswith("ID"))
        self.assertEqual([r.split()[0] for r in rows[1:]], ["0003", "0001", "0004", "0002"])
        rows = self.ok("list", "--state", "backlog", "--agent", "claude").splitlines()
        self.assertEqual([r.split()[0] for r in rows[1:]], ["0003"])


class ValidateTests(TempProject):
    def setUp(self):
        super().setUp()
        self.ok("init")
        self.task = self.new("Valid task")

    def problems(self):
        result = self.cli("validate")
        self.assertEqual(result.returncode, 1, result.stdout)
        return result.stdout

    def edit(self, old, new):
        text = self.task.read_text(encoding="utf-8")
        self.assertIn(old, text)
        self.task.write_bytes(text.replace(old, new, 1).encode("utf-8"))

    def test_clean_queue_passes(self):
        self.assertIn("ok: 1 task", self.ok("validate"))

    def test_duplicate_ids(self):
        other = self.root / "tasks" / "done" / "0001-copy.md"
        other.write_bytes(self.task.read_bytes())
        self.assertIn("duplicate id 0001", self.problems())

    def test_filename_and_id_mismatch(self):
        self.edit("id: 0001", "id: 0002")
        self.assertIn("does not match file name prefix 0001", self.problems())

    def test_bad_filename(self):
        self.task.rename(self.task.with_name("0001-Bad_Name.md"))
        self.assertIn("file name must be", self.problems())

    def test_missing_required_fields(self):
        for key in ("title", "agent", "priority", "created"):
            with self.subTest(key):
                original = self.task.read_bytes()
                self.edit(f"\n{key}:", "\nxx_removed:")
                out = self.problems()
                self.assertIn(f"missing required field '{key}'", out)
                self.task.write_bytes(original)

    def test_invalid_values(self):
        self.edit("agent: either", "agent: bob")
        self.edit("priority: p2", "priority: p9")
        self.edit("model: default", "model: huge")
        out = self.problems()
        for text in ("agent must be one of", "priority must be one of", "model must be one of"):
            self.assertIn(text, out)

    def test_unknown_depends_on(self):
        self.edit("depends_on: []", "depends_on: [0039]")
        self.assertIn("depends_on 0039 does not exist", self.problems())

    def test_stray_files(self):
        (self.root / "tasks" / "notes.txt").write_text("x", encoding="utf-8")
        (self.root / "tasks" / "archive").mkdir()
        (self.root / "tasks" / "ready" / "scratch.md").write_text("x", encoding="utf-8")
        out = self.problems()
        self.assertIn("tasks/notes.txt: unexpected file", out)
        self.assertIn("tasks/archive/: unexpected folder", out)
        self.assertIn("tasks/ready/scratch.md: unexpected file", out)

    def test_missing_sections_and_unknown_fields(self):
        self.edit("## Out of scope", "## Notes")
        self.edit("model: default", "model: default\ncolour: blue")
        out = self.problems()
        self.assertIn("missing section '## Out of scope'", out)
        self.assertIn("unknown field 'colour'", out)

    def test_empty_sections_outside_backlog(self):
        unfilled = self.place(self.new("Unfilled", filled=False), "review")
        self.assertIn(f"{unfilled.name}: section 'Goal' is empty", self.problems())

    def test_hook_mode(self):
        clean = self.cli("validate", "--hook", stdin="{}")
        self.assertEqual((clean.returncode, clean.stdout.strip()), (0, "{}"))
        (self.root / "tasks" / "stray.txt").write_text("x", encoding="utf-8")
        result = self.cli("validate", "--hook", stdin=json.dumps({"stop_hook_active": False}))
        self.assertEqual(result.returncode, 2)
        self.assertIn("stray.txt", result.stderr)
        result = self.cli("validate", "--hook", stdin=json.dumps({"stop_hook_active": True}))
        self.assertEqual(result.returncode, 0)


class RootDiscoveryTests(TempProject):
    def test_commands_find_tasks_from_a_subfolder(self):
        self.ok("init")
        sub = self.root / "src" / "deep"
        sub.mkdir(parents=True)
        result = run(CLI, "new", "From below", "--agent", "codex", cwd=sub)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root / "tasks" / "backlog" / "0001-from-below.md").is_file())

    def test_no_queue_is_an_error(self):
        result = run(CLI, "list", cwd=self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("tasks init", result.stderr)


if __name__ == "__main__":
    unittest.main()
