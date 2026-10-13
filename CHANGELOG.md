# Changelog

All notable changes are recorded here. The pattern version is the number in
`plugins/task-queue/skills/task-queue/VERSION`; installed projects carry it in their version markers.

## v1 — 2026-10-13

First release.

- `tasks/` queue: six state folders, the task file format and the allowed transitions
- `tasks` helper with `init`, `new`, `move`, `list`, `next` and `validate`, plus sh and Windows shims
- `task-queue` skill: conflict-safe install and upgrade, `AGENTS.md` section, `CLAUDE.md` import
- Optional Stop hook that runs `tasks validate`, for Claude Code (`.claude/settings.json`) and Codex (`.codex/hooks.json`)
- Plugin marketplace for Claude Code and Codex (`task-queue@task-queue-skill`)
- Skill follows the Agent Skills format and installs in Claude Code (`~/.claude/skills`) and Codex (`~/.agents/skills`)
- Test suite covering every acceptance criterion in the spec
