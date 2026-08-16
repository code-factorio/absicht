---
name: absicht-task-workflow
description: Operational playbook for absicht task tickets — harness and gate gotchas that CLAUDE.md, the specs and the task prompts do not state.
---

# absicht task-run playbook

Observed frictions from the Foundations phase (tickets 01-06). Binding rules
live in `CLAUDE.md`, `docs/tasks/00-conventions.md`, the specs and the task
prompts — this file carries only what they do not say.

## Harness environment

- The agent shell exports `FORCE_COLOR=3`. rich then emits ANSI into Typer's
  CliRunner capture, splitting `--flag` substrings, so every case of
  `tests/test_cli.py::test_command_offers_every_documented_flag` fails. This
  pre-exists every ticket — do not stash-bisect your diff over it, and do not
  "fix" `test_cli.py` for it.
- Run every suite through `env -u FORCE_COLOR -u COLORTERM`, pytest included:
  `env -u FORCE_COLOR -u COLORTERM ./scripts/verify.sh`. Re-diagnosing this
  from scratch cost real time on every one of the first six tickets.

## Gate quirks

- `deps` (deptry) fails DEP002 on any `[project.dependencies]` entry that
  `src/` never imports. Tools invoked only via `uv run` (rohrpost `rp`) and
  test-only packages belong in the dev dependency group. After touching
  dependencies, run `uv lock` and commit `uv.lock` with `pyproject.toml`.
- mypy strict needs stubs for untyped third-party deps (pyyaml ships no
  `py.typed`): add the matching `types-*` package to the dev group.
- After writing each new test or module, run
  `uv run ruff check --fix <file> && uv run ruff format <file>` before
  `verify.sh quick` — I001 import order and formatting are the recurring
  first failures (hit on 5 of 6 tickets).

## Editing the import-linter layer list

- `00-conventions.md`'s stack listing is the target state, not the current
  file: `findings` and `git` already sit below `codec`, and comments differ.
  Read the current `[[tool.importlinter.contracts]]` block before editing;
  pasting from the conventions doc makes `Edit` fail with "String to replace
  not found" (bit two tickets). Insert the new layer in place; do not reorder
  entries that are already there.
