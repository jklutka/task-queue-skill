---
id: 0004
title: Verify plugin marketplace installs in Claude Code and Codex
agent: either
review_by:
priority: p1
depends_on: []
model: default
created: 2026-10-13
claimed_by: claude
started: 2026-10-13T18:35:54-04:00
attempts: 2
---

## Goal
Both plugin marketplaces are confirmed to validate and install from the published GitHub repo.

## Context
.claude-plugin/marketplace.json, .agents/plugins/marketplace.json, plugins/task-queue/. Written from the Claude Code and Codex plugin docs; tests/test_plugin.py checks the documented rules, but neither `claude plugin validate` nor Codex was available when they were written.

## Done when
- [x] `claude plugin validate .` passes (no warnings with --strict, or warnings understood)
- [x] `claude plugin marketplace add jklutka/task-queue-skill` and `claude plugin install task-queue@task-queue-skill` work; the skill sets up a test project
- [x] `codex plugin marketplace add git@github.com:jklutka/task-queue-skill.git` works and the plugin installs from /plugins
- [x] README install steps corrected for anything that differed

## Out of scope
The skill's behavior; the task file format.

## Log
- 2026-10-13 11:09 claude: created in backlog
- 2026-10-13 18:25 human: backlog -> ready: approved by Justin in chat: finish the next task
- 2026-10-13 18:25 claude: ready -> in-progress
- 2026-10-13 18:26 claude: claude plugin validate --strict passes for the marketplace and the plugin (Claude Code 2.1.296)
- 2026-10-13 18:26 claude: task-queue@task-queue-skill installed from GitHub, enabled; cached plugin is identical to plugins/task-queue/skills/task-queue
- 2026-10-13 18:26 claude: cached install.py set up a clean project (validate ok, second run no changes); the skill also triggered and ran its conflict check in another project. A headless agent-driven run was not possible: the claude CLI login has expired
- 2026-10-13 18:26 claude: README: added installer link and the Windows PATH fix
- 2026-10-13 18:27 claude: in-progress -> blocked: Codex check remains: needs the Codex CLI on this machine (codex plugin marketplace add, then install from /plugins). Claude Code checks are done.
- 2026-10-13 18:35 human: blocked -> ready: Justin confirmed the Codex marketplace add and plugin install work
- 2026-10-13 18:35 claude: ready -> in-progress
- 2026-10-13 18:35 claude: in-progress -> review: All four checks done: Claude Code validate and install, Codex marketplace and install (confirmed by Justin), README fixed
