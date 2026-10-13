---
id: 0006
title: Define runner rules for moves into ready and done
agent: either
review_by:
priority: p2
depends_on: [0005]
model: default
created: 2026-10-13
claimed_by:
started:
attempts: 0
---

## Goal
The rules allow an approved runner to make the moves it needs (merged PR from review to done, queueing review tasks in ready) while agents in interactive sessions still never approve or accept work.

## Context
The spec and the AGENTS.md section say only humans move tasks into ready/ or done/. Testing the skill on a project with an existing runner showed it moves merged PRs to done/ and creates review tasks directly in ready/. That project's AGENTS.md also says headless agents never touch tasks/, which conflicts with the task-queue section telling agents to true up. The helper doesn't authenticate who moves a task (--by is only logged), so this is about written rules and --by values, not enforcement. Related: 0005.

## Done when
- [ ] Spec defines the runner as an actor and which moves it may make
- [ ] AGENTS.md section says how headless runner sessions treat the task-queue rules
- [ ] tasks/README.md updated; version bumped if the AGENTS.md section changes
- [ ] Tests updated for any change to allowed transitions or --by handling

## Out of scope
Building the runner; migrating the existing project's queue.

## Log
- 2026-10-13 18:16 claude: created in backlog
