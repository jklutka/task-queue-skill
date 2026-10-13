#!/usr/bin/env python3
"""tasks: manage the tasks/ folder queue.

Each task is one Markdown file in tasks/<state>/, and the folder it sits in is
its state. This helper creates, moves, lists and validates task files so that
nobody has to edit folders or managed fields by hand.

Standard library only; Python 3.10+. It never runs git.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

__version__ = "1"

STATES = ("backlog", "ready", "in-progress", "review", "blocked", "done")
AGENTS = ("claude", "codex", "either")
CLAIMANTS = ("claude", "codex")
PRIORITIES = ("p1", "p2", "p3")
REVIEWERS = ("claude", "codex", "human")
MODELS = ("default", "light", "heavy")
FIELDS = (
    "id", "title", "agent", "review_by", "priority", "depends_on", "model",
    "created", "claimed_by", "started", "attempts",
)
REQUIRED_FIELDS = ("id", "title", "agent", "priority", "created")
SECTIONS = ("Goal", "Context", "Done when", "Out of scope", "Log")
FILLED_SECTIONS = ("Goal", "Done when", "Out of scope")
CONTROL_FILES = ("README.md", "_template.md")

TRANSITIONS = frozenset(
    {
        ("backlog", "ready"),
        ("ready", "in-progress"),
        ("in-progress", "review"),
        ("in-progress", "blocked"),
        ("in-progress", "ready"),
        ("review", "done"),
        ("review", "ready"),
        ("blocked", "ready"),
    }
    | {(state, "backlog") for state in STATES if state != "backlog"}
)
NOTE_REQUIRED = frozenset({("in-progress", "blocked"), ("review", "ready")})
NEEDS_FILLED = frozenset({("backlog", "ready"), ("blocked", "ready"), ("ready", "in-progress")})

ID_RE = re.compile(r"^\d{4}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TASK_NAME_RE = re.compile(r"^(\d{4})-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
LOOSE_TASK_NAME_RE = re.compile(r"^(\d{4})-.*\.md$")
FIELD_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):(?:[ \t]+(.*?))?[ \t]*$")
HEADING_RE = re.compile(r"^##[ \t]+(.*?)[ \t]*$")
CHECKBOX_ONLY_RE = re.compile(r"^[-*+][ \t]*\[[ xX]?\]$")
COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

README_MD = r"""<!-- task-queue v1 -->
# Task queue

Planned work lives here, one Markdown file per task. The folder a file sits in
is its state. Change state only with the helper; never move task files or edit
managed fields by hand.

Run the helper from the project root:

- Linux, macOS, WSL, Git Bash: `scripts/tasks <command>`
- Windows PowerShell or cmd: `scripts\tasks <command>`
- Anywhere: `python scripts/tasks.py <command>` (Python 3.10+)

## Folders

| Folder         | Meaning                              | Moved here by               |
| -------------- | ------------------------------------ | --------------------------- |
| `backlog/`     | Drafted, not yet approved            | Human, or agent in planning |
| `ready/`       | Approved and fully specified         | Human only                  |
| `in-progress/` | Claimed by exactly one agent         | Agent or runner             |
| `review/`      | Work finished, awaiting review       | Agent or runner             |
| `blocked/`     | Failed, stalled or needs a decision  | Agent or runner             |
| `done/`        | Reviewed and accepted                | Human only                  |

Nothing else may live directly in `tasks/` besides this file and `_template.md`.

## Allowed moves

| From           | To             | Rule                                                 |
| -------------- | -------------- | ---------------------------------------------------- |
| `backlog/`     | `ready/`       | Human. Goal, Done when, Out of scope filled          |
| `ready/`       | `in-progress/` | `--by claude` or `--by codex`; task eligible for it  |
| `in-progress/` | `review/`      | Work finished                                        |
| `in-progress/` | `blocked/`     | `--note` required: what blocks it                    |
| `in-progress/` | `ready/`       | Released unfinished, e.g. usage limit                |
| `review/`      | `done/`        | Human                                                |
| `review/`      | `ready/`       | Human. `--note` with requested changes               |
| `blocked/`     | `ready/`       | Human. Same checks as backlog to ready               |
| any            | `backlog/`     | Shelved                                              |

A task is eligible for an agent when it is in `ready/`, its `agent` is that
agent or `either`, every `depends_on` ID is in `done/`, and Goal, Done when and
Out of scope are filled.

## Commands

| Command                                                   | Does                                            |
| --------------------------------------------------------- | ----------------------------------------------- |
| `init`                                                    | Create missing folders and files; safe to re-run |
| `new "<title>" --agent <a> [--priority p2] [--depends 0039,0040]` | Create a task in `backlog/`, print its path |
| `move <id> <state> [--by <who>] [--note "<text>"]`        | Move a task, update managed fields, log it      |
| `list [--state <s>] [--agent <a>]`                        | Table of tasks by state, priority, ID           |
| `next --agent <claude\|codex>`                            | Print the next eligible ID, or exit 1           |
| `validate`                                                | One line per problem; exit 0 only if clean      |

## Task file format

File name: `NNNN-short-slug.md`, a four-digit ID that is never reused and a
lowercase hyphenated slug of the title. The name never changes.

| Field        | Required | Values                         | Notes                               |
| ------------ | -------- | ------------------------------ | ----------------------------------- |
| `id`         | Yes      | 4 digits                       | Matches the file name prefix        |
| `title`      | Yes      | Text                           |                                     |
| `agent`      | Yes      | `claude`, `codex`, `either`    | Who may pick the task up            |
| `review_by`  | No       | `claude`, `codex`, `human`     | Stored only                         |
| `priority`   | Yes      | `p1`, `p2`, `p3`               | `p1` is most urgent                 |
| `depends_on` | No       | List of IDs, e.g. `[0039]`     | Must be in `done/` before pickup    |
| `model`      | No       | `default`, `light`, `heavy`    |                                     |
| `created`    | Yes      | `YYYY-MM-DD`                   | Set by `new`                        |
| `claimed_by`, `started`, `attempts` | Managed | | Written by `move` only; never edit |

Body sections, in this order: `## Goal`, `## Context`, `## Done when`,
`## Out of scope`, `## Log`. Goal, Done when and Out of scope must be filled
before a task leaves `backlog/`.

Log lines are appended, one per line: `- YYYY-MM-DD HH:MM <who>: <note>`.
The helper adds one for every move; you may add your own in the same format.

## Rules for agents

- Find work with `next --agent <you>`; claim it with
  `move <id> in-progress --by <you>` before starting.
- You may edit body text and non-managed fields (tick `Done when` boxes as you
  go). Never edit `claimed_by`, `started` or `attempts`.
- When finished, `move <id> review --by <you>`. When stuck,
  `move <id> blocked --by <you> --note "<what is needed>"`.
- Record new work found along the way with `new`; it lands in `backlog/`.
- Never move tasks into `ready/` or `done/`; those are human decisions. The one
  exception is releasing your own unfinished task back to `ready/`.
- Run `validate` before you finish; it must pass.
"""

TEMPLATE_MD = r"""---
id:
title:
agent:
review_by:
priority: p2
depends_on: []
model: default
created:
claimed_by:
started:
attempts: 0
---

## Goal
<!-- One or two sentences describing the outcome, not the steps. -->

## Context
<!-- Relevant files, prior decisions, links to related tasks or docs. -->

## Done when
<!-- Concrete, checkable conditions, one checkbox each. -->
- [ ]

## Out of scope
<!-- Files, modules or changes that must not be touched. -->

## Log
"""


class TaskError(Exception):
    """A user-facing error, printed as 'tasks: error: <message>' with exit code 1."""


# --- task documents ---------------------------------------------------------


def _strip_eol(line: str) -> str:
    return line.rstrip("\r\n")


def decode_value(raw: str):
    """Decode the flat frontmatter subset: empty, inline list, quoted or plain text."""
    if raw == "":
        return None
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        return [item.strip().strip("'\"") for item in inner.split(",")]
    if len(raw) >= 2 and raw[0] == raw[-1] == '"':
        try:
            return json.loads(raw)
        except ValueError:
            return raw
    if len(raw) >= 2 and raw[0] == raw[-1] == "'":
        return raw[1:-1].replace("''", "'")
    return raw


def encode_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "[" + ", ".join(str(item) for item in value) + "]"
    text = str(value)
    if text != text.strip() or text[:1] in ('[', '"', "'") or "\n" in text:
        return json.dumps(text, ensure_ascii=False)
    return text


class TaskDoc:
    """A task file as lines, so managed-field updates leave everything else byte-identical."""

    def __init__(self, text: str):
        self.lines = text.splitlines(keepends=True)
        self.eol = "\r\n" if self.lines and self.lines[0].endswith("\r\n") else "\n"
        if not self.lines or _strip_eol(self.lines[0]) != "---":
            raise TaskError("frontmatter must start with '---' on the first line")
        end = next((i for i in range(1, len(self.lines)) if _strip_eol(self.lines[i]) == "---"), None)
        if end is None:
            raise TaskError("frontmatter has no closing '---'")
        self.fm_end = end
        self.index: dict[str, int] = {}
        for i in range(1, end):
            line = _strip_eol(self.lines[i])
            if not line.strip():
                continue
            match = FIELD_RE.match(line)
            if not match:
                raise TaskError(f"frontmatter line {i + 1} is not 'key: value'")
            if match.group(1) in self.index:
                raise TaskError(f"field '{match.group(1)}' appears more than once")
            self.index[match.group(1)] = i

    def has(self, key: str) -> bool:
        return key in self.index

    def get(self, key: str):
        if key not in self.index:
            return None
        match = FIELD_RE.match(_strip_eol(self.lines[self.index[key]]))
        return decode_value(match.group(2) or "")

    def set(self, key: str, value) -> None:
        encoded = encode_value(value)
        line = (f"{key}: {encoded}" if encoded else f"{key}:") + self.eol
        if key in self.index:
            self.lines[self.index[key]] = line
        else:
            self.lines.insert(self.fm_end, line)
            self.index[key] = self.fm_end
            self.fm_end += 1

    def sections(self) -> list[tuple[str, int, int]]:
        """(name, heading line, end line exclusive) for each '## ' heading in the body."""
        heads = []
        for i in range(self.fm_end + 1, len(self.lines)):
            match = HEADING_RE.match(_strip_eol(self.lines[i]))
            if match:
                heads.append((match.group(1), i))
        return [
            (name, start, heads[n + 1][1] if n + 1 < len(heads) else len(self.lines))
            for n, (name, start) in enumerate(heads)
        ]

    def section_text(self, name: str) -> str | None:
        for title, start, end in self.sections():
            if title == name:
                return "".join(self.lines[start + 1:end])
        return None

    def empty_sections(self) -> list[str]:
        return [name for name in FILLED_SECTIONS if not is_filled(self.section_text(name) or "")]

    def append_log(self, entry: str) -> None:
        logs = [s for s in self.sections() if s[0] == "Log"]
        if not logs:
            raise TaskError("task has no '## Log' section")
        _, start, end = logs[-1]
        at = end
        while at - 1 > start and not self.lines[at - 1].strip():
            at -= 1
        if not self.lines[at - 1].endswith(("\n", "\r")):
            self.lines[at - 1] += self.eol
        self.lines.insert(at, entry + self.eol)

    def text(self) -> str:
        return "".join(self.lines)


def is_filled(text: str) -> bool:
    """True if a section has content beyond HTML comments and empty checkboxes."""
    for line in COMMENT_RE.sub("", text).splitlines():
        stripped = line.strip()
        if stripped and not CHECKBOX_ONLY_RE.match(stripped):
            return True
    return False


# --- the queue on disk -------------------------------------------------------


@dataclass
class Entry:
    path: Path
    state: str
    id: str
    doc: TaskDoc | None = None
    error: str | None = None


def read_text(path: Path) -> str:
    return path.read_bytes().decode("utf-8-sig")


def write_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_bytes(text.encode("utf-8"))
    os.replace(tmp, path)


def scan(root: Path) -> tuple[list[Entry], list[Path]]:
    """Task entries in every state folder, plus anything that is not a task file."""
    entries, stray = [], []
    for state in STATES:
        folder = root / "tasks" / state
        if not folder.is_dir():
            continue
        for path in sorted(folder.iterdir(), key=lambda p: p.name):
            if path.name == ".gitkeep" and path.is_file():
                continue
            match = LOOSE_TASK_NAME_RE.match(path.name)
            if not (path.is_file() and match):
                stray.append(path)
                continue
            entry = Entry(path, state, match.group(1))
            try:
                entry.doc = TaskDoc(read_text(path))
            except UnicodeDecodeError:
                entry.error = "file is not valid UTF-8"
            except TaskError as exc:
                entry.error = str(exc)
            entries.append(entry)
    return entries, stray


def rel(root: Path, path: Path) -> str:
    text = path.relative_to(root).as_posix()
    return text + "/" if path.is_dir() else text


def is_queue(path: Path) -> bool:
    return any((path / "tasks" / state).is_dir() for state in STATES)


def find_root(explicit: str | None, for_init: bool = False) -> Path:
    if explicit:
        return Path(explicit).resolve()
    cwd = Path.cwd().resolve()
    if for_init:
        return cwd
    # Prefer the project this script is installed in (<root>/scripts/tasks.py).
    installed = Path(__file__).resolve().parent.parent
    if Path(__file__).resolve().parent.name == "scripts" and is_queue(installed):
        return installed
    for candidate in (cwd, *cwd.parents):
        if is_queue(candidate):
            return candidate
    raise TaskError(
        f"no tasks/ folder found in {cwd} or its parents "
        "(run 'tasks init' at the project root, or pass --root)"
    )


def require_queue(root: Path) -> None:
    if not (root / "tasks").is_dir():
        raise TaskError(f"{root / 'tasks'} not found (run 'tasks init' first)")


def norm_id(value: str) -> str:
    if not value.isdigit() or len(value) > 4:
        raise TaskError(f"'{value}' is not a task ID (expected up to 4 digits, e.g. 0042)")
    return value.zfill(4)


def norm_state(value: str) -> str:
    state = value.strip().rstrip("/\\").lower()
    if state.startswith("tasks/") or state.startswith("tasks\\"):
        state = state[6:]
    if state not in STATES:
        raise TaskError(f"unknown state '{value}' (expected one of: {', '.join(STATES)})")
    return state


def slugify(title: str, limit: int = 50) -> str:
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_title.lower()).strip("-")
    if len(slug) > limit:
        cut = slug[:limit]
        slug = cut.rsplit("-", 1)[0] if "-" in cut else cut
    return slug or "task"


def now() -> dt.datetime:
    return dt.datetime.now().astimezone().replace(microsecond=0)


def log_line(who: str, note: str) -> str:
    note = " ".join(note.split())
    return f"- {now():%Y-%m-%d %H:%M} {who}: {note}"


# --- validation ----------------------------------------------------------------


def file_problems(entry: Entry, known_ids: set[str]) -> list[str]:
    """Problems with one task file on its own (cross-file duplicates are checked elsewhere)."""
    if entry.error:
        return [entry.error]
    doc = entry.doc
    problems = []
    if not TASK_NAME_RE.match(entry.path.name):
        problems.append("file name must be NNNN-short-slug.md (lowercase letters, digits, hyphens)")
    problems += [f"unknown field '{key}'" for key in doc.index if key not in FIELDS]
    values = {key: doc.get(key) for key in FIELDS}
    for key in REQUIRED_FIELDS:
        if values[key] in (None, "", []):
            problems.append(f"missing required field '{key}'")

    def check_choice(key: str, allowed: tuple[str, ...]) -> None:
        value = values[key]
        if value not in (None, "") and value not in allowed:
            problems.append(f"{key} must be one of {', '.join(allowed)} (got {value!r})")

    task_id = values["id"]
    if task_id not in (None, ""):
        if not (isinstance(task_id, str) and ID_RE.match(task_id)):
            problems.append(f"id must be 4 digits (got {task_id!r})")
        elif task_id != entry.id:
            problems.append(f"id {task_id} does not match file name prefix {entry.id}")
    if values["title"] is not None and not isinstance(values["title"], str):
        problems.append("title must be text")
    check_choice("agent", AGENTS)
    check_choice("priority", PRIORITIES)
    check_choice("review_by", REVIEWERS)
    check_choice("model", MODELS)
    created = values["created"]
    if created not in (None, ""):
        try:
            if not (isinstance(created, str) and DATE_RE.match(created)):
                raise ValueError
            dt.date.fromisoformat(created)
        except ValueError:
            problems.append(f"created must be a date YYYY-MM-DD (got {created!r})")
    depends = values["depends_on"]
    if depends is not None:
        if not isinstance(depends, list):
            problems.append(f"depends_on must be a list like [0039] (got {depends!r})")
        else:
            for dep in depends:
                if not ID_RE.match(dep):
                    problems.append(f"depends_on entry {dep!r} is not a 4-digit ID")
                elif dep == entry.id:
                    problems.append("depends_on lists the task itself")
                elif dep not in known_ids:
                    problems.append(f"depends_on {dep} does not exist")
    attempts = values["attempts"]
    if attempts is not None and not (isinstance(attempts, str) and attempts.isdigit()):
        problems.append(f"attempts must be a whole number (got {attempts!r})")
    started = values["started"]
    if started is not None:
        try:
            dt.datetime.fromisoformat(started)
        except (TypeError, ValueError):
            problems.append(f"started must be an ISO date-time (got {started!r})")
    if entry.state == "in-progress":
        for key in ("claimed_by", "started"):
            if values[key] in (None, ""):
                problems.append(f"in-progress task is missing managed field '{key}'")

    names = [name for name, _, _ in doc.sections() if name in SECTIONS]
    missing = [name for name in SECTIONS if name not in names]
    problems += [f"missing section '## {name}'" for name in missing]
    if not missing and names != list(SECTIONS):
        problems.append("sections must appear once each, in order: " + ", ".join(SECTIONS))
    if entry.state != "backlog":
        problems += [
            f"section '{name}' is empty (required outside backlog/)"
            for name in FILLED_SECTIONS
            if name in names and not is_filled(doc.section_text(name) or "")
        ]
    return problems


def validate(root: Path) -> list[str]:
    tasks = root / "tasks"
    if not tasks.is_dir():
        return ["tasks/: folder not found (run 'tasks init')"]
    problems = []
    for path in sorted(tasks.iterdir(), key=lambda p: p.name):
        if (path.is_dir() and path.name in STATES) or (path.is_file() and path.name in CONTROL_FILES):
            continue
        kind = "folder" if path.is_dir() else "file"
        problems.append(f"{rel(root, path)}: unexpected {kind} in tasks/")
    problems += [f"tasks/{s}/: missing state folder" for s in STATES if not (tasks / s).is_dir()]
    problems += [f"tasks/{f}: missing" for f in CONTROL_FILES if not (tasks / f).is_file()]

    entries, stray = scan(root)
    for path in stray:
        kind = "folder" if path.is_dir() else "file"
        problems.append(f"{rel(root, path)}: unexpected {kind}; state folders hold only NNNN-slug.md tasks")
    by_id: dict[str, list[Entry]] = defaultdict(list)
    for entry in entries:
        by_id[entry.id].append(entry)
    known = set(by_id)
    for entry in entries:
        others = [rel(root, e.path) for e in by_id[entry.id] if e is not entry]
        if others:
            problems.append(f"{rel(root, entry.path)}: duplicate id {entry.id} (also {', '.join(others)})")
        problems += [f"{rel(root, entry.path)}: {msg}" for msg in file_problems(entry, known)]
    return problems


def claim_blockers(entry: Entry, agent: str, done_ids: set[str]) -> list[str]:
    doc = entry.doc
    reasons = []
    assigned = doc.get("agent")
    if assigned not in (agent, "either"):
        reasons.append(f"assigned to agent '{assigned}', not '{agent}'")
    unmet = [dep for dep in (doc.get("depends_on") or []) if dep not in done_ids]
    if unmet:
        reasons.append(f"depends on tasks not in done/: {', '.join(unmet)}")
    empty = doc.empty_sections()
    if empty:
        reasons.append(f"empty sections: {', '.join(empty)}")
    return reasons


def priority_key(entry: Entry) -> tuple[str, str]:
    priority = entry.doc.get("priority") if entry.doc else None
    return (priority if priority in PRIORITIES else "p9", entry.id)


# --- commands ------------------------------------------------------------------


def cmd_init(args) -> int:
    root = find_root(args.root, for_init=True)
    tasks = root / "tasks"
    created = []
    if not tasks.is_dir():
        tasks.mkdir(parents=True)
        created.append(tasks)
    for state in STATES:
        folder = tasks / state
        if not folder.is_dir():
            folder.mkdir()
            created.append(folder)
        keep = folder / ".gitkeep"
        if not keep.exists():
            keep.write_bytes(b"")
            created.append(keep)
    for name, content in (("README.md", README_MD), ("_template.md", TEMPLATE_MD)):
        path = tasks / name
        if not path.exists():
            path.write_bytes(content.encode("utf-8"))
            created.append(path)
    if created:
        for path in created:
            print(f"created {rel(root, path)}")
    else:
        print("tasks/ is already initialised; nothing changed")
    return 0


def cmd_new(args) -> int:
    root = find_root(args.root)
    require_queue(root)
    title = " ".join(args.title.split())
    if not title:
        raise TaskError("title must not be empty")
    entries, _ = scan(root)
    ids = {e.id for e in entries}
    depends = []
    for part in re.split(r"[,\s]+", args.depends or ""):
        if part:
            dep = norm_id(part)
            if dep not in ids:
                raise TaskError(f"--depends {dep}: no such task")
            depends.append(dep)

    next_number = max((int(i) for i in ids), default=0) + 1
    if next_number > 9999:
        raise TaskError("no task IDs left (0001-9999 are used)")
    task_id = f"{next_number:04d}"
    template = root / "tasks" / "_template.md"
    doc = TaskDoc(read_text(template) if template.is_file() else TEMPLATE_MD)
    doc.set("id", task_id)
    doc.set("title", title)
    doc.set("agent", args.agent)
    if args.review_by or doc.has("review_by"):
        doc.set("review_by", args.review_by)
    doc.set("priority", args.priority)
    doc.set("depends_on", depends)
    if args.model or not doc.get("model"):
        doc.set("model", args.model or "default")
    doc.set("created", dt.date.today().isoformat())
    doc.set("claimed_by", None)
    doc.set("started", None)
    doc.set("attempts", 0)
    doc.append_log(log_line(args.by, "created in backlog"))

    backlog = root / "tasks" / "backlog"
    backlog.mkdir(exist_ok=True)
    path = backlog / f"{task_id}-{slugify(title)}.md"
    try:
        with open(path, "xb") as handle:
            handle.write(doc.text().encode("utf-8"))
    except FileExistsError:
        raise TaskError(f"{rel(root, path)} already exists; try again") from None
    print(rel(root, path))
    return 0


def cmd_move(args) -> int:
    root = find_root(args.root)
    require_queue(root)
    task_id = norm_id(args.id)
    target = norm_state(args.state)
    entries, _ = scan(root)
    matches = [e for e in entries if e.id == task_id]
    if not matches:
        raise TaskError(f"task {task_id} not found")
    if len(matches) > 1:
        raise TaskError(f"task {task_id} is duplicated: {', '.join(rel(root, e.path) for e in matches)}")
    entry = matches[0]
    source = entry.state
    if source == target:
        raise TaskError(f"task {task_id} is already in {target}/")
    if (source, target) not in TRANSITIONS:
        allowed = [t for s, t in sorted(TRANSITIONS, key=lambda p: STATES.index(p[1])) if s == source]
        raise TaskError(
            f"cannot move task {task_id} from {source}/ to {target}/; "
            f"allowed from {source}/: {', '.join(t + '/' for t in allowed)}"
        )
    if entry.error:
        raise TaskError(f"{rel(root, entry.path)}: {entry.error}")
    if (source, target) in NOTE_REQUIRED and not (args.note or "").strip():
        raise TaskError(f"moving {source}/ to {target}/ requires --note")
    doc = entry.doc
    if target in ("ready", "in-progress"):
        known = {e.id for e in entries}
        problems = [p for p in file_problems(Entry(entry.path, target, entry.id, doc), known)
                    if not p.startswith("in-progress task is missing")]
        if problems:
            raise TaskError(f"{rel(root, entry.path)} is not valid: " + "; ".join(problems))
    if (source, target) in NEEDS_FILLED:
        empty = doc.empty_sections()
        if empty:
            raise TaskError(f"task {task_id} cannot enter {target}/: empty sections: {', '.join(empty)}")
    who = args.by
    if target == "in-progress":
        if who not in CLAIMANTS:
            raise TaskError("claiming a task requires --by claude or --by codex")
        done_ids = {e.id for e in entries if e.state == "done"}
        reasons = claim_blockers(entry, who, done_ids)
        if reasons:
            raise TaskError(f"task {task_id} is not eligible for {who}: " + "; ".join(reasons))
        attempts = doc.get("attempts")
        doc.set("claimed_by", who)
        doc.set("started", now().isoformat())
        doc.set("attempts", int(attempts) + 1 if isinstance(attempts, str) and attempts.isdigit() else 1)
    elif target in ("ready", "backlog"):
        doc.set("claimed_by", None)
        doc.set("started", None)
    note = f"{source} -> {target}"
    if (args.note or "").strip():
        note += f": {args.note.strip()}"
    doc.append_log(log_line(who or "human", note))

    destination = root / "tasks" / target / entry.path.name
    if destination.exists():
        raise TaskError(f"{rel(root, destination)} already exists")
    destination.parent.mkdir(exist_ok=True)
    try:
        os.replace(entry.path, destination)  # atomic: only one process can win a claim
    except FileNotFoundError:
        raise TaskError(f"task {task_id} was already moved (it is no longer in {source}/)") from None
    write_atomic(destination, doc.text())
    print(f"moved {task_id} {source}/ -> {target}/: {rel(root, destination)}")
    return 0


def cmd_list(args) -> int:
    root = find_root(args.root)
    require_queue(root)
    entries, _ = scan(root)
    state = norm_state(args.state) if args.state else None
    rows = []
    for entry in sorted(entries, key=lambda e: (STATES.index(e.state), *priority_key(e))):
        if state and entry.state != state:
            continue
        doc = entry.doc
        agent = doc.get("agent") if doc else None
        if args.agent and agent != args.agent:
            continue
        title = doc.get("title") if doc else None
        rows.append((
            entry.id,
            entry.state,
            str(agent or "?"),
            str((doc.get("priority") if doc else None) or "?"),
            str(title) if title else "(invalid: run tasks validate)",
        ))
    if not rows:
        print("no tasks")
        return 0
    header = ("ID", "STATE", "AGENT", "PRI", "TITLE")
    widths = [max(len(r[i]) for r in [header, *rows]) for i in range(4)]
    for row in (header, *rows):
        print("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row[:4])) + "  " + row[4])
    return 0


def cmd_next(args) -> int:
    root = find_root(args.root)
    require_queue(root)
    entries, _ = scan(root)
    known = {e.id for e in entries}
    done_ids = {e.id for e in entries if e.state == "done"}
    eligible = [
        e for e in entries
        if e.state == "ready"
        and not file_problems(e, known)
        and not claim_blockers(e, args.agent, done_ids)
    ]
    if not eligible:
        return 1
    print(min(eligible, key=priority_key).id)
    return 0


def cmd_validate(args) -> int:
    if args.hook:
        return validate_hook(args)
    root = find_root(args.root)
    problems = validate(root)
    for problem in problems:
        print(problem)
    if problems:
        return 1
    count = len(scan(root)[0])
    print(f"ok: {count} task{'s' if count != 1 else ''}, no problems")
    return 0


def validate_hook(args) -> int:
    """Stop hook for Claude Code and Codex: exit 2 with problems on stderr so the agent
    fixes them; otherwise print an empty JSON object (Codex expects JSON on stdout)."""
    try:
        payload = json.loads(sys.stdin.read() or "{}") if not sys.stdin.isatty() else {}
    except ValueError:
        payload = {}
    problems = []
    # stop_hook_active: this turn already continued because of a Stop hook; don't loop.
    if not (isinstance(payload, dict) and payload.get("stop_hook_active")):
        try:
            problems = validate(find_root(args.root))
        except TaskError:
            problems = []
    if not problems:
        print("{}")
        return 0
    print(
        f"tasks validate found {len(problems)} problem(s) in tasks/. Fix them with the "
        "scripts/tasks helper (never hand-edit managed fields), then finish:",
        file=sys.stderr,
    )
    for problem in problems:
        print(f"  {problem}", file=sys.stderr)
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tasks", description="Manage the tasks/ folder queue (the folder a task is in is its state)."
    )
    parser.add_argument("--version", action="version", version=f"task-queue v{__version__}")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", help="project root containing tasks/ (default: found automatically)")
    sub = parser.add_subparsers(dest="command", required=True, metavar="command")

    p = sub.add_parser("init", parents=[common], help="create tasks/ and its folders; safe to re-run")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("new", parents=[common], help="create a task in backlog/")
    p.add_argument("title")
    p.add_argument("--agent", required=True, choices=AGENTS)
    p.add_argument("--priority", default="p2", choices=PRIORITIES)
    p.add_argument("--depends", help="comma-separated IDs that must be in done/ first")
    p.add_argument("--review-by", choices=REVIEWERS)
    p.add_argument("--model", choices=MODELS)
    p.add_argument("--by", default="human", help="who is creating it, for the Log (default: human)")
    p.set_defaults(func=cmd_new)

    p = sub.add_parser("move", parents=[common], help="move a task to another state")
    p.add_argument("id")
    p.add_argument("state", help=", ".join(STATES))
    p.add_argument("--by", help="who is moving it: claude, codex, human, ... (required for in-progress)")
    p.add_argument("--note", help="note for the Log")
    p.set_defaults(func=cmd_move)

    p = sub.add_parser("list", parents=[common], help="list tasks")
    p.add_argument("--state")
    p.add_argument("--agent", choices=AGENTS)
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("next", parents=[common], help="print the next eligible task ID")
    p.add_argument("--agent", required=True, choices=CLAIMANTS)
    p.set_defaults(func=cmd_next)

    p = sub.add_parser("validate", parents=[common], help="check every task file and folder rule")
    p.add_argument("--hook", action="store_true", help="run as a Claude Code or Codex Stop hook")
    p.set_defaults(func=cmd_validate)
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except TaskError as exc:
        print(f"tasks: error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
