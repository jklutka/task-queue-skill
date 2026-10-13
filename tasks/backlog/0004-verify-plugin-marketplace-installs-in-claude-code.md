---
id: 0004
title: Verify plugin marketplace installs in Claude Code and Codex
agent: either
review_by:
priority: p1
depends_on: []
model: default
created: 2026-10-13
claimed_by:
started:
attempts: 0
---

## Goal
Both plugin marketplaces are confirmed to validate and install from the published GitHub repo.

## Context
.claude-plugin/marketplace.json, .agents/plugins/marketplace.json, plugins/task-queue/. Written from the Claude Code and Codex plugin docs; tests/test_plugin.py checks the documented rules, but neither `claude plugin validate` nor Codex was available when they were written.

## Done when
- [ ] `claude plugin validate .` passes (no warnings with --strict, or warnings understood)
- [ ] `claude plugin marketplace add jklutka/task-queue-skill` and `claude plugin install task-queue@task-queue-skill` work; the skill sets up a test project
- [ ] `codex plugin marketplace add git@github.com:jklutka/task-queue-skill.git` works and the plugin installs from /plugins
- [ ] README install steps corrected for anything that differed

## Out of scope
The skill's behavior; the task file format.

## Log
- 2026-10-13 11:09 claude: created in backlog
