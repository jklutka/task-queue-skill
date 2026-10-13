# Contributing

Thanks for your interest in improving the task queue. Bug reports, ideas and
pull requests are all welcome.

## Ground rules

- **Standard library only.** The helper and installer must run on a stock
  Python 3.10+ with nothing installed.
- **Cross-platform.** Use `pathlib`, never assume `/` separators or a POSIX
  shell, and keep the sh and `.cmd` shims working.
- **The spec is the contract.** Behavior is defined in [docs/spec.md](docs/spec.md).
  If a change alters behavior, update the spec in the same pull request.
- **Edit the source, not the installed copy.** Everything shipped lives in
  `plugins/task-queue/skills/task-queue/`. The repo-root `scripts/`, `tasks/README.md` and
  `tasks/_template.md` are an installed copy. Refresh them with
  `python plugins/task-queue/skills/task-queue/scripts/install.py --project .`
- **Keep embedded files in sync.** `assets/tasks/README.md` and
  `assets/tasks/_template.md` are also embedded in `assets/scripts/tasks.py`
  (`README_MD` and `TEMPLATE_MD`). A test fails if they differ.

## Development

```bash
python -m unittest discover -s tests -v
```

Every acceptance criterion in the spec has a test. Add or update tests with
every behavior change. CI runs the suite on Linux, macOS and Windows with
Python 3.10 and 3.13.

## Releasing a new pattern version

Projects upgrade when the bundled version is newer than the installed one. To
release:

1. Bump `plugins/task-queue/skills/task-queue/VERSION`, and the `version` in both
   plugin manifests (`plugins/task-queue/plugin.json` and
   `plugins/task-queue/.claude-plugin/plugin.json`) to `N.0.0`.
2. Update the matching markers: `metadata.version` in `SKILL.md`, the first line of
   `assets/tasks/README.md` and of
   `README_MD` in `assets/scripts/tasks.py`, `__version__` in
   `assets/scripts/tasks.py`, and the start marker in `assets/agents-section.md`.
3. Add an entry to [CHANGELOG.md](CHANGELOG.md).
4. Run the tests (`ConsistencyTests` checks that the markers agree).
5. Re-run the skill in each project to upgrade it.

## Pull requests

- Keep each pull request focused on one change and explain why it's needed.
- Make sure the test suite passes locally.
- By contributing, you agree that your contributions are licensed under the
  [MIT License](LICENSE).
