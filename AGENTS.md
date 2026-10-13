# Agent instructions

This repo builds the `task-queue` skill (spec: docs/spec.md).

- The source of truth is `skill/task-queue/`. `scripts/`, `tasks/README.md` and
  `tasks/_template.md` at the repo root are an installed copy; never edit them.
  Change `skill/task-queue/assets/` and re-run
  `python skill/task-queue/scripts/install.py --project .` instead.
- `tasks/README.md` and `tasks/_template.md` are also embedded in
  `assets/scripts/tasks.py` (`README_MD`, `TEMPLATE_MD`); keep them identical.
- Run `python -m unittest discover -s tests` before finishing; it must pass.
- Python 3.10+, standard library only.

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
