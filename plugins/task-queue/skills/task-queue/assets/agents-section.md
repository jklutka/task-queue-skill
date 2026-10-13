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
