---
name: task-queue
description: Install, upgrade, check or true up the tasks/ folder task queue in a project, where each task is one Markdown file, the subfolder is its state (backlog, ready, in-progress, review, blocked, done) and a scripts/tasks helper manages it, wired into AGENTS.md and CLAUDE.md. Use when the user asks to set up, install, add, upgrade, update or check the task queue in a project, or to true up tasks/ after work (move finished tasks to review, record blockers, add newly found work). Do not use for general to-do lists, issue trackers such as GitHub Issues or Jira, or job and message queues such as Celery or Redis.
license: MIT
compatibility: Requires Python 3.10+. Works with Claude Code and Codex on Linux, macOS, WSL and Windows.
metadata:
  version: "1"
---

# Task queue

This skill copies a tested, versioned task-queue pattern into a project and
keeps it current. `scripts/install.py` copies the files under `assets/`
verbatim. Never regenerate the CLI, the README, the template or the AGENTS.md
section, and never restate their rules in your own words; the bundled files are
the source of truth.

Paths to `scripts/install.py` and `assets/` are relative to this skill's
folder. `<project>` is the project root. Use `python3` on Linux, macOS and WSL,
and `py` (or `python`) on Windows; Python 3.10+.

## Set up or upgrade

1. **Check.** Run `python scripts/install.py --project <project> --check`.
   Exit 0 means already up to date, 1 means install or upgrade needed, and
   2 means a decision is needed (step 2).
2. **Conflicts.** If the check lists files "not created by task-queue" or
   versions newer than the skill, stop. Show the user what is there (list
   `tasks/`, look at `scripts/tasks*`) and ask how to proceed. For unmarked
   files, the options are: adopt them (`--adopt` replaces `tasks/README.md`,
   `tasks/_template.md` and `scripts/tasks*` with the bundled versions; task
   files are never touched) or abort. For a newer installed version, tell the
   user to update the skill's repo; do not downgrade.
3. **Ask about the hook.** Ask: "Add the optional Stop hook? It runs
   `tasks validate` when each turn ends and sends problems back to the agent.
   I can add it for Claude Code (`.claude/settings.json`), Codex
   (`.codex/hooks.json`), both, or neither; existing settings are kept."
   Skip agents the check already reports as installed.
4. **Install.** Run `python scripts/install.py --project <project>`, adding
   `--claude-hook` and/or `--codex-hook` for the hooks the user chose, and
   `--adopt` only if they chose to adopt. It runs `tasks init`, upgrades the
   README, template and CLI when older, inserts or refreshes the marked
   section in `AGENTS.md`, adds `@AGENTS.md` to `CLAUDE.md`, merges the chosen
   hooks and runs `tasks validate`.
5. **Placement (judgment).** When `AGENTS.md` or `CLAUDE.md` already existed,
   the script appends the section or import at the end. Read the file; if the
   end is a poor fit (for example, after a closing appendix or inside a
   fenced block), move the whole block, both markers included, or the
   `@AGENTS.md` line to a better spot. Do not edit any text between the
   markers or any other line. Re-runs replace the block wherever it sits.
   Never copy the section into `CLAUDE.md`.
6. **Report.** Relay the list of created and changed files and the validate
   result. If the Codex hook was added, tell the user that Codex runs project
   hooks only after they review and trust them with `/hooks`. Do not commit;
   the user reviews and commits.

## True up

When the user asks to true up, or after completing a major step in a project
that has `tasks/`, compare the queue with the work actually done this session:

1. Run `scripts/tasks list` in the project (Windows: `scripts\tasks list`).
2. For each task you claimed and finished, tick its `Done when` boxes and run
   `scripts/tasks move <id> review --by <you> --note "<what was done>"`.
3. For each task you claimed that is stuck, run
   `scripts/tasks move <id> blocked --by <you> --note "<what blocks it or what decision is needed>"`.
4. For newly found work, run `scripts/tasks new "<title>" --agent <claude|codex|either>`,
   then fill Goal, Context, Done when and Out of scope in the new file's body.
5. Run `scripts/tasks validate` and fix every problem it reports.

`<you>` is `claude` or `codex`. Never move anything into `ready/` or `done/`
during a true-up. Never edit `claimed_by`, `started` or `attempts` by hand. Do
not commit.

## Releasing a new version (maintainers)

Bump `VERSION`, `metadata.version` above, the `<!-- task-queue vN -->` line in
`assets/tasks/README.md` and in `README_MD` inside `assets/scripts/tasks.py`,
`__version__` in `assets/scripts/tasks.py`, and the start marker in
`assets/agents-section.md`, all together. Then run the tests and re-run this
skill in each project.
