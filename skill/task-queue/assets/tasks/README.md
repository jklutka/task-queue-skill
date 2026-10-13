<!-- task-queue v1 -->
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
