@echo off
rem task-queue shim: runs tasks.py next to this file with the first Python 3.10+ found.
setlocal
set "TASKS_PY="
for %%P in (py python python3) do if not defined TASKS_PY (
  %%P -c "import sys; sys.exit(sys.version_info < (3, 10))" <nul >nul 2>&1 && set "TASKS_PY=%%P"
)
if not defined TASKS_PY (
  echo tasks: Python 3.10+ not found ^(tried py, python, python3^) 1>&2
  exit /b 127
)
%TASKS_PY% "%~dp0tasks.py" %*
exit /b %errorlevel%
