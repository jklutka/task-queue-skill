# Feature Spec: Task Queue Pattern and Skill

Oct 13, 2026 · Justin Klutka

## Summary

Build a `tasks/` folder queue in the repository where each unit of work is one
Markdown file, the subfolder it sits in is its state, and a field in the file
says whether Claude, Codex or either agent should pick it up. Add a small
command-line helper so tasks can be created, moved, listed and validated
without hand-editing.

The goal is to replace handing work to agents through conversation with a
written, inspectable queue. Planning still happens in conversation; the output
of planning is task files.

The pattern is packaged as a `task-queue` skill built once in a canonical repo.
The skill copies the tested assets into any project and wires them into
`AGENTS.md` and `CLAUDE.md`, so every project gets an identical queue instead
of a fresh reimplementation.

## Scope

This feature covers the folder structure, the task file format and a helper to
manage them; it does not run agents.

**In scope**

- The `tasks/` folder and its six state subfolders
- `tasks/_template.md` and `tasks/README.md`
- The task file format: naming, frontmatter fields, required body sections
- The allowed state transitions
- A `tasks` command-line helper with `init`, `new`, `move`, `list`, `next` and `validate` commands
- A `task-queue` skill that installs, wires up, upgrades and validates the pattern in any project
- The task-queue section for `AGENTS.md` and the `@AGENTS.md` import for `CLAUDE.md`
- An optional Stop hook that runs `tasks validate`, for Claude Code and Codex
- The canonical repo that holds the spec, assets, tests and skill

**Out of scope**

- Any runner loop that invokes Claude Code or Codex headless
- Git automation: branches, commits, pushes, PRs
- Cloud or Windows scheduling, usage-limit handling
- Cross-review task generation (`review_by` is stored but not acted on)

## Folder structure

The repository root gets one `tasks/` folder with six state subfolders and two
control files; the folder a task file sits in is its only state.

```
tasks/
  README.md       rules for agents, condensed from this spec
  _template.md    copied by `tasks new`
  backlog/        drafted, not approved
  ready/          approved, waiting to be picked up
  in-progress/    picked up by one agent
  review/         finished, waiting on human review
  blocked/        failed or needs a decision
  done/           accepted
```

| Folder         | Meaning                             | Normally moved here by            |
| -------------- | ----------------------------------- | --------------------------------- |
| `backlog/`     | Drafted, not yet approved           | Human, or an agent during planning |
| `ready/`       | Approved and fully specified        | Human only                        |
| `in-progress/` | Claimed by exactly one agent        | Agent or runner                   |
| `review/`      | Work finished, awaiting review      | Agent or runner                   |
| `blocked/`     | Failed, stalled or needs a decision | Agent or runner                   |
| `done/`        | Reviewed and accepted               | Human only                        |

Each empty subfolder contains a `.gitkeep` so the structure survives in git.
No other files or folders may live directly in `tasks/`; `validate` reports
anything unexpected.

## Task file format

Each task is one file named `NNNN-short-slug.md`: a four-digit, zero-padded ID
that is never reused, then a lowercase hyphenated slug of the title. The name
never changes as the file moves between folders.

```markdown
---
id: 0042
title: Add retry with backoff to the sync job
agent: claude          # claude | codex | either
review_by:             # optional: claude | codex | human
priority: p2           # p1 | p2 | p3
depends_on: [0039]     # IDs that must be in done/ first
model: default         # default | light | heavy
created: 2026-10-13
claimed_by:            # set on move to in-progress
started:               # set on move to in-progress
attempts: 0            # incremented on each move to in-progress
---

## Goal
One or two sentences describing the outcome, not the steps.

## Context
Relevant files, prior decisions, links to related tasks or docs.

## Done when
- [ ] Concrete, checkable conditions

## Out of scope
Files, modules or changes that must not be touched.

## Log
```

| Field                               | Required | Allowed values              | Rule                                                 |
| ----------------------------------- | -------- | --------------------------- | ---------------------------------------------------- |
| `id`                                | Yes      | 4 digits                    | Matches the filename prefix; unique across all folders |
| `title`                             | Yes      | Text                        | Slug in filename derives from it at creation         |
| `agent`                             | Yes      | `claude`, `codex`, `either` | Decides which agent may pick the task up             |
| `priority`                          | Yes      | `p1`, `p2`, `p3`            | `p1` is most urgent                                  |
| `created`                           | Yes      | `YYYY-MM-DD`                | Set by `tasks new`                                   |
| `depends_on`                        | No       | List of IDs                 | Every ID must exist                                  |
| `review_by`                         | No       | `claude`, `codex`, `human`  | Stored only in this feature                          |
| `model`                             | No       | `default`, `light`, `heavy` | Defaults to `default`                                |
| `claimed_by`, `started`, `attempts` | Managed  | –                           | Written by `tasks move`, never by hand               |

Body sections: Goal, Context, Done when, Out of scope and Log, in that order.
Goal, Done when and Out of scope must be non-empty for a task to enter
`ready/`. Log entries are appended, one line each:
`- YYYY-MM-DD HH:MM <who>: <note>`.

> Implementation note: the inline `#` comments above document the allowed
> values; the shipped `_template.md` omits them because the helper parses only
> flat `key: value` lines (see Implementation notes).

## Allowed transitions

`tasks move` permits only the transitions below; agents and runners move work
forward or hand it back, and every approval and acceptance is a human move.

| From           | To             | Typical actor   | Extra rule                                 |
| -------------- | -------------- | --------------- | ------------------------------------------ |
| `backlog/`     | `ready/`       | Human           | Goal, Done when, Out of scope non-empty    |
| `ready/`       | `in-progress/` | Agent or runner | Task must be eligible for that agent       |
| `in-progress/` | `review/`      | Agent or runner | –                                          |
| `in-progress/` | `blocked/`     | Agent or runner | `--note` required                          |
| `in-progress/` | `ready/`       | Agent or runner | Released unfinished, e.g. usage limit      |
| `review/`      | `done/`        | Human           | –                                          |
| `review/`      | `ready/`       | Human           | `--note` with requested changes            |
| `blocked/`     | `ready/`       | Human           | Same checks as backlog → ready             |
| any            | `backlog/`     | Human           | Shelved                                    |

The helper does not authenticate who runs it; the actor column documents
intent, and `--by` is recorded in the Log.

## Helper CLI

A single `tasks` command manages the queue so no one edits folders or managed
fields by hand; every command exits non-zero with a clear message on error.

| Command | Behavior |
| ------- | -------- |
| `tasks init` | Creates `tasks/`, the six subfolders with `.gitkeep`, `_template.md` and `README.md`. Safe to re-run; never overwrites existing files. |
| `tasks new "<title>" --agent <a> [--priority p2] [--depends 0039,0040]` | Allocates the next ID (highest existing ID across all folders + 1), copies the template into `backlog/` with frontmatter filled, prints the path. |
| `tasks move <id> <state> [--by <who>] [--note "<text>"]` | Moves the file if the transition is allowed, updates managed fields, appends a Log line. Rejects a disallowed transition and lists the allowed ones. |
| `tasks list [--state <s>] [--agent <a>]` | Prints a table of ID, state, agent, priority, title, sorted by state then priority then ID. |
| `tasks next --agent <claude\|codex>` | Prints the ID of the next eligible task without moving it, or nothing and exit code 1 if none. |
| `tasks validate` | Checks every file against the format and folder rules; prints one line per problem; exit code 0 only if clean. |

**Eligibility for `next`:** the task is in `ready/`, its `agent` matches or is
`either`, every `depends_on` ID is in `done/`, and its required sections are
filled. Ties break by priority (`p1` first), then lowest ID.

**Managed-field updates in `move`:** moving to `in-progress/` sets `claimed_by`
(from `--by`), `started` (now) and increments `attempts`; moving back to
`ready/` clears `claimed_by` and `started` but keeps `attempts`.

## Skill: task-queue

The `task-queue` skill copies the pattern into a project and keeps it current;
it never regenerates the CLI or rewrites rules in its own words.

**Triggers:** a request to set up, install, upgrade or check the task queue in
a project, or to true up `tasks/` after work.

Setup and upgrade behavior, in order:

1. **Check for conflicts.** If `tasks/` or `scripts/tasks.py` exists but was not
   created by this skill (no version marker), stop and ask before changing
   anything.
2. **Install or upgrade the queue.** Run the bundled CLI's `init`. Replace
   `tasks/README.md`, `tasks/_template.md` and `scripts/tasks.py` and its shims
   with the bundled versions when the installed version is older. Never touch
   task files.
3. **Wire up `AGENTS.md`.** Create it if missing. Insert the task-queue section
   between `<!-- task-queue:start vN -->` and `<!-- task-queue:end -->`. If the
   markers exist, replace only what is between them.
4. **Wire up `CLAUDE.md`.** Create it containing `@AGENTS.md` if missing. If it
   exists without that import, add the import on its own line at the end.
   Never copy the section into it.
5. **Offer the hook.** Ask whether to add the Stop hook (see below) for Claude
   Code, Codex, both or neither. Merge into `.claude/settings.json` and/or
   `.codex/hooks.json`; never overwrite existing settings.
6. **Validate and report.** Run `tasks validate`, then list every file created
   or changed. Do not commit; the user reviews and commits.

**True-up behavior:** when asked to true up, compare `tasks/` with the work
actually done in the session. Move finished tasks to `review/`, move stuck ones
to `blocked/` with a note, add newly discovered work to `backlog/`, then run
`tasks validate`. Never move anything into `ready/` or `done/`.

**Stop hook (optional):** a Stop hook that runs `tasks validate` when a turn
ends and reports problems back to the agent: in `.claude/settings.json` for
Claude Code, and in `.codex/hooks.json` for Codex (which runs project hooks
only after the user trusts them with `/hooks`). It exits 2 with the problems
on stderr to send the agent back to fix them, prints `{}` otherwise, and
does nothing when `stop_hook_active` is set, so it can't loop. The pattern
works without it; it only makes the true-up harder to skip.

## Agent instructions

The section the skill inserts into `AGENTS.md` is short on purpose: it says the
queue exists, when to use it and how to true it up, and leaves the full rules
to `tasks/README.md`.

```markdown
<!-- task-queue:start v1 -->
## Task queue
Planned work lives in tasks/ (rules: tasks/README.md; helper: scripts/tasks.py).
- Before starting, check tasks/ready/ for work assigned to you or to `either`.
- For multi-step or multi-slice work, break it into task files in
  tasks/backlog/ instead of keeping the plan only in conversation.
- After completing a major step, true up tasks/: move your finished work
  to review/, record blockers in blocked/, add newly found work to
  backlog/, then run `tasks validate`.
- Never move tasks into ready/ or done/; those are human decisions.
<!-- task-queue:end -->
```

`CLAUDE.md` gets one line, `@AGENTS.md`, so Claude Code and Codex read
identical instructions from one source.

**Version markers:** the installed version is recorded in three places the
skill checks: the `AGENTS.md` start marker, a first-line comment in
`tasks/README.md` (`<!-- task-queue v1 -->`) and a `__version__` constant in
`scripts/tasks.py`.

## Canonical repo

Everything is built and tested once in a `task-queue-skill` repo; the skill
folder inside it is what gets installed into your user-level skills folder.

```
task-queue-skill/
  .claude-plugin/marketplace.json    Claude Code plugin marketplace
  .agents/plugins/marketplace.json   Codex plugin marketplace
  docs/spec.md                       this spec, exported
  plugins/task-queue/                the plugin
    .claude-plugin/plugin.json       Claude Code plugin manifest
    plugin.json                      Codex plugin manifest
    skills/task-queue/               the skill
      SKILL.md                       triggers and the setup, upgrade, true-up steps
      VERSION                        current pattern version, e.g. 1
      scripts/install.py             mechanical setup and upgrade steps
      assets/
        tasks/README.md              agent-facing rules
        tasks/_template.md
        scripts/tasks.py             the CLI
        scripts/tasks                shell shim
        scripts/tasks.cmd            Windows shim
        agents-section.md            the AGENTS.md section, with markers
        hooks/claude-stop-validate.json  the optional Claude Code Stop hook fragment
        hooks/codex-stop-validate.json   the optional Codex Stop hook fragment
  tests/                             CLI, skill install and plugin tests
  tasks/                             this repo's own queue, used while building it
```

The repo is a plugin marketplace for Claude Code (`.claude-plugin/marketplace.json`)
and Codex (`.agents/plugins/marketplace.json`) listing one plugin, `task-queue`,
which holds the skill. Plugin-level hooks are deliberately absent: the Stop hook
is per project and is added by `install.py`. Without a plugin manager, install by
linking `plugins/task-queue/skills/task-queue/` into the user-level skills folder
(`~/.claude/skills/` for Claude Code, `~/.agents/skills/` for Codex), so pulling
the repo upgrades the installed skill. The skill follows the open Agent Skills
format (agentskills.io): runnable code in `scripts/`, copied files in
`assets/`, and `name`, `description`, `license`, `compatibility` and
`metadata` frontmatter.

Releasing a change means bumping `VERSION` and the markers together, then
re-running the skill in each project.

## Acceptance criteria

The feature is done when each of these can be shown with a test or a command
run.

- `tasks init` on an empty repo creates exactly the structure in Folder structure; a second run changes nothing.
- `tasks new` creates `backlog/0001-<slug>.md` in an empty queue and the next call creates `0002`, even if `0001` has moved to `done/`.
- `tasks move` allows every transition in the Allowed transitions table and rejects every other one without touching the file.
- Moving a task to `ready/` fails if Goal, Done when or Out of scope is empty.
- Moving to `in-progress/` sets `claimed_by`, `started` and increments `attempts`; each move appends exactly one Log line.
- `tasks next --agent codex` skips tasks with `agent: claude`, skips tasks with unmet dependencies, and picks `p1` before `p2`.
- `tasks validate` flags: duplicate IDs, filename and id mismatch, missing required fields, invalid values, unknown `depends_on` IDs, and stray files in `tasks/`.
- Running the skill on a project with no `tasks/`, `AGENTS.md` or `CLAUDE.md` creates all three, and `validate` passes.
- Running it on a project with existing `AGENTS.md` and `CLAUDE.md` content adds the section and import without changing any other line.
- Running it twice produces no changes the second time.
- Bumping `VERSION` and re-running replaces only the content between markers, the README, the template and the CLI; no task file changes.
- The skill stops and asks when it finds an unmarked `tasks/` or `scripts/tasks.py`.
- All commands work the same on Windows (PowerShell) and Linux (WSL).
- Automated tests cover each criterion above.

## Implementation notes

Keep the helper small, dependency-free and boring; it is plumbing for a later
runner.

- **Language:** Python 3.10+, standard library only, in a single file `scripts/tasks.py` with a thin `tasks` entry point (a shell script and a `.cmd`/`.ps1` shim for Windows).
- **Frontmatter:** parse and write only the flat key-value and inline-list subset shown in the template. Preserve the body text and field order exactly when updating managed fields.
- **Atomic moves:** use `os.replace` within the same filesystem so two processes can't both claim a file; if the source no longer exists, report that the task was already moved.
- **Paths:** use `pathlib` throughout; never assume `/` separators or a POSIX shell.
- **Git:** the helper never runs git. Committing queue changes belongs to the later runner.
- **Tests:** `unittest` with temporary directories, one test per acceptance criterion.
- **README.md:** a short, agent-facing summary of the folder meanings, file format and the rule that agents never edit managed fields by hand.

**Skill internals:** put the mechanical setup and upgrade steps in a bundled
`install.py` so they run the same way every time. The agent's judgment is
reserved for the parts a script can't decide: conflicts with unmarked files,
and where an import or section fits in an existing `CLAUDE.md` or `AGENTS.md`.
