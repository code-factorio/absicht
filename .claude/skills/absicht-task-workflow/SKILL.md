---
name: absicht-task-workflow
description: Operational playbook for absicht task tickets — harness and gate gotchas that CLAUDE.md, the specs and the task prompts do not state.
---

# absicht task-run playbook

Observed frictions from the Foundations and Authoring phases. Binding rules
live in `CLAUDE.md`, `docs/tasks/00-conventions.md`, the specs and the task
prompts — this file carries only what they do not say.

## Harness environment

- Prefix EVERY suite invocation with `env -u FORCE_COLOR -u COLORTERM`,
  verify.sh and pytest alike, FIRST call of the session included. The shell
  exports `FORCE_COLOR=3`; a raw call fails the ~24 flag-presence cases in
  `tests/test_cli.py` (rich ANSI-splits `--flag`). That failure pre-exists
  every diff and is never yours: all eight reviewer agents ran verify.sh raw
  first and re-derived this from scratch before re-running guarded.
- zsh expands a word starting with `=` (=cmd expansion): `echo ===` and bare
  `==` separators fail with "not found". Quote them or use `---`.

## Gates

- deptry DEP002 fires on `[project.dependencies]` entries src/ never
  imports: uv-run-only tools (rohrpost `rp`) and test-only packages go in
  the dev group, then `uv lock` and commit uv.lock with pyproject.toml.
- mypy strict needs `types-*` stubs for deps without py.typed
  (types-pyyaml precedent) — dev group, not project deps.
- Run `uv run ruff check --fix <files> && uv run ruff format <files>` after
  EVERY edit round, not only before the first gate run: I001/format
  resurface whenever a file is touched again after its fix pass (twice in
  Authoring). Autofix rewrites the file — re-Read it before the next Edit,
  or the old_string no longer matches (three Edit misses, one ticket).
- `verify.sh mutation` runs in minutes and mutmut CACHES verdicts in the
  gitignored `mutants/` dir, re-serving them when only tests changed:
  `rm -rf mutants` before any run whose score you will trust or compare
  (stale cache cost one extra full run on two tickets). The run's output is
  \r-spinner-padded and may land in a tool-results file — read the verdict
  with `tr '\r' '\n' | grep -a "mutation:"` or redirect to a file, and list
  survivors with `uv run mutmut results`.

## Editing the import-linter layer list

- The live `[[tool.importlinter.contracts]]` block is the only truth; specs
  drift from it in BOTH directions. 00-conventions.md's stack listing is
  the target state, and a ticket's own DoD can claim "no change needed"
  while the block needs a reorder (resolve sat above check until the
  integrity ticket moved it). Read the current block, insert the new layer
  in place, never reorder what is already correct — pasting from a doc
  makes Edit fail with "String to replace not found".

## Reporting, committing, probing

- Commit ids in a return value or ticket comment: copy them from
  `git log`/`git rev-parse` output. One agent reported hallucinated full
  SHAs (right short prefix, wrong tail) and the reviewer's `git show` died
  on them — resolve received ids via `git rev-parse <short>`.
- Commit messages containing backticks need the heredoc form
  `git commit -m "$(cat <<'EOF' ... EOF)"` or `-F <file>`; a plain
  double-quoted `-m` runs the backticks as command substitution.
- Multi-line python probes: write /tmp/probe.py and run it. Inline
  `uv run python -c` with nested quotes fought the shell for ~8 calls on
  one ticket before the file form just worked.
