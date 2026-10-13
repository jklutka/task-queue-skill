---
id: 0002
title: Confirm CI passes on all platforms after first push
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
The GitHub Actions matrix (Linux, macOS, Windows x Python 3.10, 3.13) passes on the published repo.

## Context
.github/workflows/test.yml. Tests so far ran locally on Windows with Python 3.14 only, including the PowerShell shim and the sh Stop hook.

## Done when
- [x] Workflow ran on main
- [x] All six jobs green, or failures fixed in plugins/task-queue/skills/task-queue/ and tests/

## Out of scope
New features; changes to the spec.

## Log
- 2026-10-13 09:29 claude: created in backlog
- 2026-10-13 12:18 claude: run 38428919367 on fc4656f passed all six jobs (Linux, macOS, Windows x Python 3.10, 3.13)
