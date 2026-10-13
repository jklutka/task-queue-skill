---
id: 0005
title: Allow project-specific frontmatter fields
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
Projects can add their own frontmatter fields (for example a runner's branch and pr) without `tasks validate` failing, while typos in the built-in fields are still caught.

## Context
validate reports every field outside FIELDS in assets/scripts/tasks.py as an unknown field. Found when testing the skill on a project whose existing runner (Invoke-TaskRunner.ps1) writes branch and pr when a task moves to review or blocked, and kind and parent on cross-review tasks. Editing the installed tasks.py locally is undone by the next skill upgrade. Options: accept fields with a prefix such as x-, or read extra allowed fields from a project-level setting (outside tasks/, which may only hold README.md, _template.md and the six folders). The spec plans a later runner, which will need this.

## Done when
- [ ] Approach chosen and recorded in docs/spec.md
- [ ] tasks validate accepts project fields and still flags misspelled built-in fields
- [ ] Managed-field updates in move leave project fields untouched
- [ ] Tests cover both cases; README and tasks/README.md document the rule

## Out of scope
Building the runner; git automation; changes to the built-in fields.

## Log
- 2026-10-13 18:16 claude: created in backlog
