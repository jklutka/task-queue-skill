---
id: 0003
title: Verify the skill and Stop hook in a real Codex session
agent: either
review_by:
priority: p2
depends_on: []
model: default
created: 2026-10-13
claimed_by:
started:
attempts: 0
---

## Goal
The skill and the Codex Stop hook are confirmed working in a real Codex session on Linux or macOS and on Windows.

## Context
skill/task-queue/assets/hooks/codex-stop-validate.json. Built from the Codex docs (skills in ~/.agents/skills; hooks in .codex/hooks.json; exit 2 + stderr continues the turn; Stop stdout must be JSON). The commands were tested by running them the way the docs describe, not inside Codex. The docs don't say which shell runs hook commands on Windows; commandWindows (.\scripts\tasks.cmd) was tested in both cmd and PowerShell.

## Done when
- [ ] Codex lists the skill from ~/.agents/skills and runs scripts/install.py from it
- [ ] After trusting the hook with /hooks, a stray file in tasks/ makes Codex continue the turn and fix it
- [ ] Same check on Windows; fix commandWindows if Codex uses a different shell
- [ ] README and spec updated with anything learned

## Out of scope
The Claude Code hook; the task file format.

## Log
- 2026-10-13 10:49 claude: created in backlog
