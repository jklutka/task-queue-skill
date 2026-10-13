#!/usr/bin/env python3
"""Install or upgrade the task-queue pattern in a project.

Mechanical steps only, so they run the same way every time:

  1. stop if tasks/ or scripts/tasks* exist without a task-queue version marker
  2. run the bundled CLI's init; replace tasks/README.md, tasks/_template.md and
     scripts/tasks.py (+ shims) when the installed version is older
  3. insert or refresh the marked task-queue section in AGENTS.md
  4. make sure CLAUDE.md imports @AGENTS.md
  5. optionally merge the Stop hook for Claude Code (.claude/settings.json,
     --claude-hook) and/or Codex (.codex/hooks.json, --codex-hook)
  6. run tasks validate and list every file created or changed

Task files are never touched and nothing is committed.

Exit codes: 0 done (or up to date with --check), 1 error or validate failed
(with --check: install or upgrade needed), 2 stopped for a decision (conflict
or downgrade).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
ASSETS = SKILL_DIR / "assets"
STATES = ("backlog", "ready", "in-progress", "review", "blocked", "done")
CLI_FILES = ("tasks.py", "tasks", "tasks.cmd")
SHIM_MARKER = "task-queue shim"

README_MARKER_RE = re.compile(r"^<!--\s*task-queue v(\d+)\s*-->")
CLI_VERSION_RE = re.compile(r"^__version__\s*=\s*[\"']?(\d+)[\"']?\s*$", re.MULTILINE)
SECTION_START_RE = re.compile(r"<!--\s*task-queue:start v(\d+)\s*-->")
SECTION_END_RE = re.compile(r"<!--\s*task-queue:end\s*-->")
IMPORT_LINE = "@AGENTS.md"
# agent -> (settings file in the project, bundled fragment, where to review it)
HOOKS = {
    "claude": (Path(".claude") / "settings.json", "claude-stop-validate.json", None),
    "codex": (Path(".codex") / "hooks.json", "codex-stop-validate.json",
              "Codex runs project hooks only after you trust them: run /hooks in Codex to review it"),
}


class Stop(Exception):
    """Needs a human decision; nothing has been changed."""


def bundled_version() -> int:
    return int((SKILL_DIR / "VERSION").read_text(encoding="utf-8").strip())


def read(path: Path) -> str | None:
    try:
        return path.read_bytes().decode("utf-8-sig")
    except FileNotFoundError:
        return None


def readme_version(project: Path) -> int | None:
    text = read(project / "tasks" / "README.md")
    match = README_MARKER_RE.match(text or "")
    return int(match.group(1)) if match else None


def cli_version(project: Path) -> int | None:
    match = CLI_VERSION_RE.search(read(project / "scripts" / "tasks.py") or "")
    return int(match.group(1)) if match else None


def agents_version(project: Path) -> int | None:
    match = SECTION_START_RE.search(read(project / "AGENTS.md") or "")
    return int(match.group(1)) if match else None


def find_conflicts(project: Path) -> list[str]:
    conflicts = []
    if (project / "tasks").exists() and readme_version(project) is None:
        conflicts.append("tasks/ exists but tasks/README.md has no '<!-- task-queue vN -->' marker")
    scripts = project / "scripts"
    if (scripts / "tasks.py").exists() and cli_version(project) is None:
        conflicts.append("scripts/tasks.py exists but has no __version__ marker")
    for shim in ("tasks", "tasks.cmd"):
        path = scripts / shim
        if path.exists() and SHIM_MARKER not in (read(path) or ""):
            conflicts.append(f"scripts/{shim} exists but was not installed by task-queue")
    return conflicts


def find_downgrades(project: Path, bundled: int) -> list[str]:
    installed = {
        "tasks/README.md": readme_version(project),
        "scripts/tasks.py": cli_version(project),
        "AGENTS.md section": agents_version(project),
    }
    return [f"{where} is v{v}, newer than this skill (v{bundled})"
            for where, v in installed.items() if v is not None and v > bundled]


# --- change tracking -------------------------------------------------------------


def tracked_paths(project: Path) -> list[Path]:
    paths = [project / "AGENTS.md", project / "CLAUDE.md", *(project / f for f, _, _ in HOOKS.values()),
             project / "tasks", project / "tasks" / "README.md", project / "tasks" / "_template.md"]
    for state in STATES:
        paths += [project / "tasks" / state, project / "tasks" / state / ".gitkeep"]
    paths += [project / "scripts" / name for name in CLI_FILES]
    return paths


def snapshot(project: Path) -> dict[str, str]:
    state = {}
    for path in tracked_paths(project):
        key = path.relative_to(project).as_posix()
        if path.is_dir():
            state[key + "/"] = "dir"
        elif path.is_file():
            state[key] = hashlib.sha256(path.read_bytes()).hexdigest()
    return state


def write_if_changed(path: Path, text: str) -> None:
    data = text.encode("utf-8")
    if path.is_file() and path.read_bytes() == data:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def eol_of(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


# --- steps ------------------------------------------------------------------------


def install_queue(project: Path, bundled: int) -> None:
    subprocess.run(
        [sys.executable, str(ASSETS / "scripts" / "tasks.py"), "init", "--root", str(project)],
        check=True, stdout=subprocess.DEVNULL,
    )
    readme = readme_version(project)
    if readme is None or readme < bundled:
        for name in ("README.md", "_template.md"):
            shutil.copyfile(ASSETS / "tasks" / name, project / "tasks" / name)

    scripts = project / "scripts"
    cli = cli_version(project)
    replace_all = cli is None or cli < bundled
    scripts.mkdir(exist_ok=True)
    for name in CLI_FILES:
        target = scripts / name
        if replace_all or not target.exists():
            shutil.copyfile(ASSETS / "scripts" / name, target)
        if name != "tasks.cmd" and os.name != "nt":
            target.chmod(target.stat().st_mode | 0o111)


def wire_agents(project: Path) -> None:
    path = project / "AGENTS.md"
    section = (ASSETS / "agents-section.md").read_text(encoding="utf-8").strip("\r\n")
    text = read(path)
    if text is None:
        write_if_changed(path, section + "\n")
        return
    section = section.replace("\n", eol_of(text))
    start, end = SECTION_START_RE.search(text), SECTION_END_RE.search(text)
    if start and end and start.start() < end.start():
        updated = text[:start.start()] + section + text[end.end():]
    elif start or end:
        raise Stop("AGENTS.md has only one task-queue marker (or they are out of order); "
                   "fix the markers by hand, then re-run")
    else:
        eol = eol_of(text)
        if text and not text.endswith(("\n", "\r")):
            text += eol
        updated = text + (eol if text.strip() else "") + section + eol
    write_if_changed(path, updated)


def wire_claude(project: Path) -> None:
    path = project / "CLAUDE.md"
    text = read(path)
    if text is None:
        write_if_changed(path, IMPORT_LINE + "\n")
        return
    if any(line.strip() == IMPORT_LINE for line in text.splitlines()):
        return
    eol = eol_of(text)
    if text and not text.endswith(("\n", "\r")):
        text += eol
    lines = text.splitlines()
    gap = eol if lines and lines[-1].strip() else ""
    write_if_changed(path, text + gap + IMPORT_LINE + eol)


def load_settings(path: Path, project: Path) -> dict:
    name = path.relative_to(project).as_posix()
    text = read(path)
    try:
        data = json.loads(text) if text and text.strip() else {}
    except ValueError as exc:
        raise Stop(f"{name} is not valid JSON ({exc}); fix it, then re-run") from None
    hooks = data.get("hooks", {}) if isinstance(data, dict) else None
    if not isinstance(hooks, dict) or not isinstance(hooks.get("Stop", []), list):
        raise Stop(f"{name} has an unexpected shape; add the hook by hand")
    return data


def merge_hook(project: Path, agent: str) -> None:
    settings_file, fragment_name, _ = HOOKS[agent]
    path = project / settings_file
    fragment = json.loads((ASSETS / "hooks" / fragment_name).read_text(encoding="utf-8"))
    settings = load_settings(path, project)
    changed = False
    for event, groups in fragment["hooks"].items():
        existing = settings.setdefault("hooks", {}).setdefault(event, [])
        commands = {h.get("command") for g in existing if isinstance(g, dict)
                    for h in g.get("hooks", []) if isinstance(h, dict)}
        for group in groups:
            if not all(h["command"] in commands for h in group["hooks"]):
                existing.append(group)
                changed = True
    if changed:
        write_if_changed(path, json.dumps(settings, indent=2) + "\n")


def hook_installed(project: Path, agent: str) -> bool:
    return "validate --hook" in (read(project / HOOKS[agent][0]) or "")


def preflight(project: Path, hooks: list[str]) -> None:
    """Raise Stop for anything a later step would refuse, before any file is written."""
    text = read(project / "AGENTS.md") or ""
    start, end = SECTION_START_RE.search(text), SECTION_END_RE.search(text)
    if bool(start) != bool(end) or (start and end and start.start() > end.start()):
        raise Stop("AGENTS.md has only one task-queue marker (or they are out of order); "
                   "fix the markers by hand, then re-run")
    for agent in hooks:
        load_settings(project / HOOKS[agent][0], project)


def run_validate(project: Path) -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, str(project / "scripts" / "tasks.py"), "validate", "--root", str(project)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return result.returncode, (result.stdout + result.stderr).strip()


# --- entry points -----------------------------------------------------------------


def check(project: Path, bundled: int) -> int:
    print(f"task-queue skill: v{bundled}")
    for label, version in (("tasks/README.md", readme_version(project)),
                           ("scripts/tasks.py", cli_version(project)),
                           ("AGENTS.md section", agents_version(project))):
        print(f"  {label}: {'v' + str(version) if version is not None else 'not installed'}")
    claude = read(project / "CLAUDE.md")
    has_import = claude is not None and any(l.strip() == IMPORT_LINE for l in claude.splitlines())
    print(f"  CLAUDE.md imports @AGENTS.md: {'yes' if has_import else 'no'}")
    for agent, (settings_file, _, _) in HOOKS.items():
        state = "installed" if hook_installed(project, agent) else "not installed"
        print(f"  {agent.capitalize()} Stop hook ({settings_file.as_posix()}): {state}")
    problems = find_conflicts(project) + find_downgrades(project, bundled)
    if problems:
        print("Needs a decision:")
        for problem in problems:
            print(f"  - {problem}")
        return 2
    current = (readme_version(project) == cli_version(project) == agents_version(project) == bundled
               and has_import and all((project / "scripts" / n).exists() for n in CLI_FILES))
    print("Up to date." if current else "Install or upgrade needed.")
    return 0 if current else 1


def install(project: Path, bundled: int, adopt: bool, hooks: list[str]) -> int:
    conflicts = find_conflicts(project)
    if conflicts and not adopt:
        raise Stop("found files not created by task-queue:\n"
                   + "\n".join(f"  - {c}" for c in conflicts)
                   + "\nAsk the user; re-run with --adopt to replace README.md, _template.md and "
                     "scripts/tasks* (task files are never touched).")
    downgrades = find_downgrades(project, bundled)
    if downgrades:
        raise Stop("installed version is newer than this skill:\n"
                   + "\n".join(f"  - {d}" for d in downgrades)
                   + "\nUpdate the skill (pull its repo) before re-running.")
    preflight(project, hooks)

    before = snapshot(project)
    if adopt:
        # Remove unmarked control files so the bundled versions replace them.
        unmarked = [project / "tasks" / "README.md"] if readme_version(project) is None else []
        if cli_version(project) is None:
            unmarked.append(project / "scripts" / "tasks.py")
        unmarked += [project / "scripts" / shim for shim in ("tasks", "tasks.cmd")
                     if SHIM_MARKER not in (read(project / "scripts" / shim) or "")]
        for path in unmarked:
            if path.is_file():
                path.unlink()
    install_queue(project, bundled)
    wire_agents(project)
    wire_claude(project)
    for agent in hooks:
        merge_hook(project, agent)
    after = snapshot(project)

    created = sorted(k for k in after if k not in before)
    changed = sorted(k for k in after if k in before and after[k] != before[k])
    print(f"task-queue v{bundled} in {project}")
    if created or changed:
        for key in created:
            print(f"  created  {key}")
        for key in changed:
            print(f"  changed  {key}")
    else:
        print("  no changes (already up to date)")
    for agent, (settings_file, _, review) in HOOKS.items():
        if hook_installed(project, agent):
            note = f"; {review}" if review else ""
            print(f"  {agent.capitalize()} Stop hook: installed in {settings_file.as_posix()}{note}")
        else:
            print(f"  {agent.capitalize()} Stop hook: not installed (add with --{agent}-hook)")
    code, output = run_validate(project)
    print("tasks validate:")
    print("\n".join(f"  {line}" for line in output.splitlines()))
    print("Nothing was committed; review the changes and commit them yourself.")
    return 0 if code == 0 else 1


def main(argv: list[str] | None = None) -> int:
    if sys.version_info < (3, 10):
        print("install.py needs Python 3.10+", file=sys.stderr)
        return 1
    parser = argparse.ArgumentParser(description="Install or upgrade the task-queue pattern in a project.")
    parser.add_argument("--project", default=".", help="project root (default: current directory)")
    parser.add_argument("--check", action="store_true", help="report status only; change nothing")
    parser.add_argument("--claude-hook", action="store_true",
                        help="merge the Claude Code Stop hook into .claude/settings.json")
    parser.add_argument("--codex-hook", action="store_true",
                        help="merge the Codex Stop hook into .codex/hooks.json")
    parser.add_argument("--adopt", action="store_true",
                        help="replace unmarked tasks/README.md and scripts/tasks* (after the user agreed)")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    project = Path(args.project).resolve()
    if not project.is_dir():
        print(f"install.py: {project} is not a folder", file=sys.stderr)
        return 1
    bundled = bundled_version()
    if args.check:
        return check(project, bundled)
    try:
        hooks = [agent for agent in HOOKS if getattr(args, f"{agent}_hook")]
        return install(project, bundled, args.adopt, hooks)
    except Stop as exc:
        print(f"install.py: stopped, nothing changed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
