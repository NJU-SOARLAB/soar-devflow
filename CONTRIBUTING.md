# Contributing to SOAR DevFlow

Thanks for your interest in contributing to **SOAR DevFlow**!

## Core Design Principles

1. **Zero project coupling in skills and scripts.** Every project-specific coordinate (tenant domain, space ID, tasklist GUID, stage names, language list, paths) belongs in the target project's local configuration, never inside `skills/`.
2. **Fail closed on remote mutations.** Never guess IDs, never silently overwrite manual human edits or comments, and always verify readback after structural document changes.
3. **Deterministic gates over prose reminders.** If a rule can be enforced mechanically (anchor parity, unclosed Vue tags, broken links, idempotent notifications, privacy leaks), enforce it in `scripts/` and test it in `tests/`.
4. **Honest evidence.** Never mark a task or check as passed unless it actually ran and succeeded.

## Local Verification

Run the full test suite, privacy scan, and companion site gate before opening a PR:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/privacy_scan.py --include-untracked
python3 skills/soar-devflow-docs/scripts/check_docs.py --config site/docs.config.json --check
cd site && npm ci && npm run build
```

## Opening a Pull Request

- Keep PRs focused on a single capability or bug fix.
- Add or update unit tests in `tests/` for any script behavior change.
- If user-facing behavior or config schema changes, update both Chinese and English documentation under `site/`.
