---
name: absicht-task-workflow
description: Operational playbook for absicht task tickets — harness and gate gotchas that CLAUDE.md, the specs and the task prompts do not state.
---

# absicht task-run playbook

Frictions observed across Foundations, Authoring and Projections — only
operational facts the binding rules do not state.

## Environment and command forms

- Prefix EVERY suite invocation with `env -u FORCE_COLOR -u COLORTERM`,
  verify.sh and pytest alike, FIRST call of the session included: the shell
  exports `FORCE_COLOR=3` and rich ANSI-splits `--flag`, failing the
  flag-presence cases in `tests/test_cli.py`. Pre-exists every diff, never
  yours — 14 reviewers so far ran a raw suite first and re-derived this;
  impl agents that read this file don't.
- zsh expands a word starting with `=`: `echo ===` and bare `==` fail.
- `ab`'s `--store`/`--rev` are root options: pass them BEFORE the
  subcommand (`ab --store X list component`), after it they are USAGE errors;
  only `--json` works in both positions.
- `rp comment ID "text"` takes the note POSITIONALLY — no `--text` flag
  (`rp close` uses `--reason`); check `rp <cmd> -h` before inventing flags.
- `docs/users/` doesn't exist yet (docs/: adr, maintainers, spec, tasks) —
  create it on first use, don't `ls` it.

## Gates

- deptry DEP002 fires on `[project.dependencies]` entries src/ never
  imports: uv-run-only tools (rohrpost `rp`), test-only packages and the
  `types-*` stubs mypy strict wants go in the dev group; `uv lock` and commit
  uv.lock with pyproject.toml.
- After EVERY edit round: `uv run ruff check --fix <files> && uv run ruff
  format <files>`. Besides I001/format, the pytest rules fire on new test
  files with NO auto-fix (PT011 broad `pytest.raises`, PT018 compound
  asserts) — budget a hand-fix round. Autofix rewrites files: re-Read
  before the next Edit or the old_string misses (five times, two phases).
- `verify.sh mutation` takes minutes and mutmut re-serves CACHED verdicts
  from gitignored `mutants/` when only tests changed: `rm -rf mutants`
  first. Output is \r-spinner-padded — redirect to a file, read with
  `tr '\r' '\n' | grep -a "mutation:"`, survivors via `uv run mutmut
  results`.
- The live `[[tool.importlinter.contracts]]` block is the only truth
  (specs drift from it in BOTH directions): read it, insert the new layer
  in place, never reorder — pasting from a doc makes Edit miss.

## Snapshots and fixtures

- Golden `.ambr` files are generated, byte-faithful output: regenerate
  with `env -u FORCE_COLOR -u COLORTERM uv run pytest <file>::<test>
  --snapshot-update` and commit the `.ambr` with the change. Growing a
  fixture system moves OTHER tickets' snapshots (brownfield growth moved
  `test_build.ambr` on gaps). Never hand-edit or strip them —
  `tests/__snapshots__/` is excluded from the trailing-whitespace hook
  for that reason; keep it that way. Grep fixtures before a red assertion
  assumes an edge or owner: trace's no-route pair was linked by an up
  `contains` hop.

## Reporting and committing

- Commit ids in a return value or ticket comment: copy from `git log` /
  `git rev-parse` output — agents keep completing short prefixes into
  wrong full SHAs (layout again; only a failed call exposed it).
- Commit messages containing backticks need `git commit -m "$(cat <<'EOF'
  ... EOF)"` or `-F <file>`; plain `-m` runs them as command substitution.
- Multi-line python probes: write /tmp/probe.py and run it; inline
  `uv run python -c` with nested quotes fights the shell.
