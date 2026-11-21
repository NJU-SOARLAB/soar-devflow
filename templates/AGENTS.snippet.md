## Engineering Workflow (SOAR DevFlow)

This repository uses [SOAR DevFlow](https://github.com/NJU-SOARLAB/soar-devflow) for project tracking and technical documentation:

- **Process Management**: Follow skill `soar-devflow-tasks`. Project settings live in `.soar-devflow/tasks.json`; group chat notification settings live in `.soar-devflow/notifications.json`.
- **Docs Site & Tutorials**: Follow skill `soar-devflow-docs`. Technical docs live in `docs/site/`; check and screenshot settings live in `.soar-devflow/docs.json`.
- **Rules**: Never commit credentials. Native tasks track real completion—do not close tasks that still require human or hardware verification.
