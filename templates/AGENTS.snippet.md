## Engineering Workflow (SOAR DevFlow)

This repository uses [SOAR DevFlow](https://github.com/NJU-SOARLAB/soar-devflow) for project tracking and technical documentation:

- **Pre-Work Task Gate (Required)**: Before starting any substantive feature, performance optimization, cross-module refactor, or non-trivial bugfix, load skill `soar-devflow-tasks` first—check remote tasks to avoid duplicates, register a task via `create_task.py` (or append to the configured rolling minor-fix doc for tiny fixes), and after delivery run `sync_tasks.py` and `notify_delivery.py`. Pure Q&A does not create tasks; recording a plan does not authorize implementation or deployment.
- **Project Configs**: Task settings live in `.soar-devflow/tasks.json` (or legacy `docs/development_management/registry.json`); notification settings live in `.soar-devflow/notifications.json`. In multi-repo workspaces, run scripts from the target sub-repo or pass `--config`.
- **Docs Site & Tutorials**: When editing `docs/site/`, guides, references, or specs, load skill `soar-devflow-docs` and run `check_docs.py --check` before finishing.
- **Integrity Rules**: Never commit credentials. Native tasks track real completion—keep native tasks open (`待人工验收` / `review`) whenever human judgment, UI/UX feel, or hardware verification is still required.
